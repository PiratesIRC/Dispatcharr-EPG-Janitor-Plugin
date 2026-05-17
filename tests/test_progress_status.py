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
