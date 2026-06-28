"""Regression tests for the 2026-06-14 matcher parity port (sibling-plugin fixes)."""
import json
import os

import pytest
from fuzzy_matcher import FuzzyMatcher

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(HERE, "EPG-Janitor")


def test_norway_channel_db_present_and_valid():
    path = os.path.join(PKG, "NO_channels.json")
    assert os.path.isfile(path), "NO_channels.json must ship with the plugin"
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    channels = data["channels"]
    assert isinstance(channels, list) and len(channels) > 0
    assert all("channel_name" in c for c in channels)


def test_norway_db_loads_via_reload_databases():
    m = FuzzyMatcher(plugin_dir=PKG)
    m.reload_databases(["NO"])
    # reload_databases with a country list loads only that DB; it must not raise.
    assert True


def _matcher():
    return FuzzyMatcher()


def test_bug026_numbered_siblings_below_threshold():
    m = _matcher()
    ratio = m.calculate_similarity("fox sports 1", "fox sports 2")
    assert ratio == pytest.approx(11 / 12, abs=1e-9)
    assert ratio < 0.95


def test_bug026_identity_and_empty():
    m = _matcher()
    assert m.calculate_similarity("espn", "espn") == 1.0
    assert m.calculate_similarity("", "espn") == 0.0
    assert m.calculate_similarity("espn", "") == 0.0


def test_bug026_min_ratio_early_reject_consistent():
    # The min_ratio >= decision must agree across the rapidfuzz and pure-Python
    # paths. The raw below-threshold value may differ (rapidfuzz returns the true
    # ratio; pure-Python may early-return 0.0) — that never flips a call-site
    # >= comparison, so we assert the DECISION, not the raw value.
    import matching_core as fm  # calculate_similarity + _USE_RAPIDFUZZ live in the shared core now
    m = _matcher()
    # 0.9167 < 0.95 -> reject in both paths; 0.9167 >= 0.90 -> accept in both.
    for mr, expect_pass in ((0.95, False), (0.90, True)):
        for use_rf in (True, False):
            fm._USE_RAPIDFUZZ = use_rf
            try:
                ratio = m.calculate_similarity("fox sports 1", "fox sports 2", min_ratio=mr)
            finally:
                fm._USE_RAPIDFUZZ = True
            assert (ratio >= mr) is expect_pass, (mr, use_rf, ratio)
    # the accepted case returns the true ratio in both paths
    assert m.calculate_similarity("fox sports 1", "fox sports 2", min_ratio=0.90) == pytest.approx(11 / 12, abs=1e-9)


def test_bug026_pure_python_matches_rapidfuzz_when_available():
    import matching_core as fm  # calculate_similarity + _USE_RAPIDFUZZ live in the shared core now
    if not getattr(fm, "_USE_RAPIDFUZZ", False):
        pytest.skip("rapidfuzz not installed")
    m = _matcher()
    pairs = [("fox sports 1", "fox sports 2"), ("espn", "espn news"),
             ("bbc one", "bbc two"), ("the cw", "cw")]
    for a, b in pairs:
        rf = m.calculate_similarity(a, b)
        fm._USE_RAPIDFUZZ = False
        try:
            py = m.calculate_similarity(a, b)
        finally:
            fm._USE_RAPIDFUZZ = True
        assert rf == pytest.approx(py, abs=1e-9), f"{a!r} vs {b!r}: rf={rf} py={py}"


def test_numword_to_digit():
    m = _matcher()
    assert m.normalize_name("BBC Three") == m.normalize_name("BBC 3")
    assert m.normalize_name("Channel Four") == m.normalize_name("Channel 4")
    assert "1" not in m.normalize_name("Onesimus")


def test_dot_between_letters_to_space():
    m = _matcher()
    assert m.normalize_name("Racing.com") == m.normalize_name("Racing com")
    assert " TV" in (" " + m.normalize_name("Justice.TV"))


def test_dot_radio_frequency_preserved():
    m = _matcher()
    assert "97 2" not in m.normalize_name("97.2 JACK FM")
    assert "102 3" not in m.normalize_name("102.3 VIRGIN Radio")


