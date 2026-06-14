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
