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


class TestQualityTagLeavesASpace(unittest.TestCase):
    """bug-096: a quality tag in the MIDDLE of a name glued its neighbours together.

    Every QUALITY_PATTERN also consumes the whitespace flanking the tag, so
    substituting an empty string deletes that whitespace with it. A tag at the
    start or end of a name is harmless, because the leftover edge space is
    stripped later; a tag in the middle joins two words that were never one:
    "SKY NEWS FHD rec" became "SKY NEWSrec", which matches nothing.

    The fix belongs HERE rather than in the shared core. The core already
    substitutes a space (its own bug-126 change), but EPG-Janitor is a PARTIAL
    subclass that overrides normalize_name outright, so the core's version never
    runs and re-vendoring the core does not deliver this. That is exactly how the
    fix was credited in a released changelog while being absent from the plugin.
    """

    def setUp(self):
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=80)

    def test_mid_name_quality_tag_does_not_glue_neighbours(self):
        for raw, expected in (
            ("SKY NEWS FHD rec", "SKY NEWS rec"),
            ("CNN [HD] USA", "CNN USA"),
            ("SKY NEWS HD rec", "SKY NEWS rec"),
            # "ONE" folds to "1" further down the pipeline; that is existing,
            # intended behaviour and is not what this test is about. What matters
            # here is the space between "1" and "Scotland".
            ("BBC ONE (UHD) Scotland", "BBC 1 Scotland"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(self.m.normalize_name(raw), expected)

    def test_edge_quality_tags_are_unchanged_by_the_fix(self):
        # A tag at the start or end must still leave no stray space, because the
        # whitespace cleanup at the end of normalize_name removes the edge space
        # the substitution introduces. This is the guard that a naive fix breaks.
        for raw, expected in (
            ("ESPN HD", "ESPN"),
            ("HD ESPN", "ESPN"),
            ("ESPN [FHD]", "ESPN"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(self.m.normalize_name(raw), expected)

    def test_a_custom_ignore_tag_can_reach_a_word_that_followed_a_quality_tag(self):
        # The second half of the same defect. A user ignore tag is applied with a
        # word boundary, and there is no boundary inside "NEWSrec", so the tag
        # silently did nothing on precisely the names the gluing had damaged.
        self.assertEqual(
            self.m.normalize_name("SKY NEWS FHD rec", user_ignored_tags=["rec"]).strip(),
            "SKY NEWS")

    def test_the_plugin_now_agrees_with_the_shared_core_on_this_input(self):
        # Pins the specific divergence rather than the general one: the override
        # legitimately differs from the core elsewhere, but not here.
        import matching_core
        self.assertEqual(
            self.m.normalize_name("SKY NEWS FHD rec"),
            matching_core.FuzzyMatcherCore().normalize_name("SKY NEWS FHD rec"))


class TestBracketGroupGluesItsNeighbours(unittest.TestCase):
    """bug-102: a bracketed group in the MIDDLE of a name joined the words
    around it.

    Every pattern in MISC_PATTERNS also consumes the whitespace flanking the
    bracket group, so substituting the match with '' removed both spaces:
    "Big Ten Network (Southern California) Alternate" normalized to
    "Big 10 NetworkAlternate". A glued token matches nothing, and it is also
    unreachable by a user ignore tag, because there is no word boundary inside
    "NetworkAlternate".

    This is the same defect as bug-096, which corrected QUALITY_PATTERNS only.
    REGIONAL_PATTERNS were corrected as well; the bracket patterns were missed.
    """

    def setUp(self):
        self.m = fuzzy_matcher.FuzzyMatcher()

    def test_a_bracket_group_between_two_words_leaves_them_separate(self):
        for raw, expected in (
            ("Big Ten Network (Southern California) Alternate",
             "Big 10 Network Alternate"),
            ("Penthouse (TEN) On Demand", "Penthouse On Demand"),
            ("Spectrum News (New York) Rochester", "Spectrum News Rochester"),
        ):
            with self.subTest(raw=raw):
                self.assertEqual(self.m.normalize_name(raw), expected)

    def test_no_name_gains_or_loses_letters_only_a_space(self):
        # Invariant guard, not a regression test: this passed before the fix as
        # well, and is here so that a later change cannot start DELETING text
        # under cover of this one. The correction may only insert a separator.
        raw = "Big Ten Network (Southern California) Alternate"
        self.assertEqual(self.m.normalize_name(raw).replace(" ", ""),
                         "Big10NetworkAlternate")

    def test_a_bracket_group_at_the_end_still_leaves_no_trailing_space(self):
        # Positive control: the whitespace cleanup at the end of normalize_name
        # must still absorb the separator when the group is at an edge.
        # "Discovery", not "Comedy Central", because "Central" is stripped as a
        # regional marker and would test something other than the bracket.
        self.assertEqual(self.m.normalize_name("Discovery (US)"), "Discovery")

    def test_a_single_word_ignore_tag_can_reach_a_word_that_followed_a_bracket(self):
        # The second half of the defect, matching bug-096's shape. A SINGLE-word
        # ignore tag is applied with word boundaries, and there is no boundary
        # inside "NewsRochester", so before the fix the tag silently did nothing
        # on precisely the names the gluing had damaged. A multi-word tag would
        # NOT show this, because that path does not use word boundaries.
        self.assertEqual(
            self.m.normalize_name("Spectrum News (New York) Rochester",
                                  user_ignored_tags=["Rochester"]).strip(),
            "Spectrum News")