def test_camelcase_split():
    m = _matcher()
    assert m.normalize_name("DangerTV") == m.normalize_name("Danger TV")
    assert m.normalize_name("JusticeCentral") == m.normalize_name("Justice Central")


def test_camelcase_protects_short_brands():
    m = _matcher()
    for brand in ("MeTV", "truTV", "GameTV"):
        assert " " not in m.normalize_name(brand), f"{brand} must not be split"


def test_token_overlap_rejects_numeric_siblings():
    m = _matcher()
    # End-to-end: numeric siblings must never appear as matches.
    assert m.match_all_streams("BBC One", ["BBC Two"], {}) == []
    assert m.match_all_streams("ESPN 1", ["ESPN 2"], {}) == []
    # Guard-level: the numeric/ordinal divergent guard must reject directly.
    assert not m._has_token_overlap("bbc one", "bbc two", require_majority=True)
    assert not m._has_token_overlap("espn 1", "espn 2", require_majority=True)


def test_token_overlap_rejects_divergent_brands():
    m = _matcher()
    assert m.match_all_streams("Sky Cinema Disney", ["Sky Cinema Decades"], {}) == []
    # Guard-level: divergent distinctive tokens ("disney" vs "decades").
    assert not m._has_token_overlap(
        "sky cinema disney", "sky cinema decades", require_majority=True
    )


def test_token_overlap_rejects_subset_specific_channel():
    m = _matcher()
    # End-to-end (defense-in-depth): the pipeline rejects a more-specific
    # sibling. For THIS pair the rejection actually comes from the combined
    # bug-026 similarity + substring length-ratio gate, not the subset guard
    # alone — the guard-level assertion below isolates the subset guard itself.
    assert m.match_all_streams("Nickelodeon", ["Nickelodeon Teen"], {}) == []
    # Guard-level: subset guard rejects when the larger side adds a distinctive
    # (>=5 char) token the smaller lacks ("In Country Television" vs
    # "Country Music Television" -> the extra "music" is distinctive).
    assert not m._has_token_overlap(
        "in country television", "country music television", require_majority=True
    )


def test_calc_sim_rapidfuzz_pure_agree_at_exact_cutoff():
    # QA follow-up: rapidfuzz score_cutoff must not zero a score landing exactly
    # on min_ratio (pure-Python returns it). "abcde" vs "abcdf" = 4/5 = 0.8.
    m = _matcher()
    assert m.calculate_similarity("abcde", "abcdf", min_ratio=0.8) == pytest.approx(0.8, abs=1e-9)


def test_provider_prefix_preserves_us_open_brand():
    m = _matcher()
    # "US Open" is a tennis brand, not a US country tag — must survive both the
    # provider bare-space strip and the geographic bare-US strip.
    assert "open" in m.normalize_name("US Open").lower()
    assert "open" in m.normalize_name("US Open Tennis").lower()
    # a genuine US country tag still strips
    assert m.normalize_name("US Armenian TV").lower().strip().startswith("armenian")


def test_provider_prefix_ger_not_over_stripped():
    m = _matcher()
    # GER dropped from the bare-space set -> "GER TV" must not become "TV".
    assert "ger" in m.normalize_name("GER TV").lower()


def test_token_overlap_still_allows_legit_extension():
    # The enriched majority-mode guard must NOT reject a legitimate extension
    # like "ABC News" -> "ABC News Live": the only extra token ("live") is 4
    # chars, below the >=5 subset threshold, so the subset guard stays silent.
    # (We assert on the guard directly because EPG-Janitor's hardened
    # calculate_similarity scores this pair below match_threshold for unrelated
    # reasons (bug-026), so it never reaches the guard via match_all_streams.)
    m = _matcher()
    assert m._has_token_overlap("abc news", "abc news live", require_majority=True)
    assert m._has_token_overlap("abc news", "abc live news", require_majority=True)


