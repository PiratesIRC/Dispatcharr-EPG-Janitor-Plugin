"""Pinned EPG rules: an exact channel-name to guide map, re-applied after an M3U refresh.

Why it exists: M3U account 11 (ipt-hot) is a trending list whose streams change on every
refresh. Dispatcharr's auto channel sync creates its channels in channel group !Hot and resets
each channel's epg_data on every sync, matching a guide only by exact tvg_id, so hand-set
guides are lost every two hours. The feature re-applies an operator-written map after each
refresh of a pinned account.

Matching is EXACT after normalisation (leading rank stripped, quality, country and misc tags
removed, case folded). There is no fuzzy matching and no threshold: a near name does not match.

The pure rules live in pinned_epg.py and are tested directly. The plugin methods are tested
with their database seams replaced by in-memory fakes, because conftest.py stubs Django and
no query can run here.
"""
import importlib
import json
import logging
import sys
from unittest.mock import MagicMock

import pytest

from conftest import build_bare_plugin

# The six stream names the operator named. Each must normalise to the key shown.
EXAMPLE_KEYS = {
    "100 US Columbia, SC WLTX CBS 19 (A)": "columbia, sc wltx cbs 19",
    "64 US ID Investigation Discovery (A)": "id investigation discovery",
    "47 US: NBC (WIS) Columbia South Carolina": "nbc (wis) columbia south carolina",
    "94 US: OXYGEN TRUE CRIME": "oxygen true crime",
    "57 CA: CityTV Toronto (D)": "citytv toronto",
    "73 LAT: TELEMUNDO 47 NEW YORK HD": "telemundo 47 new york",
}


@pytest.fixture(scope="session")
def pinned(plugin_module):
    return importlib.import_module(plugin_module.__name__ + ".pinned_epg")


@pytest.fixture(scope="session")
def normalize(plugin_module):
    fuzzy = importlib.import_module(plugin_module.__name__ + ".fuzzy_matcher")
    matcher = fuzzy.FuzzyMatcher(plugin_dir=None)
    return lambda name: matcher.normalize_name(name, **{
        "ignore_quality": True, "ignore_regional": False,
        "ignore_geographic": True, "ignore_misc": True})


@pytest.fixture
def key_of(pinned, normalize):
    return lambda name: pinned.match_key(name, normalize)


# --------------------------------------------------------------------------- #
# Name matching
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("stream_name, expected", list(EXAMPLE_KEYS.items()))
def test_the_six_example_names_normalise_to_their_keys(key_of, stream_name, expected):
    assert key_of(stream_name) == expected


def test_a_rank_number_and_its_country_tag_do_not_change_the_key(key_of):
    assert key_of("100 US Columbia, SC WLTX CBS 19") == key_of("Columbia, SC WLTX CBS 19")


def test_quality_and_misc_tags_are_removed_from_both_sides(key_of):
    assert key_of("OXYGEN TRUE CRIME") == key_of("94 US: OXYGEN TRUE CRIME (A) HD")


def test_regional_markers_are_kept_so_east_and_west_feeds_stay_apart(key_of):
    assert key_of("HBO East") != key_of("HBO West")


def test_matching_is_exact_so_a_near_name_does_not_match(key_of):
    assert key_of("TELEMUNDO 47 NEW YORK") != key_of("TELEMUNDO 47 NEW YORK 2")
    assert key_of("Columbia, SC WLTX CBS 19") != key_of("Columbia SC WLTX CBS 19")
    assert key_of("ABC") != key_of("ABC News")


def test_keys_are_case_insensitive(key_of):
    assert key_of("oxygen true crime") == key_of("OXYGEN TRUE CRIME")


# --------------------------------------------------------------------------- #
# Map validation
# --------------------------------------------------------------------------- #

def _parse(pinned, normalize, text):
    return pinned.parse_map(text, normalize)


def test_an_empty_map_is_valid_and_has_no_rules(pinned, normalize):
    assert _parse(pinned, normalize, "") == {}
    assert _parse(pinned, normalize, "   \n") == {}


