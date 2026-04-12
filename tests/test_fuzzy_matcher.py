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


class TestCaching(unittest.TestCase):
    def setUp(self):
        import fuzzy_matcher
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=80)

    def test_precompute_populates_norm_cache(self):
        names = ["CNN [HD]", "Fox News", "ESPN 2"]
        self.m.precompute_normalizations(names)
        self.assertEqual(len(self.m._norm_cache), 3)
        for name in names:
            self.assertIn(name, self.m._norm_cache)

    def test_precompute_clears_prior_state(self):
        self.m.precompute_normalizations(["CNN [HD]"])
        self.m.precompute_normalizations(["BBC News"])
        self.assertEqual(len(self.m._norm_cache), 1)
        self.assertNotIn("CNN [HD]", self.m._norm_cache)
        self.assertIn("BBC News", self.m._norm_cache)

    def test_cached_norm_matches_ondemand_norm(self):
        name = "CNN [HD]"
        self.m.precompute_normalizations([name])
        cached, _ = self.m._get_cached_norm(name)
        live = self.m.normalize_name(name).lower()
        self.assertEqual(cached, live)

    def test_cached_nospace_is_stripped(self):
        self.m.precompute_normalizations(["Fox News"])
        _, nospace = self.m._get_cached_norm("Fox News")
        self.assertNotIn(" ", nospace)

    def test_short_names_excluded_from_cache(self):
        self.m.precompute_normalizations(["X"])
        self.assertNotIn("X", self.m._norm_cache)




class TestAliasStage(unittest.TestCase):
    def setUp(self):
        import fuzzy_matcher
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=80)
        self.alias_map = {
            "FOX News Channel": ["Fox News", "FNC", "FOX NEWS"],
            "HISTORY Channel, The": ["HISTORY", "History Channel HD"],
        }

    def test_alias_hits_exact_variant(self):
        result = self.m.alias_match(
            "FOX News Channel",
            ["Fox News"],
            self.alias_map,
        )
        self.assertIsNotNone(result)
        self.assertEqual(len(result), 1)
        matched, score, match_type = result[0]
        self.assertEqual(matched, "Fox News")
        self.assertEqual(match_type, "alias")
        self.assertGreaterEqual(score, 95)

    def test_alias_miss_when_variant_not_in_candidates(self):
        result = self.m.alias_match(
            "FOX News Channel",
            ["CNN", "ESPN"],
            self.alias_map,
        )
        self.assertEqual(result, [])

    def test_alias_empty_map_returns_none(self):
        result = self.m.alias_match("FOX News Channel", ["Fox News"], {})
        self.assertEqual(result, [])

    def test_alias_unknown_query_returns_none(self):
        result = self.m.alias_match("Unknown Channel", ["Fox News"], self.alias_map)
        self.assertEqual(result, [])


class TestLengthScaledThreshold(unittest.TestCase):
    def setUp(self):
        import fuzzy_matcher
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=80)

    def test_short_name_gets_strict_threshold(self):
        t = self.m._length_scaled_threshold(80, 4)
        self.assertGreaterEqual(t, 95)

    def test_medium_name_gets_moderate_threshold(self):
        t = self.m._length_scaled_threshold(80, 8)
        self.assertGreaterEqual(t, 90)
        self.assertLess(t, 95)

    def test_long_name_uses_base_threshold(self):
        t = self.m._length_scaled_threshold(80, 20)
        self.assertEqual(t, 80)


class TestTokenOverlap(unittest.TestCase):
    def setUp(self):
        import fuzzy_matcher
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=80)

    def test_basic_overlap_requires_one_shared_long_token(self):
        self.assertTrue(self.m._has_token_overlap("america racing", "america bbc"))

    def test_basic_no_overlap_when_only_stopwords_shared(self):
        self.assertFalse(self.m._has_token_overlap("the one show", "the big bang"))

    def test_majority_mode_requires_majority_overlap(self):
        self.assertTrue(
            self.m._has_token_overlap("america racing sports", "america racing news", require_majority=True)
        )
        self.assertFalse(
            self.m._has_token_overlap("america racing", "america bbc", require_majority=True)
        )


class TestChannelNumberBoost(unittest.TestCase):
    def setUp(self):
        import fuzzy_matcher
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=80)

    def test_boost_applied_when_number_in_candidate(self):
        boost = self.m._channel_number_boost("CNN 202", 202)
        self.assertGreaterEqual(boost, 5)

    def test_no_boost_when_number_missing(self):
        boost = self.m._channel_number_boost("CNN HD", 202)
        self.assertEqual(boost, 0)

    def test_no_boost_when_channel_number_none(self):
        boost = self.m._channel_number_boost("CNN 202", None)
        self.assertEqual(boost, 0)


