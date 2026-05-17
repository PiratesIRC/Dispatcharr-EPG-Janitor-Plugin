"""Unit tests for EPG-Janitor's progress_status module."""
import unittest


class TestFormatEta(unittest.TestCase):
    def test_zero(self):
        import progress_status
        self.assertEqual(progress_status.format_eta(0), "0s")

    def test_seconds(self):
        import progress_status
        self.assertEqual(progress_status.format_eta(45), "45s")

    def test_minutes_seconds(self):
        import progress_status
        self.assertEqual(progress_status.format_eta(130), "2m 10s")

    def test_hours_minutes(self):
        import progress_status
        self.assertEqual(progress_status.format_eta(3780), "1h 3m")

    def test_exact_one_minute(self):
        import progress_status
        self.assertEqual(progress_status.format_eta(60), "1m 0s")

    def test_hours_zero_minutes(self):
        import progress_status
        self.assertEqual(progress_status.format_eta(3600), "1h 0m")

    def test_negative_clamps_to_zero(self):
        import progress_status
        self.assertEqual(progress_status.format_eta(-5), "0s")


import json
import os
import tempfile


class TestProgressIO(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "p.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_load_missing_returns_idle(self):
        import progress_status
        self.assertEqual(progress_status.load_progress(self.path), {"status": "idle"})

    def test_load_corrupt_returns_idle(self):
        import progress_status
        with open(self.path, "w") as f:
            f.write("{not json")
        self.assertEqual(progress_status.load_progress(self.path), {"status": "idle"})

    def test_save_then_load_roundtrip(self):
        import progress_status
        data = {"status": "running", "action": "preview_auto_match",
                "current": 5, "total": 10, "start_time": 1747500000.0}
        progress_status.save_progress_atomic(self.path, data)
        self.assertEqual(progress_status.load_progress(self.path), data)

    def test_save_is_atomic_no_temp_left(self):
        import progress_status
        progress_status.save_progress_atomic(self.path, {"status": "done"})
        leftovers = [n for n in os.listdir(self.dir) if n != "p.json"]
        self.assertEqual(leftovers, [])


class TestNormalizeStale(unittest.TestCase):
    def test_running_becomes_idle(self):
        import progress_status
        out = progress_status.normalize_stale_progress(
            {"status": "running", "action": "preview_auto_match", "current": 3}
        )
        self.assertEqual(out["status"], "idle")
        self.assertEqual(out["action"], "preview_auto_match")  # other keys kept

    def test_done_unchanged(self):
        import progress_status
        d = {"status": "done", "action": "scan_and_heal_apply"}
        self.assertEqual(progress_status.normalize_stale_progress(d), d)

    def test_idle_unchanged(self):
        import progress_status
        self.assertEqual(
            progress_status.normalize_stale_progress({"status": "idle"}),
            {"status": "idle"},
        )


class TestBuildStatusOrSummary(unittest.TestCase):
    def test_running_shows_percent_and_eta(self):
        import progress_status
        prog = {"status": "running", "action": "preview_auto_match",
                "current": 810, "total": 1000, "start_time": 0.0}
        msg = progress_status.build_status_or_summary(
            prog, None, now=100.0
        )
        self.assertIn("81%", msg)
        self.assertIn("810/1000", msg)
        self.assertIn("Preview Auto-Match", msg)
        # elapsed=100, rate=100/810; remaining=(100/810)*190 ≈ 23.4s -> "23s"
        self.assertIn("ETA: 23s", msg)
        self.assertNotIn("calculating", msg)

    def test_running_zero_current_calculating(self):
        import progress_status
        prog = {"status": "running", "action": "scan_and_heal_apply",
                "current": 0, "total": 50, "start_time": 0.0}
        msg = progress_status.build_status_or_summary(prog, None, now=5.0)
        self.assertIn("calculating", msg)

    def test_done_with_results_shows_summary_and_timestamp(self):
        import progress_status
        prog = {"status": "done", "action": "preview_auto_match"}
        results = {"channels": [{"epg_source": "pia", "channel_group": "US ABC"}],
                   "scan_time": "2026-05-17 20:40", "check_hours": 12,
                   "selected_groups": "", "ignore_groups": "PPV",
                   "total_channels_with_epg": 1517}
        msg = progress_status.build_status_or_summary(prog, results)
        self.assertIn("Last EPG scan", msg)
        self.assertIn("2026-05-17 20:40", msg)          # results' own scan_time
        self.assertIn("no run in progress", msg)
        self.assertIn("Channels missing program data: 1", msg)
        self.assertIn("pia", msg)
        # Bug pin: progress.json's action must NOT leak into the not-running view
        self.assertNotIn("Preview Auto-Match", msg)

    def test_no_results_no_run_friendly(self):
        import progress_status
        msg = progress_status.build_status_or_summary({"status": "idle"}, None)
        self.assertIn("Nothing has been run yet", msg)

    def test_corrupt_progress_treated_idle(self):
        import progress_status
        results = {"channels": [], "scan_time": "x", "check_hours": 12,
                   "selected_groups": "", "ignore_groups": "",
                   "total_channels_with_epg": 0}
        msg = progress_status.build_status_or_summary({}, results)
        self.assertIn("no run in progress", msg)
        self.assertNotIn("ETA:", msg)