def test_trailing_number_method():
    m = _matcher()
    assert m._trailing_number("HBO 2") == 2
    assert m._trailing_number("Sky Sports News 13") == 13
    assert m._trailing_number("ESPN") is None
    assert m._trailing_number("ESPN2") is None  # glued digit, not space-separated


def test_numbered_siblings_rejected_high_similarity():
    m = _matcher()
    # Numbers >12 slip past the Task-5 numeric guard but share ~94% similarity;
    # the trailing-number / digit-token guards must still separate them.
    assert m.match_all_streams("Sky Sports News 13", ["Sky Sports News 14"], {}) == []


def test_digit_token_guard_rejects_only_on_number_disagreement():
    m = _matcher()
    # Both sides numbered with DIFFERENT numbers -> rejected (sibling).
    assert m.match_all_streams("Sky Sports News 13", ["Sky Sports News 14"], {}) == []
    # Numbered channel vs UNnumbered candidate -> ALLOWED. US OTA channels carry the
    # broadcast number but the EPG entry usually doesn't; the digit guard must not
    # reject these (regression found by the real-data match-sim, 2026-06-14).
    assert m.match_all_streams("ABC 7 (KGO) San Francisco HD", ["ABC San Francisco"], {})
    assert m.match_all_streams("NBC 5 (KXAS) Dallas", ["NBC Dallas"], {})


def test_digit_glued_to_token_after_paren_strip_is_respaced():
    m = _matcher()
    # The broad parenthetical strip removes " (KGO) " and would glue "7" to "SAN"
    # ("ABC 7SAN FRANCISCO"); a second digit/letter spacing pass re-splits it so
    # US OTA names tokenize correctly.
    assert "7san" not in m.normalize_name("ABC 7 (KGO) SAN FRANCISCO HD").lower()
    assert "7 san" in m.normalize_name("ABC 7 (KGO) SAN FRANCISCO HD").lower()


def test_numberless_query_not_over_rejected():
    m = _matcher()
    # A numberless query must still match a numbered candidate (guards only fire
    # when the QUERY carries the number/shift).
    assert m.match_all_streams("Sky Sports News", ["Sky Sports News 14"], {})


def test_plus_shift_separation():
    m = _matcher()
    # ~82% similar, differ only by a +1 shift -> must be separated.
    assert m.match_all_streams("Comedy Central +1", ["Comedy Central"], {}) == []
    assert m.match_all_streams("Comedy Central", ["Comedy Central +1"], {}) == []
    res = m.match_all_streams("Comedy Central +1", ["Comedy Central +1"], {})
    assert res and res[0][0] == "Comedy Central +1"


def test_plus_shift_brand_not_treated_as_shift():
    m = _matcher()
    # "Discovery+" is a brand "+", not a +N shift -> still matches itself.
    assert m.match_all_streams("Discovery+", ["Discovery+"], {})


def test_usa_network_not_mis_stripped():
    m = _matcher()
    n = m.normalize_name("USA Network")
    assert "usa" in n.lower() and "network" in n.lower(), f"got {n!r}"


def test_provider_prefix_gaps():
    m = _matcher()
    assert m.normalize_name("PLUTO: MTV") == m.normalize_name("MTV")
    assert m.normalize_name("UKHD: Sky Sports") == m.normalize_name("Sky Sports")
    assert m.normalize_name("US Racer") == m.normalize_name("Racer")


def test_provider_prefix_collisions_preserved():
    m = _matcher()
    assert "gold" in m.normalize_name("UK Gold").lower()
    assert "crowd" in m.normalize_name("IT Crowd").lower()


def test_orig_overlap_tiebreak_orders_by_shared_original_tokens():
    m = _matcher()
    # Both candidates match the query exactly after normalization (nospace
    # "abcnews"), tying at 100. The tie-break ranks the one sharing more
    # ORIGINAL tokens with the query first: "ABCNews" (shares "abcnews")
    # before "ABC News" (shares none of the query's single token).
    res = m.match_all_streams("ABCNews", ["ABC News", "ABCNews"], {})
    names = [n for n, _, _ in res]
    assert names[:2] == ["ABCNews", "ABC News"], names