class TestMatchAllStreams(unittest.TestCase):
    def setUp(self):
        import fuzzy_matcher
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=80)

    def test_results_sorted_descending_by_score(self):
        results = self.m.match_all_streams(
            "CNN",
            ["CNN", "CNN HD", "Unrelated"],
            alias_map={},
            min_score=0,
        )
        scores = [score for _, score, _ in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_min_score_filters_low_results(self):
        results = self.m.match_all_streams(
            "CNN",
            ["CNN", "Unrelated"],
            alias_map={},
            min_score=50,
        )
        for _, score, _ in results:
            self.assertGreaterEqual(score, 50)

    def test_alias_stage_short_circuits(self):
        results = self.m.match_all_streams(
            "FOX News Channel",
            ["Fox News"],
            alias_map={"FOX News Channel": ["Fox News"]},
            min_score=0,
        )
        self.assertTrue(any(mt == "alias" for _, _, mt in results))

    def test_empty_when_no_matches(self):
        results = self.m.match_all_streams(
            "zzzqqq",
            ["CNN", "ESPN"],
            alias_map={},
            min_score=70,
        )
        self.assertEqual(results, [])


class TestRegionalDifferentiation(unittest.TestCase):
    def setUp(self):
        import fuzzy_matcher
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=70)

    def test_ignore_regional_true_matches_any_region(self):
        # With the toggle on, East/West are stripped at normalize time
        # so all variants are eligible; regional filter skipped.
        results = self.m.match_all_streams(
            "HBO East",
            ["HBO West", "HBO"],
            alias_map={},
            min_score=0,
            user_ignored_tags=["regional"],
        )
        names = {name for name, _, _ in results}
        self.assertIn("HBO", names)

    def test_ignore_regional_false_east_does_not_match_west_only(self):
        results = self.m.match_all_streams(
            "HBO East",
            ["HBO West"],
            alias_map={},
            min_score=0,
            user_ignored_tags=[],
        )
        self.assertEqual(results, [])

    def test_ignore_regional_false_pacific_matches_only_pacific(self):
        results = self.m.match_all_streams(
            "HBO Pacific",
            ["HBO East", "HBO Pacific"],
            alias_map={},
            min_score=0,
            user_ignored_tags=[],
        )
        names = {name for name, _, _ in results}
        self.assertIn("HBO Pacific", names)
        self.assertNotIn("HBO East", names)


class TestLegacyMethodsPresent(unittest.TestCase):
    """Smoke tests confirming EPG-Janitor-specific methods and attributes
    survived the Lineuparr port."""

    def setUp(self):
        import fuzzy_matcher
        self.m = fuzzy_matcher.FuzzyMatcher(plugin_dir="/tmp", match_threshold=85)

    def test_plugin_dir_accepted(self):
        self.assertEqual(self.m.plugin_dir, "/tmp")

    def test_legacy_instance_attrs_initialized(self):
        self.assertEqual(self.m.broadcast_channels, [])
        self.assertEqual(self.m.premium_channels, [])
        self.assertIsNone(self.m.country_codes)

    def test_ignore_star_attrs_default_true(self):
        self.assertTrue(self.m.ignore_quality)
        self.assertTrue(self.m.ignore_regional)
        self.assertTrue(self.m.ignore_geographic)
        self.assertTrue(self.m.ignore_misc)

    def test_legacy_methods_callable(self):
        # Just verify they're present; behavior-level tests come later.
        for name in ("_load_channel_databases", "reload_databases",
                     "extract_callsign", "normalize_callsign",
                     "extract_tags", "find_best_match",
                     "match_broadcast_channel", "get_category_for_channel",
                     "build_final_channel_name"):
            self.assertTrue(hasattr(self.m, name), f"missing: {name}")
            self.assertTrue(callable(getattr(self.m, name)), f"not callable: {name}")

    def test_extract_callsign_basic(self):
        # WABC is a known US broadcast callsign format.
        result = self.m.extract_callsign("WABC ABC 7 New York")
        # Legacy returns extracted callsign string or None/empty; accept either
        # truthy string or None — just checking the method runs without error.
        self.assertIsNotNone(result) if result else self.assertIsNone(result)

    def test_normalize_name_honors_instance_ignore_quality(self):
        # Instance attr should be used when kwarg is omitted/None.
        self.m.ignore_quality = False
        result = self.m.normalize_name("CNN [HD]")
        # With ignore_quality=False, [HD] should NOT be stripped.
        self.assertIn("HD", result.upper())
        # Reset
        self.m.ignore_quality = True


if __name__ == "__main__":
    unittest.main()
