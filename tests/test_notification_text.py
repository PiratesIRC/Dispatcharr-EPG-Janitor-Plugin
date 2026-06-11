"""Tests for the Django-free notification_text helpers (extracted from
plugin.py). These pin the Dispatcharr ~380-char action-card contract.
"""
import unittest

import notification_text


class TestFilterPhrase(unittest.TestCase):
    def test_few_items_are_named(self):
        self.assertEqual(
            notification_text.filter_phrase(["A", "B"], "in", "groups"),
            " in groups: A, B")

    def test_many_items_collapse_to_count(self):
        items = [f"g{i}" for i in range(10)]
        self.assertEqual(
            notification_text.filter_phrase(items, "in", "groups"),
            " in 10 groups")

    def test_three_items_still_named(self):
        self.assertEqual(
            notification_text.filter_phrase(["A", "B", "C"], "in", "groups"),
            " in groups: A, B, C")

    def test_parens_wrapping(self):
        self.assertEqual(
            notification_text.filter_phrase(["A"], "in", "groups", parens=True),
            " (in groups: A)")


class TestTruncateMessage(unittest.TestCase):
    def test_short_message_unchanged(self):
        self.assertEqual(notification_text.truncate_message("hello"), "hello")

    def test_empty_and_none(self):
        self.assertEqual(notification_text.truncate_message(""), "")
        self.assertEqual(notification_text.truncate_message(None), "")

    def test_long_message_is_clamped_to_cap(self):
        text = "x" * 1000
        out = notification_text.truncate_message(text)
        self.assertLessEqual(len(out), notification_text.NOTIFICATION_CHAR_CAP)
        self.assertTrue(out.endswith("…"))

    def test_custom_limit(self):
        out = notification_text.truncate_message("abcdefghij", limit=5)
        self.assertLessEqual(len(out), 5)
        self.assertTrue(out.endswith("…"))


if __name__ == "__main__":
    unittest.main()
