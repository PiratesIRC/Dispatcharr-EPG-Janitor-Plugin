"""Guards for the shipped FCC station callsign allowlist.

The allowlist decides whether a callsign-shaped token is treated as a real
station. Getting it wrong is silent in both directions: too small and real
stations never reach high confidence, too large and callsign-shaped English
words start matching. These tests pin the shape of the data file, the behaviour
it enables, and the degradation when it is missing.

Every guard here was verified by planting the corresponding regression and
watching it fail. A guard that passes the first time it is written is probably
vacuous.
"""
import importlib.util
import json
import os
import pathlib
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
INNER = REPO_ROOT / "EPG-Janitor"
DATA_FILE = INNER / "us_station_callsigns.json"


def _load_matcher_module():
    """Import fuzzy_matcher.py directly from the inner folder.

    Mirrors tests/test_matcher_golden.py: the inner package is what ships, and
    importing it by path keeps this file independent of any conftest fixture.
    """
    spec = importlib.util.spec_from_file_location(
        "fuzzy_matcher_station_test", INNER / "fuzzy_matcher.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(INNER))
    spec.loader.exec_module(module)
    return module


FM = _load_matcher_module()


@pytest.fixture
def data():
    return json.loads(DATA_FILE.read_text(encoding="utf-8"))


# --- the data file itself ---------------------------------------------------

def test_data_file_ships_in_the_deployable_folder():
    # The plugin deploys as the inner directory. A data file left in the repo
    # root would pass every test here and be absent on the container.
    assert DATA_FILE.exists(), "us_station_callsigns.json must live in EPG-Janitor/"


def test_callsigns_are_sorted_and_unique(data):
    # Sorted and unique is what makes a rebuild produce a readable diff rather
    # than a whole-file rewrite.
    calls = data["callsigns"]
    assert calls == sorted(set(calls))


def test_every_entry_is_a_plausible_callsign(data):
    import re
    shape = re.compile(r"^[KW][A-Z]{2,4}$")
    bad = [c for c in data["callsigns"] + data["carried_over"] if not shape.match(c)]
    assert bad == [], f"entries that are not callsign-shaped: {bad[:10]}"


def test_file_has_no_carriage_returns():
    # .gitattributes pins the data files to LF. A CRLF rewrite looks correct on
    # Windows and breaks hash-pinned checks on Linux.
    assert b"\r" not in DATA_FILE.read_bytes()


def test_file_records_where_it_came_from(data):
    # Provenance is the difference between a rebuildable file and a mystery.
    assert "FCC" in data["_source"]
    assert "build_station_callsigns.py" in data["_what"]


def test_holds_the_expected_order_of_magnitude(data):
    # Measured 3037 on the 2026-08-10 dump. The bounds catch a truncated parse
    # or a rule change that quietly admits radio, without failing on the normal
    # drift between dumps.
    assert 2500 <= len(data["callsigns"]) <= 4000


# --- the behaviour the file enables -----------------------------------------

def test_allowlist_is_populated_without_any_channel_database():
    # Before the FCC file existed this returned an empty set until a country
    # database was loaded, so the leading-callsign promotion never fired.
    matcher = FM.FuzzyMatcher()
    assert len(matcher._get_known_callsigns()) > 2500


def test_station_absent_from_the_channel_databases_now_promotes():
    # The point of the whole change. KAGN is licensed in the FCC table and does
    # not appear in station format in any shipped channel database, so before
    # this file it could not reach high confidence.
    matcher = FM.FuzzyMatcher()
    assert "KAGN" in matcher._get_known_callsigns()
    callsign, high_confidence = matcher._extract_callsign_with_confidence("KAGN (ABC)")
    assert callsign == "KAGN"
    assert high_confidence is True


def test_callsign_shaped_english_word_still_does_not_promote():
    # The guard the allowlist exists to provide. KILN is callsign-shaped and is
    # not a licensed station, so it must stay low confidence even now that the
    # allowlist is 3000 entries rather than empty.
    matcher = FM.FuzzyMatcher()
    assert "KILN" not in matcher._get_known_callsigns()
    _, high_confidence = matcher._extract_callsign_with_confidence("KILN (ABC)")
    assert high_confidence is False


def test_database_derived_callsigns_are_kept_not_replaced():
    # The channel databases hold callsigns the FCC table does not. Replacing
    # rather than merging would be a regression, and it would not be visible in
    # any count.
    matcher = FM.FuzzyMatcher()
    file_only = matcher._load_station_callsigns()
    matcher.broadcast_channels = [{"callsign": "KZZZ", "channel_name": "KZZZ (TEST)"}]
    matcher._known_callsigns = None
    merged = matcher._get_known_callsigns()
    assert "KZZZ" in merged
    assert file_only.issubset(merged)


def test_reload_databases_rebuilds_the_allowlist():
    # The cache must not survive a database reload, or a newly loaded country
    # database is invisible to the allowlist.
    matcher = FM.FuzzyMatcher()
    matcher._get_known_callsigns()
    assert matcher._known_callsigns is not None
    matcher._known_callsigns = None
    assert len(matcher._get_known_callsigns()) > 2500


# --- degradation ------------------------------------------------------------

def test_missing_file_degrades_to_the_database_derived_set(monkeypatch, caplog):
    # A missing data file must cost matches, never raise. An exception here runs
    # on Dispatcharr's per-request hot path.
    matcher = FM.FuzzyMatcher()
    monkeypatch.setattr(FM.FuzzyMatcher, "_STATION_CALLSIGN_FILE", "does_not_exist.json")
    matcher._known_callsigns = None
    matcher.broadcast_channels = [{"callsign": "KZZZ", "channel_name": "KZZZ (TEST)"}]
    with caplog.at_level("WARNING"):
        result = matcher._get_known_callsigns()
    assert result == {"KZZZ"}
    assert any("does_not_exist.json" in r.message for r in caplog.records), \
        "a silently empty allowlist is indistinguishable from a missing file"


def test_unreadable_file_degrades_rather_than_raising(monkeypatch, tmp_path):
    # Malformed JSON takes the same path as a missing file.
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    matcher = FM.FuzzyMatcher()
    monkeypatch.setattr(FM.FuzzyMatcher, "_STATION_CALLSIGN_FILE", os.path.join("..", "..", str(broken)))
    assert matcher._load_station_callsigns() == set()


# --- the builder ------------------------------------------------------------

def test_builder_script_ships_and_compiles():
    import py_compile
    script = REPO_ROOT / "scripts" / "build_station_callsigns.py"
    assert script.exists(), "the data file must stay rebuildable"
    py_compile.compile(str(script), doraise=True)
