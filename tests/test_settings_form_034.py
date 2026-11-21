"""The Dispatcharr 0.34 settings form built by epgj_fields and Plugin.get_fields.

0.34 calls get_fields instead of reading fields; 0.33 and earlier read only the
flat fields list, which must not change. Three text settings are drawn under new
ids in the 0.34 form and written back into the old ids at run time.
"""
import json

import pytest
from conftest import build_bare_plugin

NEW_TYPES = {"section", "multiselect", "table", "file"}

PROFILES = ["All", "Favorites"]
SOURCES = [(46, "guru-USLocals"), (34, "guru-US"), (40, "epg.pw-GB")]
GROUPS = ["UK: Entertainment", "UK: Sports", "US: News"]


@pytest.fixture
def ef(plugin_module):
    import sys
    return sys.modules[plugin_module.__package__ + ".epgj_fields"]


@pytest.fixture
def flat(plugin_module):
    return build_bare_plugin(plugin_module).fields


def _form(ef, flat, settings=None):
    return ef.build_form(flat, settings or {}, PROFILES, SOURCES, GROUPS)


def _by_id(fields):
    return {f["id"]: f for f in fields}


def test_flat_form_has_no_034_types(flat):
    assert not [f["id"] for f in flat if f.get("type") in NEW_TYPES]
    assert not [f["id"] for f in flat if "section" in f or "rows" in f]


def test_every_flat_id_is_in_the_034_form_or_mapped(ef, flat):
    form_ids = set(_by_id(_form(ef, flat)))
    missing = [f["id"] for f in flat
               if f["id"] not in form_ids and ef.NEW_ID_BY_OLD_ID.get(f["id"]) not in form_ids]
    assert missing == []


def test_every_field_after_the_first_heading_has_a_declared_section(ef, flat):
    form = _form(ef, flat)
    sections = {f["id"] for f in form if f["type"] == "section"}
    assert "_section_scope" in sections and "_section_usage" in sections
    first = next(i for i, f in enumerate(form) if f["type"] == "section")
    loose = [f["id"] for f in form[first:] if f["type"] != "section" and f.get("section") not in sections]
    assert loose == []


def test_section_text_moves_to_an_about_field(ef, flat):
    form = _by_id(_form(ef, flat))
    assert form["_section_scope"]["type"] == "section"
    assert "description" not in form["_section_scope"]
    assert "region" in form["_section_scope_about"]["description"]
    assert form["_section_watchdog"]["collapsed"] is True
    assert form["_section_scope"]["collapsed"] is False


WILDCARD_IDS = {
    "selected_group_list": "selected_groups",
    "ignore_group_list": "ignore_groups",
    "epg_source_list": "epg_sources_to_match",
    "heal_fallback_source_list": "heal_fallback_sources",
}


def _values(field):
    return [o["value"] for o in field["options"]]


def test_wildcard_settings_are_pick_lists_under_new_ids(ef, flat):
    form = _by_id(_form(ef, flat))
    for new_id, old_id in WILDCARD_IDS.items():
        assert ef.LIST_SETTINGS[new_id] == old_id
        assert form[new_id]["type"] == "multiselect"
        assert form[new_id]["default"] == []
        assert old_id not in form
        assert old_id + "_names" not in form
        assert "Plugins page" in form[new_id]["help_text"]
    assert form["heal_fallback_source_list"]["section"] == "_section_heal"
    assert form["selected_group_list"]["section"] == "_section_scope"


def test_group_options_are_names_plus_prefix_patterns(ef, flat):
    form = _by_id(_form(ef, flat))
    values = _values(form["selected_group_list"])
    # Patterns first, then names, each sorted.
    assert values == ["UK:*", "US:*", "UK: Entertainment", "UK: Sports", "US: News"]
    labels = {o["value"]: o["label"] for o in form["ignore_group_list"]["options"]}
    assert labels["US:*"] == "US:* (every group whose name starts with US:)"
    assert labels["US: News"] == "US: News"


