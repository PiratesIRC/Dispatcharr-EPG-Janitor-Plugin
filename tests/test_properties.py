"""Property-based tests for the matcher's pure string functions.

Invariants that must hold for ALL inputs, not just curated examples. Skipped
automatically if Hypothesis is not installed (it is a dev-only dependency;
see requirements-dev.txt).
"""
import unittest

import fuzzy_matcher

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st
    HAVE_HYPOTHESIS = True
except ImportError:  # pragma: no cover - exercised only when dep is absent
    HAVE_HYPOTHESIS = False


@unittest.skipUnless(HAVE_HYPOTHESIS, "hypothesis not installed")
class TestSimilarityProperties(unittest.TestCase):
    def setUp(self):
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=80)

    @settings(max_examples=200)
    @given(st.text(min_size=1, max_size=40))
    def test_identity_is_one(self, s):
        self.assertAlmostEqual(self.m.calculate_similarity(s, s), 1.0, places=9)

    @settings(max_examples=200)
    @given(st.text(max_size=40), st.text(max_size=40))
    def test_ratio_in_unit_interval(self, a, b):
        ratio = self.m.calculate_similarity(a, b)
        self.assertGreaterEqual(ratio, 0.0)
        self.assertLessEqual(ratio, 1.0)

    @settings(max_examples=200)
    @given(st.text(max_size=40), st.text(max_size=40))
    def test_symmetry(self, a, b):
        self.assertAlmostEqual(
            self.m.calculate_similarity(a, b),
            self.m.calculate_similarity(b, a),
            places=9)


@unittest.skipUnless(HAVE_HYPOTHESIS, "hypothesis not installed")
class TestNormalizationProperties(unittest.TestCase):
    def setUp(self):
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=80)

    @settings(max_examples=200)
    @given(st.text(max_size=60))
    def test_process_for_matching_is_idempotent(self, s):
        once = self.m.process_string_for_matching(s)
        twice = self.m.process_string_for_matching(once)
        self.assertEqual(once, twice)


@unittest.skipUnless(HAVE_HYPOTHESIS, "hypothesis not installed")
class TestCallsignProperties(unittest.TestCase):
    def setUp(self):
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=80)

    @settings(max_examples=300)
    @given(st.text(max_size=40))
    def test_extracted_callsign_never_denylisted(self, s):
        callsign = self.m.extract_callsign(s)
        if callsign is not None:
            self.assertNotIn(callsign, self.m._CALLSIGN_DENYLIST)


if __name__ == "__main__":
    unittest.main()
