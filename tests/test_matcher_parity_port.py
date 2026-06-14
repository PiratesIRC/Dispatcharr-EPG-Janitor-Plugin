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
    m = _matcher()
    assert m.calculate_similarity("fox sports 1", "fox sports 2", min_ratio=0.95) == 0.0
    assert m.calculate_similarity("fox sports 1", "fox sports 2", min_ratio=0.90) == pytest.approx(11 / 12, abs=1e-9)


def test_bug026_pure_python_matches_rapidfuzz_when_available():
    import fuzzy_matcher as fm
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
    assert m.match_all_streams("Nickelodeon", ["Nickelodeon Teen"], {}) == []
    # Guard-level: subset guard rejects when the larger side adds a distinctive
    # (>=5 char) token the smaller lacks ("In Country Television" vs
    # "Country Music Television" -> the extra "music" is distinctive).
    assert not m._has_token_overlap(
        "in country television", "country music television", require_majority=True
    )


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


def test_digit_token_guard_numbered_vs_unnumbered():
    m = _matcher()
    # Query carries a digit token; candidate shares none -> skip even at high sim.
    assert m.match_all_streams("Eurosport 1 Extra", ["Eurosport Extra"], {}) == []


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