def test_source_options_are_names_plus_prefix_patterns(ef, flat):
    form = _by_id(_form(ef, flat))
    values = _values(form["epg_source_list"])
    assert values == ["epg.pw-*", "guru-*", "epg.pw-GB", "guru-US", "guru-USLocals"]
    assert _values(form["heal_fallback_source_list"]) == values


@pytest.mark.parametrize("name, pattern", [
    ("US: ABC", "US:*"),
    ("US-Family", "US-*"),
    ("UK | Sports", "UK |*"),
    ("epg.pw-GB", "epg.pw-*"),
    ("epgshare-sports-US", "epgshare-*"),
    ("24/7 Streams", None),           # no separator
    ("epgshare locals", None),        # no separator
    ("PPV Live Events - Main", None),  # the part before the separator has a space
    (": Leading", None),              # nothing before the separator
    ("[VIP]-Sports", None),           # [ ] would be a character class to fnmatch
    ("Averyverylongprefix: X", None),  # more than 12 characters before it
])
def test_prefix_pattern_rule(ef, name, pattern):
    assert ef.prefix_pattern(name) == pattern


def test_every_prefix_pattern_matches_the_name_it_came_from(plugin_module, ef):
    import sys
    wm = sys.modules[plugin_module.__package__ + ".wildcard_match"]
    names = GROUPS + [n for _, n in SOURCES] + ["US-Family", "UK | Sports", "A:"]
    for name in names:
        pattern = ef.prefix_pattern(name)
        if pattern:
            matched, _ = wm.expand_patterns([pattern], [name], ci_plain=False)
            assert matched == [name], (name, pattern)


def test_saved_text_values_become_defaults_and_options(ef, flat):
    form = _by_id(_form(ef, flat, {
        "selected_groups": "UK:*, Gone Group",
        "epg_sources_to_match": "*UK*, GURU-us",
    }))
    groups = form["selected_group_list"]
    assert groups["default"] == ["UK:*", "Gone Group"]
    labels = {o["value"]: o["label"] for o in groups["options"]}
    assert labels["Gone Group"] == "Gone Group (not found)"
    sources = form["epg_source_list"]
    # A literal source name is spelled as the database spells it (sources match
    # case-insensitively); a pattern is kept exactly as typed.
    assert sources["default"] == ["*UK*", "guru-US"]
    labels = {o["value"]: o["label"] for o in sources["options"]}
    assert labels["*UK*"] == "*UK* (wildcard pattern)"
    assert "GURU-us" not in labels


def test_group_names_keep_their_case(ef, flat):
    """Literal group names match case-sensitively, so a saved spelling that
    differs from the database is kept, not folded into the database name."""
    form = _by_id(_form(ef, flat, {"ignore_groups": "uk: sports"}))
    field = form["ignore_group_list"]
    assert field["default"] == ["uk: sports"]
    assert "uk: sports" in _values(field) and "UK: Sports" in _values(field)


def test_saved_pattern_spelling_wins_over_derived(ef, flat):
    form = _by_id(_form(ef, flat, {"selected_group_list": ["uk:*"]}))
    values = _values(form["selected_group_list"])
    assert "uk:*" in values and "UK:*" not in values


def test_saved_list_values_stay_wildcard_options(ef, flat):
    form = _by_id(_form(ef, flat, {"heal_fallback_source_list": ["old-*", "Old Source"]}))
    values = _values(form["heal_fallback_source_list"])
    assert "old-*" in values and "Old Source" in values


def test_wildcard_lists_write_back(ef):
    out = ef.legacy_settings({
        "selected_group_list": ["UK:*", "US: News"],
        "ignore_group_list": [],
        "epg_source_list": ["*UK*"],
        "heal_fallback_source_list": ["guru-*", "epg.pw-GB"],
        "selected_groups": "stale",
        "ignore_groups": "stale",
    })
    assert out["selected_groups"] == "UK:*, US: News"
    assert out["ignore_groups"] == ""
    assert out["epg_sources_to_match"] == "*UK*"
    assert out["heal_fallback_sources"] == "guru-*, epg.pw-GB"


