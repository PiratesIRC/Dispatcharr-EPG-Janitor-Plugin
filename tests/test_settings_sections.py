"""The settings form is divided into sections, and every setting sits under one.

Measured 2026-09-05 against the field list the plugin actually serves. The form
opened with the twelve channel-database toggles (Enable US, Enable UK, and so
on) ABOVE every heading, because the `fields` property builds them first and
then appends the declared list. So the first thing an operator saw was twelve
country checkboxes with no heading and no explanation, and the Quick Start panel
sat at position 12, below them.

Section headings are fields of type "info" whose id starts with _section_. They
are declared in Plugin._base_fields in plugin.py and mirrored in plugin.json.
The channel-database toggles are built at runtime, so putting them inside a
section is a change to the `fields` property rather than to a list literal.

These tests lock the section boundaries, so a setting added later cannot
silently land under the wrong heading, and they lock the rules this workspace
has for text the plugin shows the operator.
"""
import pytest

# Each section heading and the field id that must come directly after it.
# Locking the BOUNDARY rather than the full membership means adding a setting
# inside a section needs no test change, while moving a boundary does.
SECTION_BOUNDARIES = [
    ("_section_quickstart", "_section_databases"),
    ("_section_databases", "enable_db_AU"),
    ("_section_scope", "channel_profile_name"),
    ("_section_automatch", "automatch_confidence_threshold"),
    ("_section_heal", "heal_fallback_sources"),
    ("_section_cleanup", "epg_regex_to_remove"),
    ("_section_normalization", "ignore_quality_tags"),
    ("_section_aliases", "custom_aliases"),
    ("_section_watchdog", "watchdog_enabled"),
    ("_section_housekeeping", "csv_retention_days"),
]


def _fields(plugin_module):
    """The field list Dispatcharr serves, built without running __init__.

    __init__ writes progress state to a container path, so it must not run here.
    """
    P = plugin_module.Plugin
    inst = P.__new__(P)
    inst.version = "test"
    return inst.fields


def _ids(plugin_module):
    return [f.get("id") for f in _fields(plugin_module)]


def _section_ids(plugin_module):
    return [f for f in _ids(plugin_module) if str(f).startswith("_section_")]


def _fields_under(plugin_module, section_id):
    """The field ids between section_id and the next section heading."""
    ids = _ids(plugin_module)
    out = []
    for fid in ids[ids.index(section_id) + 1:]:
        if str(fid).startswith("_section_"):
            break
        out.append(fid)
    return out


# --------------------------------------------------------------------------- #
# The sections exist and are in order
# --------------------------------------------------------------------------- #
def test_every_expected_section_heading_is_served(plugin_module):
    served = _section_ids(plugin_module)
    missing = [name for name, _first in SECTION_BOUNDARIES if name not in served]
    assert not missing, f"missing section heading(s): {missing}"


def test_the_sections_appear_in_the_expected_order(plugin_module):
    assert _section_ids(plugin_module) == [name for name, _f in SECTION_BOUNDARIES]


@pytest.mark.parametrize("section_id,first_field", SECTION_BOUNDARIES)
def test_each_section_is_followed_by_the_field_that_opens_it(
        plugin_module, section_id, first_field):
    ids = _ids(plugin_module)
    assert section_id in ids, f"{section_id} is not served at all"
    assert ids[ids.index(section_id) + 1] == first_field


# --------------------------------------------------------------------------- #
# The defect that prompted this
# --------------------------------------------------------------------------- #
def test_no_setting_sits_above_the_first_section_heading(plugin_module):
    """The twelve channel-database toggles used to open the form, unlabelled."""
    ids = _ids(plugin_module)
    first_section = next(i for i, f in enumerate(ids)
                         if str(f).startswith("_section_"))
    assert first_section == 0, f"{ids[:first_section]} appear before any heading"


def test_every_channel_database_toggle_sits_under_the_database_heading(plugin_module):
    under = set(_fields_under(plugin_module, "_section_databases"))
    toggles = {f for f in _ids(plugin_module) if str(f).startswith("enable_db_")}
    assert toggles, "no channel-database toggles were built, so this proves nothing"
    assert toggles <= under, f"toggles outside the database section: {toggles - under}"


def test_the_database_section_holds_only_database_fields(plugin_module):
    under = _fields_under(plugin_module, "_section_databases")
    strays = [f for f in under if not str(f).startswith(("enable_db_", "channel_database"))]
    assert not strays, f"unrelated settings under the database heading: {strays}"


# --------------------------------------------------------------------------- #
# Rules for text this plugin shows the operator
# --------------------------------------------------------------------------- #
def _section_fields(plugin_module):
    return [f for f in _fields(plugin_module)
            if str(f.get("id", "")).startswith("_section_")]


def test_every_section_heading_has_a_body(plugin_module):
    """A heading with no body says only its own name, which the label already does."""
    bare = [f["id"] for f in _section_fields(plugin_module)
            if not (f.get("description") or "").strip()]
    assert not bare, bare


def test_no_section_body_contains_a_line_break(plugin_module):
    """An info panel body is one flowing paragraph; line breaks are not safe there."""
    offenders = [f["id"] for f in _section_fields(plugin_module)
                 if "\n" in (f.get("description") or "")]
    assert not offenders, offenders


def test_no_setting_copy_uses_an_em_or_en_dash(plugin_module):
    """Standing instruction: no em or en dashes in copy the plugin shows."""
    dashes = (chr(0x2014), chr(0x2013))
    offenders = [f["id"] for f in _fields(plugin_module)
                 if any(d in (f.get("label") or "") + (f.get("description") or "")
                        + (f.get("help_text") or "") for d in dashes)]
    assert not offenders, offenders


def test_section_headings_are_information_panels_that_store_nothing(plugin_module):
    """A heading must never become a stored setting: Dispatcharr never prunes one."""
    for f in _section_fields(plugin_module):
        assert f.get("type") == "info", f["id"]
        assert "default" not in f, f["id"]


def test_no_operator_facing_copy_contains_a_double_encoded_character(plugin_module):
    """The marker left when text is written through a shell that mangles it.

    A tick character passed through a here-document during this pass arrived in
    the watchdog section body as three characters, and it is invisible in a
    diff unless you look for it. U+FFFD does not appear, because the result is
    valid UTF-8 for the wrong characters.
    """
    # Built from codepoints on purpose. Typing these characters into this file
    # is exactly the transit that mangles them, and a mangled marker matches
    # nothing while the test still passes.
    markers = (chr(0xC3), chr(0xE2), chr(0xC2))
    offenders = []
    for f in _fields(plugin_module):
        text = (f.get("label") or "") + (f.get("description") or "") + \
               (f.get("help_text") or "")
        if any(marker in text for marker in markers):
            offenders.append(f.get("id"))
    assert not offenders, offenders


def test_no_setting_label_uses_a_prefix_its_own_section_already_states(plugin_module):
    """The five watchdog settings were labelled "Watchdog: ...", under a heading
    that already says EPG Freshness Watchdog."""
    labels = [f.get("label", "") for f in _fields(plugin_module)
              if not str(f.get("id", "")).startswith("_section_")]
    offenders = [label for label in labels if label.startswith("Watchdog:")]
    assert not offenders, offenders
