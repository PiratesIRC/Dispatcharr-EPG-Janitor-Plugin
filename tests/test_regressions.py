"""Regression tests for bugs recorded in .wolf/buglog.json and the cerebrum
Do-Not-Repeat list. Each test pins a specific production failure so matcher
tuning cannot silently reintroduce it.

These exercise fuzzy_matcher only — it is Django-free and importable offline
(tests/__init__.py prepends EPG-Janitor/ to sys.path).
"""
import unittest

import fuzzy_matcher


class TestAliasShortStringFalsePositive(unittest.TestCase):
    """bug-028: Preview Heal scored "MeTV" -> "WE tv" at 90% Alias.

    A single Levenshtein substitution between two 5-char strings scores 0.90,
    which clears the length-scaled threshold. The majority-overlap guard must
    reject it because "me tv" and "we tv" share only the token "tv".
    """

    def setUp(self):
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=80)
        self.alias_map = {"MeTV": ["ME TV", "MeTV"]}

    def test_metv_does_not_alias_match_we_tv(self):
        results = self.m.alias_match("MeTV", ["WE tv"], self.alias_map)
        matched_names = [name for name, _score, _type in results]
        self.assertNotIn("WE tv", matched_names,
                         "MeTV must not alias-match the distinct channel WE tv")

    def test_metv_still_matches_genuine_me_tv(self):
        # Positive control: the guard must not break real matches.
        results = self.m.alias_match("MeTV", ["ME TV"], self.alias_map)
        matched_names = [name for name, _score, _type in results]
        self.assertIn("ME TV", matched_names)


class TestCallsignConfidence(unittest.TestCase):
    """Callsign extraction must distinguish high-confidence (parenthesized /
    end-of-name) from low-confidence (loose mid-name word) callsigns.
    """

    def setUp(self):
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=80)

    def test_parenthesized_callsign_is_high_confidence(self):
        callsign, high_conf = self.m._compute_callsign_with_confidence("ABC (KOMO)")
        self.assertEqual(callsign, "KOMO")
        self.assertTrue(high_conf)

    def test_loose_word_callsign_is_not_high_confidence(self):
        # "with" has callsign shape ([KW][A-Z]{2,4}) but is a common word.
        _callsign, high_conf = self.m._compute_callsign_with_confidence(
            "Bizarre Foods with Andrew Zimmern")
        self.assertFalse(high_conf,
                         "a loose mid-name word must never be a high-confidence callsign")


class TestCallsignAnchor(unittest.TestCase):
    """match_all_streams callsign anchor (cerebrum 2026-05-16/05-21).

    A shared high-confidence callsign rescues a match; a disagreeing one
    hard-rejects a wrong-market false positive. A loose-word callsign must do
    neither.
    """

    def setUp(self):
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=80)

    def test_shared_high_confidence_callsign_floors_match(self):
        results = self.m.match_all_streams("CBS (KMOV)", ["Local CBS KMOV"], {})
        by_name = {name: (score, mtype) for name, score, mtype in results}
        self.assertIn("Local CBS KMOV", by_name)
        score, mtype = by_name["Local CBS KMOV"]
        self.assertGreaterEqual(score, 95)
        self.assertEqual(mtype, "callsign")

    def test_mismatched_high_confidence_callsign_hard_rejects(self):
        # Both normalize to "cbs" (a 100 exact false positive) but the
        # callsigns disagree -> wrong-market, must be rejected.
        results = self.m.match_all_streams("CBS (KMOV)", ["CBS (KPHO)"], {})
        matched_names = [name for name, _score, _type in results]
        self.assertNotIn("CBS (KPHO)", matched_names)

    def test_loose_word_callsign_does_not_anchor(self):
        # "Paramount+ with Showtime" shares only the loose word "with" with the
        # query; it must not be floored to 95 via the callsign anchor.
        results = self.m.match_all_streams(
            "Bizarre Foods with Andrew Zimmern", ["Paramount+ with Showtime"], {})
        for name, score, mtype in results:
            self.assertFalse(
                mtype == "callsign" and score >= 95,
                f"loose-word callsign wrongly anchored {name!r} at {score}")


if __name__ == "__main__":
    unittest.main()