def test_live_settings_survive_the_round_trip(ef, flat):
    """A saved prefix pattern and a saved contains pattern come back
    unchanged through the field default and the write-back."""
    old = {"selected_groups": "UK:*", "epg_sources_to_match": "*UK*",
           "ignore_groups": "", "heal_fallback_sources": ""}
    form = _by_id(_form(ef, flat, old))
    saved = {new_id: form[new_id]["default"] for new_id in WILDCARD_IDS}
    for new_id, value in saved.items():
        assert set(value) <= set(_values(form[new_id]))
    out = ef.legacy_settings(saved)
    for old_id, value in old.items():
        assert out[old_id] == value


def test_long_help_is_split(ef, flat):
    form = _by_id(_form(ef, flat))
    assert form["allow_epg_without_programs"]["help_text"].endswith("Usually OFF.")
    assert form["allow_epg_without_programs_help_1"]["label"] == "When to turn it on"
    assert form["epg_source_list_help_2"]["section"] == "_section_scope"


def test_profile_pick_list_default_from_old_text(ef, flat):
    form = _by_id(_form(ef, flat, {"channel_profile_name": "favorites, Gone"}))
    field = form["channel_profile_list"]
    assert field["type"] == "multiselect"
    # Spelled as the database spells it; a name no longer in the database is kept.
    assert field["default"] == ["Favorites", "Gone"]
    values = [o["value"] for o in field["options"]]
    assert values == ["All", "Favorites", "Gone"]


def test_saved_list_values_stay_options(ef, flat):
    form = _by_id(_form(ef, flat, {"channel_profile_list": ["Old Profile"],
                                    "watchdog_exclude_source_list": ["99"]}))
    assert "Old Profile" in [o["value"] for o in form["channel_profile_list"]["options"]]
    labels = {o["value"]: o["label"] for o in form["watchdog_exclude_source_list"]["options"]}
    assert labels["99"] == "99 - (not found)"


def test_exclude_source_pick_list(ef, flat):
    form = _by_id(_form(ef, flat, {"watchdog_exclude_source_ids": "39, 21, x, 39"}))
    field = form["watchdog_exclude_source_list"]
    assert field["default"] == ["39", "21"]
    labels = [o["label"] for o in field["options"]]
    assert labels[:3] == ["34 - guru-US", "40 - epg.pw-GB", "46 - guru-USLocals"]
    assert "39 - (not found)" in labels


def test_option_with_separator_is_left_out(ef):
    opts = ef._options(["A, B", "C"], extra=[])
    assert [o["value"] for o in opts] == ["C"]


def test_alias_table_built_from_json(ef, flat):
    text = json.dumps({"FOX News Channel": ["FOX NEWS HD", "FoxNews"]})
    form = _by_id(_form(ef, flat, {"custom_aliases": text}))
    assert "custom_aliases" not in form
    table = form["custom_aliases_rows"]
    assert table["type"] == "table" and table["label"] == ""
    assert table["default"] == [{"channel": "FOX News Channel", "aliases": "FOX NEWS HD, FoxNews"}]
    assert form["custom_aliases_rows_about"]["type"] == "info"


@pytest.mark.parametrize("text", ["{not json", "[1, 2]", '{"A": "B"}', '{"A": ["x, y"]}'])
def test_alias_text_box_kept_when_json_cannot_become_a_table(ef, flat, text):
    form = _by_id(_form(ef, flat, {"custom_aliases": text}))
    assert form["custom_aliases"]["type"] == "text"
    assert form["custom_aliases"]["rows"] == 6
    assert "custom_aliases_rows" not in form


