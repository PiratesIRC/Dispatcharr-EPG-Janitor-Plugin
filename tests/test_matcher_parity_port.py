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
