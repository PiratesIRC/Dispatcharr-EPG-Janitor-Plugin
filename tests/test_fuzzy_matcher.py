"""Unit tests for EPG-Janitor's fuzzy_matcher module."""
import unittest


class TestImport(unittest.TestCase):
    def test_module_imports(self):
        import fuzzy_matcher  # noqa: F401


class TestAliases(unittest.TestCase):
    def test_aliases_module_exports_channel_aliases_dict(self):
        import aliases
        self.assertIsInstance(aliases.CHANNEL_ALIASES, dict)
        self.assertGreater(len(aliases.CHANNEL_ALIASES), 100)

    def test_alias_values_are_lists_of_strings(self):
        import aliases
        for key, value in aliases.CHANNEL_ALIASES.items():
            self.assertIsInstance(key, str)
            self.assertIsInstance(value, list)
            for item in value:
                self.assertIsInstance(item, str)

    def test_known_alias_present(self):
        import aliases
        self.assertIn("FOX News Channel", aliases.CHANNEL_ALIASES)
        self.assertIn("FNC", aliases.CHANNEL_ALIASES["FOX News Channel"])


class TestNormalizationPatterns(unittest.TestCase):
    """Verify merged pattern set strips what EPG-Janitor 0.7.0a stripped
    AND what Lineuparr strips."""

    def setUp(self):
        import fuzzy_matcher
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=80)

    # EPG-Janitor legacy coverage
    def test_strips_bracketed_4k(self):
        self.assertEqual(self.m.normalize_name("CNN [4K]").strip().lower(), "cnn")

    def test_strips_bracketed_unknown_lowercase(self):
        self.assertEqual(self.m.normalize_name("CNN [unknown]").strip().lower(), "cnn")

    def test_strips_parenthesized_backup(self):
        self.assertEqual(self.m.normalize_name("CNN (Backup)").strip().lower(), "cnn")

    def test_strips_single_letter_tag(self):
        self.assertEqual(self.m.normalize_name("CNN (A)").strip().lower(), "cnn")

    def test_strips_cx_tag(self):
        self.assertEqual(self.m.normalize_name("Cinemax (CX)").strip().lower(), "cinemax")

    def test_strips_us_prefix(self):
        self.assertEqual(self.m.normalize_name("US: CNN").strip().lower(), "cnn")

    # Lineuparr new coverage
    def test_strips_8k(self):
        self.assertEqual(self.m.normalize_name("CNN 8K").strip().lower(), "cnn")

    def test_strips_pacific(self):
        self.assertEqual(
            self.m.normalize_name("HBO Pacific", ignore_regional=True).strip().lower(),
            "hbo",
        )

    def test_strips_provider_prefix_us_pipe(self):
        self.assertEqual(self.m.normalize_name("US | CNN").strip().lower(), "cnn")

    # Regional toggle behavior
    def test_strips_east_when_ignore_regional_true(self):
        result = self.m.normalize_name("HBO East", ignore_regional=True).strip().lower()
        self.assertEqual(result, "hbo")

    def test_preserves_east_when_ignore_regional_false(self):
        result = self.m.normalize_name("HBO East", ignore_regional=False).strip().lower()
        self.assertIn("east", result)


if __name__ == "__main__":
    unittest.main()
