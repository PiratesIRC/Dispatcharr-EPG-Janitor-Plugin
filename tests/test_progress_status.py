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