def test_alias_round_trip(ef):
    data = {"FOX News Channel": ["FOX NEWS HD", "FoxNews"], "ESPN": []}
    rows = ef.alias_rows_from_json(json.dumps(data))
    assert json.loads(ef.alias_json_from_rows(rows)) == data


def test_alias_rows_merge_and_drop_blank(ef):
    rows = [{"channel": "A", "aliases": "x, y"}, {"channel": "", "aliases": "z"},
            {"channel": "A", "aliases": "y, w"}, "junk"]
    assert json.loads(ef.alias_json_from_rows(rows)) == {"A": ["x", "y", "w"]}
    assert ef.alias_json_from_rows([]) == ""


def test_legacy_settings_writes_back(ef):
    out = ef.legacy_settings({
        "channel_profile_list": ["All", "Favorites"],
        "watchdog_exclude_source_list": ["39", "21"],
        "custom_aliases_rows": [{"channel": "A", "aliases": "x"}],
        "channel_profile_name": "stale",
    })
    assert out["channel_profile_name"] == "All, Favorites"
    assert out["watchdog_exclude_source_ids"] == "39, 21"
    assert json.loads(out["custom_aliases"]) == {"A": ["x"]}


def test_legacy_settings_ignores_non_list_values(ef):
    settings = {"channel_profile_list": "All", "channel_profile_name": "Favorites"}
    assert ef.legacy_settings(settings)["channel_profile_name"] == "Favorites"


def test_default_written_back_equals_old_value(ef, flat):
    """An install that never saved the new fields: 0.34 stores the defaults,
    and writing them back must reproduce what the old settings meant."""
    old = {"channel_profile_name": "All", "watchdog_exclude_source_ids": "40",
           "custom_aliases": json.dumps({"A": ["x", "y"]}),
           "selected_groups": "UK:*", "epg_sources_to_match": "guru-US, *UK*"}
    form = _by_id(_form(ef, flat, old))
    saved = {fid: form[fid]["default"] for fid in ef.NEW_ID_BY_OLD_ID.values()}
    out = ef.legacy_settings(saved)
    assert out["channel_profile_name"] == "All"
    assert out["watchdog_exclude_source_ids"] == "40"
    assert json.loads(out["custom_aliases"]) == {"A": ["x", "y"]}
    assert out["selected_groups"] == "UK:*"
    assert out["epg_sources_to_match"] == "guru-US, *UK*"


def test_get_fields_builds_the_034_form(plugin_module, monkeypatch):
    inst = build_bare_plugin(plugin_module)
    monkeypatch.setattr(plugin_module.Plugin, "_form_names",
                        staticmethod(lambda: (PROFILES, SOURCES, GROUPS)))
    form = inst.get_fields({"settings": {}})
    assert any(f["type"] == "section" for f in form)
    assert inst._uses_pick_lists is True


def test_get_fields_falls_back_to_flat_on_error(plugin_module, monkeypatch, ef):
    inst = build_bare_plugin(plugin_module)

    def boom(*a, **k):
        raise RuntimeError("boom")

    monkeypatch.setattr(ef, "build_form", boom)
    form = inst.get_fields({"settings": {}})
    assert form == inst.fields
    assert inst._uses_pick_lists is False


def test_run_writes_back_only_after_get_fields(plugin_module):
    inst = build_bare_plugin(plugin_module)
    ctx = {"settings": {"channel_profile_list": ["All"], "channel_profile_name": "Favorites"}}
    assert inst._with_legacy_settings(ctx) is ctx
    inst._uses_pick_lists = True
    out = inst._with_legacy_settings(ctx)
    assert out["settings"]["channel_profile_name"] == "All"
    assert ctx["settings"]["channel_profile_name"] == "Favorites"


def test_help_texts_are_one_paragraph_without_em_dashes(ef, flat):
    for f in _form(ef, flat):
        for key in ("help_text", "description"):
            text = f.get(key) or ""
            assert "\n" not in text, f["id"]
            assert chr(0x2014) not in text, f["id"]
