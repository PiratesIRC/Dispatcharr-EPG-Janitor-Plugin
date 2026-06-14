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
