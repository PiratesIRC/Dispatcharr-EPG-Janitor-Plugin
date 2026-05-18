"""Unit tests for EPG-Janitor's wildcard_match module."""
import unittest


class TestExpandPatterns(unittest.TestCase):
    def test_literal_case_sensitive_miss(self):
        import wildcard_match
        m, u = wildcard_match.expand_patterns(["abc"], ["ABC", "abc"], ci_plain=False)
        self.assertEqual(m, ["abc"])
        self.assertEqual(u, [])

    def test_literal_case_insensitive_hit(self):
        import wildcard_match
        m, u = wildcard_match.expand_patterns(["abc"], ["ABC"], ci_plain=True)
        self.assertEqual(m, ["ABC"])
        self.assertEqual(u, [])

    def test_star_prefix(self):
        import wildcard_match
        m, u = wildcard_match.expand_patterns(
            ["US*"], ["US ABC", "US CBS", "UK ITV"], ci_plain=False)
        self.assertEqual(m, ["US ABC", "US CBS"])
        self.assertEqual(u, [])

    def test_star_suffix_and_contains(self):
        import wildcard_match
        m, _ = wildcard_match.expand_patterns(
            ["*HD"], ["ABC HD", "ABC SD"], ci_plain=False)
        self.assertEqual(m, ["ABC HD"])
        m2, _ = wildcard_match.expand_patterns(
            ["*Sport*"], ["Fox Sports 1", "CNN"], ci_plain=False)
        self.assertEqual(m2, ["Fox Sports 1"])

    def test_star_is_case_insensitive(self):
        import wildcard_match
        m, _ = wildcard_match.expand_patterns(
            ["us*"], ["US ABC"], ci_plain=False)
        self.assertEqual(m, ["US ABC"])

    def test_question_single_char(self):
        import wildcard_match
        m, _ = wildcard_match.expand_patterns(
            ["Pluto ?"], ["Pluto 1", "Pluto 12"], ci_plain=False)
        self.assertEqual(m, ["Pluto 1"])

    def test_bare_star_matches_all(self):
        import wildcard_match
        m, u = wildcard_match.expand_patterns(["*"], ["A", "B"], ci_plain=False)
        self.assertEqual(m, ["A", "B"])
        self.assertEqual(u, [])

    def test_unmatched_token_reported(self):
        import wildcard_match
        m, u = wildcard_match.expand_patterns(
            ["ZZ*", "A"], ["A", "B"], ci_plain=False)
        self.assertEqual(m, ["A"])
        self.assertEqual(u, ["ZZ*"])

    def test_token_order_preserved_for_priority(self):
        import wildcard_match
        m, _ = wildcard_match.expand_patterns(
            ["B*", "A*"], ["A1", "B1", "A2"], ci_plain=False)
        self.assertEqual(m, ["B1", "A1", "A2"])

    def test_dedup_overlapping_patterns(self):
        import wildcard_match
        m, _ = wildcard_match.expand_patterns(
            ["US*", "*ABC"], ["US ABC", "US CBS"], ci_plain=False)
        self.assertEqual(m, ["US ABC", "US CBS"])

    def test_mixed_literal_and_glob(self):
        import wildcard_match
        m, u = wildcard_match.expand_patterns(
            ["CNN", "Fox*"], ["CNN", "Fox News", "ESPN"], ci_plain=True)
        self.assertEqual(m, ["CNN", "Fox News"])
        self.assertEqual(u, [])

    def test_empty_inputs(self):
        import wildcard_match
        self.assertEqual(wildcard_match.expand_patterns([], ["A"], ci_plain=False),
                         ([], []))
        self.assertEqual(wildcard_match.expand_patterns(["A"], [], ci_plain=False),
                         ([], ["A"]))