def test_a_valid_map_holds_each_rule_kind(pinned, normalize):
    rules = _parse(pinned, normalize, json.dumps({
        "NBC Columbia": 17,
        "CityTV Toronto": {"tvg_id": "CityTV.ca", "source": "guru-CA"},
        "Oxygen True Crime": {"epg_data_id": 42},
        "Telemundo 47": {"tvg_id": "Telemundo.us", "source": 5},
    }))
    by_name = {rule.channel: rule for rule in rules.values()}
    assert by_name["NBC Columbia"].epg_data_id == 17
    assert by_name["CityTV Toronto"].tvg_id == "CityTV.ca"
    assert by_name["CityTV Toronto"].source_name == "guru-CA"
    assert by_name["Oxygen True Crime"].epg_data_id == 42
    assert by_name["Telemundo 47"].source_id == 5


@pytest.mark.parametrize("text, fragment", [
    ("{not json", "not valid JSON"),
    ("[1, 2]", "JSON object"),
    ('{"": 5}', "empty"),
    ('{"ABC": true}', "rule"),
    ('{"ABC": 0}', "rule"),
    ('{"ABC": -3}', "rule"),
    ('{"ABC": "17"}', "rule"),
    ('{"ABC": {"epg_data_id": 1, "tvg_id": "x"}}', "both"),
    ('{"ABC": {"tvg_id": ""}}', "tvg_id"),
    ('{"ABC": {"tvg_id": "x", "colour": "red"}}', "colour"),
    ('{"ABC": {}}', "tvg_id or epg_data_id"),
])
def test_a_malformed_map_is_refused_with_a_reason(pinned, normalize, text, fragment):
    with pytest.raises(pinned.MapError) as caught:
        _parse(pinned, normalize, text)
    assert fragment in str(caught.value)


def test_two_names_that_match_the_same_key_are_refused(pinned, normalize):
    text = json.dumps({"ABC HD": 1, "ABC (A)": 2})
    with pytest.raises(pinned.MapError) as caught:
        _parse(pinned, normalize, text)
    assert "both match" in str(caught.value)


# --------------------------------------------------------------------------- #
# Event payload: allowlist only
# --------------------------------------------------------------------------- #

def test_a_button_press_is_not_an_event(pinned):
    assert pinned.event_account(None) is None
    assert pinned.event_account({}) is None


def test_only_account_name_is_read_from_an_m3u_refresh_payload(pinned):
    params = {"event": "m3u_refresh", "payload": {
        "account_name": "  ipt-hot  ",
        "stream_url": "http://user:secret@provider.example/live/u/p/1.ts",
        "channel_url": "http://provider.example/u/p",
        "provider_name": "Provider",
    }}
    assert pinned.event_account(params) == "ipt-hot"


def test_a_non_string_account_name_reads_as_no_account(pinned):
    assert pinned.event_account({"event": "m3u_refresh", "payload": {"account_name": 7}}) == ""
    assert pinned.event_account({"event": "m3u_refresh", "payload": None}) == ""


def test_the_account_name_is_length_capped(pinned):
    params = {"event": "m3u_refresh", "payload": {"account_name": "x" * 5000}}
    assert len(pinned.event_account(params)) <= pinned.ACCOUNT_NAME_LIMIT


def test_another_event_never_applies(pinned):
    assert pinned.event_account({"event": "channel_error", "payload": {"account_name": "ipt-hot"}}) == ""


def test_trigger_accounts_match_exactly_after_strip_and_case_fold(pinned):
    assert pinned.is_trigger_account("IPT-Hot", "ipt-hot, other")
    assert pinned.is_trigger_account("other", "ipt-hot,\nother")
    assert not pinned.is_trigger_account("ipt", "ipt-hot")
    assert not pinned.is_trigger_account("", "ipt-hot")
    assert not pinned.is_trigger_account("ipt-hot", "")


# --------------------------------------------------------------------------- #
# Plugin methods, with the database seams replaced by fakes
# --------------------------------------------------------------------------- #

@pytest.fixture
def plugin_impl(plugin_module):
    return sys.modules[plugin_module.Plugin.__module__]


class Fakes:
    """Records every write and stands in for the three database seams."""

    def __init__(self, channels, epg_rows):
        self.channels = channels          # list of dicts: id, name, epg_id, epg_label
        self.epg_rows = epg_rows          # list of dicts: id, tvg_id, source_id, source_name
        self.writes = []

    def scope(self, settings, logger):
        return list(self.channels)

    def epg_lookup(self, rules):
        return list(self.epg_rows)

    def write(self, associations, logger):
        self.writes.extend(associations)
        return {"channels_updated": len(associations), "programs_queued": 0}


