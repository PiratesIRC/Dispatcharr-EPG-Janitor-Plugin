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


def test_wildcard_settings_stay_text_with_rows_and_name_lists(ef, flat):
    form = _by_id(_form(ef, flat))
    for fid in ("selected_groups", "ignore_groups", "epg_sources_to_match", "heal_fallback_sources"):
        assert form[fid]["type"] == "text"
        assert form[fid]["rows"] == 2
    assert "UK: Sports" in form["ignore_groups_names"]["description"]
    assert "guru-US" in form["epg_sources_to_match_names"]["description"]
    assert form["heal_fallback_sources_names"]["section"] == "_section_heal"


def test_long_help_is_split(ef, flat):
    form = _by_id(_form(ef, flat))
    assert form["allow_epg_without_programs"]["help_text"].endswith("Usually OFF.")
    assert form["allow_epg_without_programs_help_1"]["label"] == "When to turn it on"
    assert form["epg_sources_to_match_help_2"]["section"] == "_section_scope"


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
           "custom_aliases": json.dumps({"A": ["x", "y"]})}
    form = _by_id(_form(ef, flat, old))
    saved = {fid: form[fid]["default"] for fid in ef.NEW_ID_BY_OLD_ID.values()}
    out = ef.legacy_settings(saved)
    assert out["channel_profile_name"] == "All"
    assert out["watchdog_exclude_source_ids"] == "40"
    assert json.loads(out["custom_aliases"]) == {"A": ["x", "y"]}


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
