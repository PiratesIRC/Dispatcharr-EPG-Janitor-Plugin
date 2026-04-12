"""Unit tests for EPG-Janitor's fuzzy_matcher module."""
import unittest


class TestImport(unittest.TestCase):
    def test_module_imports(self):
        import fuzzy_matcher  # noqa: F401


if __name__ == "__main__":
    unittest.main()