STANDARD_EPG = (
    {"id": 17, "tvg_id": "WLTX", "source_id": 1, "source_name": "guru"},
    {"id": 3, "tvg_id": "CityTV.ca", "source_id": 2, "source_name": "guru-CA"},
)


@pytest.fixture
def fakes(bare_plugin, monkeypatch):
    def install(channels, epg_rows=STANDARD_EPG):
        seam = Fakes(channels, list(epg_rows))
        monkeypatch.setattr(bare_plugin, "_pinned_channel_scope", seam.scope)
        monkeypatch.setattr(bare_plugin, "_pinned_epg_lookup", seam.epg_lookup)
        monkeypatch.setattr(bare_plugin, "_batch_set_epg", seam.write)
        return seam
    return install


@pytest.fixture
def inst(bare_plugin, plugin_impl):
    bare_plugin.fuzzy_matcher = plugin_impl.FuzzyMatcher(plugin_dir=None)
    bare_plugin._report_usage = MagicMock()  # run() reports usage in a finally; never send
    return bare_plugin


def _settings(groups="!Hot", accounts="ipt-hot", pinned_map=None):
    return {
        "pinned_epg_groups": groups,
        "pinned_epg_accounts": accounts,
        "pinned_epg_map": json.dumps(pinned_map if pinned_map is not None else {
            "Columbia, SC WLTX CBS 19": 17,
            "CityTV Toronto": {"tvg_id": "CityTV.ca", "source": "guru-CA"},
        }),
    }


def _channel(cid, name, epg_id=None, label=""):
    return {"id": cid, "name": name, "epg_id": epg_id, "epg_label": label}


def test_apply_writes_only_mapped_channels_in_scope(inst, fakes):
    seam = fakes([
        _channel(1, "100 US Columbia, SC WLTX CBS 19 (A)"),
        _channel(2, "Some Other Channel"),
    ])
    result = inst.apply_pinned_epg_action(_settings(), MagicMock())
    assert result["status"] == "success"
    assert seam.writes == [{"channel_id": 1, "epg_data_id": 17}]


def test_apply_skips_a_channel_already_on_the_target_guide(inst, fakes):
    seam = fakes([_channel(1, "Columbia, SC WLTX CBS 19", epg_id=17, label="x")])
    inst.apply_pinned_epg_action(_settings(), MagicMock())
    assert seam.writes == []


def test_apply_never_clears_an_assignment(inst, fakes):
    seam = fakes([_channel(1, "Unrelated", epg_id=99, label="keep")])
    inst.apply_pinned_epg_action(_settings(), MagicMock())
    assert seam.writes == []
    assert all(w["epg_data_id"] is not None for w in seam.writes)


def test_a_missing_guide_is_reported_and_the_channel_is_left_alone(inst, fakes):
    seam = fakes([_channel(1, "CityTV Toronto", epg_id=5, label="old")], epg_rows=[])
    result = inst.apply_pinned_epg_action(_settings(), MagicMock())
    assert seam.writes == []
    assert "missing guides 1" in result["message"]


def test_an_ambiguous_tvg_id_without_a_source_is_refused(inst, fakes):
    seam = fakes([_channel(1, "Telemundo 47")],
                 epg_rows=[{"id": 8, "tvg_id": "T.us", "source_id": 1, "source_name": "a"},
                           {"id": 9, "tvg_id": "T.us", "source_id": 2, "source_name": "b"}])
    settings = _settings(pinned_map={"Telemundo 47": {"tvg_id": "T.us"}})
    result = inst.apply_pinned_epg_action(settings, MagicMock())
    assert seam.writes == []
    assert "ambiguous guides 1" in result["message"]


def test_an_ambiguous_tvg_id_with_a_source_resolves(inst, fakes):
    seam = fakes([_channel(1, "Telemundo 47")],
                 epg_rows=[{"id": 8, "tvg_id": "T.us", "source_id": 1, "source_name": "a"},
                           {"id": 9, "tvg_id": "T.us", "source_id": 2, "source_name": "b"}])
    settings = _settings(pinned_map={"Telemundo 47": {"tvg_id": "T.us", "source": "b"}})
    inst.apply_pinned_epg_action(settings, MagicMock())
    assert seam.writes == [{"channel_id": 1, "epg_data_id": 9}]


