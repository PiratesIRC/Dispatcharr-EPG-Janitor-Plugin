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


if __name__ == "__main__":
    unittest.main()