def test_match_all_streams_deterministic():
    m = _matcher()
    a = m.match_all_streams("Comedy Central", ["Comedy TV", "Comedy Central HD"], {})
    b = m.match_all_streams("Comedy Central", ["Comedy TV", "Comedy Central HD"], {})
    assert a == b


# --- leading "CALLSIGN (NETWORK)" high-confidence rule (jesmann-US format) ---
# Gated on a KNOWN-callsign allowlist (from the loaded DBs). Tests stub the
# allowlist via _known_callsigns so no DB load is needed.

def _matcher_with_callsigns(*callsigns):
    m = _matcher()
    m._known_callsigns = set(callsigns)
    return m


def test_leading_callsign_paren_high_confidence_when_known():
    m = _matcher_with_callsigns("KSVI", "WYTV", "WPLG")
    # jesmann-US names stations "KSVI (ABC)" / "WYTV-DT (ABC)": leading callsign,
    # network in parens. A KNOWN callsign is promoted to HIGH confidence.
    assert m._extract_callsign_with_confidence("KSVI (ABC)") == ("KSVI", True)
    assert m._extract_callsign_with_confidence("WYTV-DT (ABC)") == ("WYTV-DT", True)
    assert m._extract_callsign_with_confidence("WPLG (FOX)") == ("WPLG", True)


def test_leading_callsign_paren_requires_known_callsign():
    # Callsign-shaped ENGLISH WORDS that are NOT real stations must NOT be
    # promoted (a denylist cannot bound this open-ended set — the allowlist does).
    m = _matcher_with_callsigns("KSVI")  # KILN/WHIP/KART are not known callsigns
    assert m._extract_callsign_with_confidence("KILN (ABC)")[1] is False
    assert m._extract_callsign_with_confidence("WHIP (FOX)")[1] is False
    assert m._extract_callsign_with_confidence("KART (START)")[1] is False
    # ...but a real station whose callsign IS an English word is rescued.
    m2 = _matcher_with_callsigns("WAVE")
    assert m2._extract_callsign_with_confidence("WAVE (NBC)") == ("WAVE", True)


def test_leading_callsign_no_false_anchor_from_english_words():
    # Workflow-found damage modes must NOT occur when the leading token is not a
    # known callsign (empty allowlist -> Priority 3 never fires).
    m = _matcher()  # no DBs loaded -> _known_callsigns is empty
    # false 95-FLOOR: two unrelated "KILN (...)" names must not anchor
    assert m.match_all_streams("KILN (ABC) Pottery Hour", ["KILN (FOX) Ceramics Today"], {}, min_score=80) == []
    # false HARD-REJECT: a legitimate fuzzy match must survive
    assert m.match_all_streams("KART Racing", ["KART Racing Network"], {}, min_score=80)


def test_leading_callsign_paren_subchannel_stays_distinct():
    m = _matcher_with_callsigns("WPLG")
    # WPLG-DT (main ABC) normalizes to WPLG; WPLG-DT2 (a diginet) must NOT, so a
    # main-affiliate channel does not wrongly anchor to a subchannel feed.
    assert m._extract_callsign_with_confidence("WPLG-DT (ABC)") == ("WPLG-DT", True)
    assert m._extract_callsign_with_confidence("WPLG-DT2 (METVN)") == ("WPLG-DT2", True)
    assert m.normalize_callsign("WPLG-DT") == "WPLG"
    assert m.normalize_callsign("WPLG-DT2") != "WPLG"


def test_jesmann_format_now_anchors_to_channel():
    m = _matcher_with_callsigns("KSVI")
    # The real regression: "ABC - MT Billings (KSVI)" now anchors to "KSVI (ABC)".
    res = m.match_all_streams("ABC - MT Billings (KSVI)", ["KSVI (ABC)", "KSVI-DT (ABC)"], {}, min_score=80)
    assert res and res[0][1] >= 95
    # but a DIFFERENT station's callsign (not in the allowlist) is not anchored.
    assert m.match_all_streams("ABC - MT Billings (KSVI)", ["KXYZ (ABC)"], {}, min_score=80) == []