def test_an_epg_id_that_does_not_exist_is_reported(inst, fakes):
    seam = fakes([_channel(1, "Columbia, SC WLTX CBS 19")], epg_rows=[])
    result = inst.apply_pinned_epg_action(_settings(), MagicMock())
    assert seam.writes == []
    assert "missing guides 1" in result["message"]


def test_the_summary_counts_each_outcome(inst, fakes):
    fakes([
        _channel(1, "Columbia, SC WLTX CBS 19"),
        _channel(2, "CityTV Toronto (D)", epg_id=3),
        _channel(3, "Not Pinned"),
    ], epg_rows=[
        {"id": 17, "tvg_id": "WLTX", "source_id": 1, "source_name": "guru"},
        {"id": 3, "tvg_id": "CityTV.ca", "source_id": 2, "source_name": "guru-CA"},
    ])
    result = inst.apply_pinned_epg_action(_settings(), MagicMock())
    assert "applied 1" in result["message"]
    assert "already correct 1" in result["message"]
    assert "unmatched 1" in result["message"]


def test_the_real_scope_builder_passes_the_pinned_groups_to_the_existing_parser(
        inst, plugin_impl, monkeypatch):
    seen = []

    def fake_filter(settings, logger, query):
        seen.append(settings["selected_groups"])
        return query, "", ""

    monkeypatch.setattr(inst, "_validate_and_filter_groups", fake_filter)
    monkeypatch.setattr(plugin_impl, "Channel", MagicMock())
    inst._pinned_channel_scope(_settings(groups="!Hot*"), MagicMock())
    assert seen == ["!Hot*"]


def test_no_pinned_groups_is_refused_with_both_keys(inst, fakes):
    fakes([_channel(1, "Columbia, SC WLTX CBS 19")])
    result = inst.apply_pinned_epg_action(_settings(groups=""), MagicMock())
    assert result["status"] == "error"
    assert result["message"] and result["error"] == result["message"]


def test_a_malformed_map_is_refused_with_both_keys(inst, fakes):
    fakes([_channel(1, "Columbia, SC WLTX CBS 19")])
    settings = _settings()
    settings["pinned_epg_map"] = "{oops"
    result = inst.apply_pinned_epg_action(settings, MagicMock())
    assert result["status"] == "error"
    assert result["message"] and result["error"] == result["message"]


def test_the_preview_writes_nothing(inst, fakes):
    seam = fakes([_channel(1, "Columbia, SC WLTX CBS 19")], epg_rows=[])
    result = inst.preview_pinned_epg_action(_settings(), MagicMock())
    assert seam.writes == []
    assert result["status"] in ("success", "ok")
    assert result["message"]


def test_the_preview_writes_a_csv_to_the_exports_folder(inst, fakes, plugin_impl):
    fakes([_channel(1, "Columbia, SC WLTX CBS 19")],
          epg_rows=[{"id": 17, "tvg_id": "WLTX", "source_id": 1, "source_name": "guru"}])
    result = inst.preview_pinned_epg_action(_settings(), MagicMock())
    path = result.get("file_path")
    assert path and path.startswith(str(plugin_impl.Plugin.EXPORTS_DIR))
    text = open(path, encoding="utf-8").read()
    assert "channel" in text and "outcome" in text
    assert "Columbia, SC WLTX CBS 19" in text
    assert "apply" in text
    text.encode("ascii")  # the preamble is plain ASCII


# --------------------------------------------------------------------------- #
# Event runs and button runs through Plugin.run
# --------------------------------------------------------------------------- #

def _event(account):
    return {"event": "m3u_refresh",
            "payload": {"account_name": account, "stream_url": "http://u:pw@p.example/x.ts"}}


def test_an_event_for_a_non_pinned_account_does_no_work(inst, plugin_impl, monkeypatch, caplog):
    ran = []
    monkeypatch.setattr(inst, "_run_action", lambda *a, **k: ran.append(a))
    channel_model = MagicMock()
    epg_model = MagicMock()
    schedule = MagicMock()
    usage = MagicMock()
    monkeypatch.setattr(plugin_impl, "Channel", channel_model)
    monkeypatch.setattr(plugin_impl, "EPGData", epg_model)
    monkeypatch.setattr(plugin_impl, "watchdog_sync_schedule", schedule)
    monkeypatch.setattr(inst, "_report_usage", usage)
    with caplog.at_level(logging.DEBUG):
        result = inst.run("apply_pinned_epg", _event("some-other-account"),
                          {"settings": _settings(accounts="ipt-hot"), "logger": MagicMock()})
    assert ran == []
    assert result["status"] == "ok"
    assert channel_model.mock_calls == []
    assert epg_model.mock_calls == []
    assert schedule.call_count == 0
    usage.assert_not_called()
    assert "pw" not in caplog.text


def test_an_event_for_a_pinned_account_applies(inst, monkeypatch):
    calls = []
    monkeypatch.setattr(inst, "_run_action", lambda action, params, context: calls.append(action))
    inst.run("apply_pinned_epg", _event("ipt-hot"),
             {"settings": _settings(accounts="ipt-hot"), "logger": MagicMock()})
    assert calls == ["apply_pinned_epg"]


def test_an_event_with_no_settings_in_context_does_nothing(inst, monkeypatch):
    ran = []
    monkeypatch.setattr(inst, "_run_action", lambda *a: ran.append(a))
    inst.run("apply_pinned_epg", _event("ipt-hot"), {"logger": MagicMock()})
    assert ran == []


def test_a_button_run_applies_whatever_the_account(inst, monkeypatch):
    calls = []
    monkeypatch.setattr(inst, "_run_action", lambda action, params, context: calls.append(action))
    inst.run("apply_pinned_epg", {}, {"settings": _settings(accounts=""), "logger": MagicMock()})
    assert calls == ["apply_pinned_epg"]


def test_a_button_run_with_no_params_applies(inst, monkeypatch):
    calls = []
    monkeypatch.setattr(inst, "_run_action", lambda action, params, context: calls.append(action))
    inst.run("apply_pinned_epg", None, {"settings": _settings(accounts=""), "logger": MagicMock()})
    assert calls == ["apply_pinned_epg"]


# --------------------------------------------------------------------------- #
# Declarations: manifest and class agree, settings sit in their section
# --------------------------------------------------------------------------- #

def test_the_apply_action_declares_the_refresh_event_in_both_places(manifest, plugin_module):
    from_manifest = next(a for a in manifest["actions"] if a["id"] == "apply_pinned_epg")
    from_class = next(a for a in plugin_module.Plugin.actions if a["id"] == "apply_pinned_epg")
    assert from_manifest.get("events") == ["m3u_refresh"]
    assert from_class.get("events") == ["m3u_refresh"]


def test_the_preview_is_blue_and_the_apply_is_orange(plugin_module):
    by_id = {a["id"]: a for a in plugin_module.Plugin.actions}
    assert by_id["preview_pinned_epg"]["button_color"] == "blue"
    assert by_id["apply_pinned_epg"]["button_color"] == "orange"
    assert by_id["apply_pinned_epg"]["button_label"]
    assert by_id["preview_pinned_epg"]["button_label"]


def test_the_pinned_settings_sit_under_their_own_heading(plugin_module):
    ids = [f.get("id") for f in build_bare_plugin(plugin_module).fields]
    start = ids.index("_section_pinned")
    under = []
    for fid in ids[start + 1:]:
        if str(fid).startswith("_section_"):
            break
        under.append(fid)
    assert under == ["pinned_epg_groups", "pinned_epg_accounts", "pinned_epg_map"]


def test_the_pinned_settings_appear_in_the_034_form_under_the_section(plugin_module):
    epgj = importlib.import_module(plugin_module.__name__ + ".epgj_fields")
    flat = build_bare_plugin(plugin_module).fields
    form = epgj.build_form(flat, {}, (), (), ())
    section = [f for f in form if f.get("section") == "_section_pinned"]
    assert {f["id"] for f in section if f.get("type") == "text"} == {
        "pinned_epg_groups", "pinned_epg_accounts", "pinned_epg_map"}


def test_the_manifest_declares_the_pinned_settings_like_the_class(manifest, plugin_module):
    class_by_id = {f["id"]: f for f in build_bare_plugin(plugin_module).fields}
    manifest_by_id = {f["id"]: f for f in manifest["fields"]}
    for fid in ("_section_pinned", "pinned_epg_groups", "pinned_epg_accounts", "pinned_epg_map"):
        assert fid in manifest_by_id
        assert manifest_by_id[fid] == class_by_id[fid]
