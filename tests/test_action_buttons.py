"""Action button colour, and the two action lists agreeing with each other.

Measured 2026-09-05. Colour did not track consequence.

Apply Auto-Match was GREEN. It overwrites an existing EPG assignment whenever a
new match scores above the threshold, so a channel that was on the right guide
can come out of a run on a different one; the workspace notes record a preview
that wanted to move seventeen channels from East feeds to Pacific feeds. Clear
CSV Exports was RED, and it deletes export files and no channel data at all. So
the two extremes of the page were the wrong way round.

Remove EPG from Hidden Channels was ORANGE while the three other actions that
remove EPG assignments were red, so the same consequence carried two colours.

The rule adopted here, adapted from the sibling plugin Stream-Mapparr:

  red     can REMOVE a guide assignment the operator relies on
  orange  writes data or clears state, but removes no guide assignment
  green   runs an operation that writes no channel data
  blue    reads and reports, changing nothing

There is no cyan action, because this plugin sends nothing outward: it has no
email path, no bug reporter and no network code at all.

The two places actions are declared, Plugin.actions in plugin.py and the
"actions" list in plugin.json, were measured in agreement on 2026-09-05 across
all fifteen actions. Dispatcharr serves the plugin.py list for an enabled
plugin, so reading plugin.json alone can mislead; the sibling plugin
Stream-Mapparr had them drifting across twenty-two values. Tests below keep them
in step.
"""
import json
import os

import pytest

MANIFEST = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "EPG-Janitor", "plugin.json")

EXPECTED_COLOURS = {
    # red: can remove a guide assignment the operator relies on
    "apply_auto_match": "red",
    "remove_epg_assignments": "red",
    "remove_epg_from_hidden": "red",
    "remove_epg_by_regex": "red",
    "remove_all_epg_from_groups": "red",
    # orange: writes data or clears state, removes no guide assignment
    "scan_and_heal_apply": "orange",
    "add_bad_epg_suffix": "orange",
    "clear_csv_exports": "orange",
    # green: runs an operation, writes no channel data
    "export_results": "green",
    "watchdog_run_check_now": "green",
    # blue: reads and reports
    "validate_settings": "blue",
    "scan_missing_epg": "blue",
    "get_summary": "blue",
    "preview_auto_match": "blue",
    "scan_and_heal_dry_run": "blue",
}

RED = {aid for aid, colour in EXPECTED_COLOURS.items() if colour == "red"}


def _actions(plugin_module):
    """The list Dispatcharr actually serves for an enabled plugin."""
    return plugin_module.Plugin.actions


def _manifest_actions():
    with open(MANIFEST, encoding="utf-8") as handle:
        return json.load(handle)["actions"]


# --------------------------------------------------------------------------- #
# Every button is labelled and coloured
# --------------------------------------------------------------------------- #
def test_every_action_has_a_button_label(plugin_module):
    missing = [a["id"] for a in _actions(plugin_module) if not a.get("button_label")]
    assert missing == []


def test_every_action_has_a_button_colour(plugin_module):
    missing = [a["id"] for a in _actions(plugin_module) if not a.get("button_color")]
    assert missing == []


def test_the_expected_colours_cover_every_action_served(plugin_module):
    """A new action must be given a colour here, with a reason, not left to drift."""
    served = {a["id"] for a in _actions(plugin_module)}
    assert served == set(EXPECTED_COLOURS), served ^ set(EXPECTED_COLOURS)


# --------------------------------------------------------------------------- #
# Colour means one thing
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("action_id,colour", sorted(EXPECTED_COLOURS.items()))
def test_the_action_carries_the_colour_its_consequence_calls_for(
        plugin_module, action_id, colour):
    action = next((a for a in _actions(plugin_module) if a["id"] == action_id), None)
    assert action is not None, f"{action_id} is not served"
    assert action.get("button_color") == colour


def test_red_is_reserved_for_actions_that_can_remove_a_guide_assignment(plugin_module):
    """If red spreads to merely noisy actions it stops carrying any warning."""
    red = {a["id"] for a in _actions(plugin_module) if a.get("button_color") == "red"}
    assert red == RED


def test_every_red_action_also_asks_for_confirmation(plugin_module):
    """Colour is the glance; the dialog is the guard. A red button needs both."""
    for a in _actions(plugin_module):
        if a.get("button_color") == "red":
            assert a.get("confirm"), f"{a['id']} is red but has no confirm dialog"


def test_no_action_that_only_reads_asks_for_confirmation(plugin_module):
    """A dialog on an action that changes nothing teaches the operator to click through."""
    for a in _actions(plugin_module):
        if a.get("button_color") == "blue":
            assert not a.get("confirm"), f"{a['id']} only reads but asks for confirmation"


def test_the_button_variant_matches_the_colour(plugin_module):
    """Filled for the actions that write, outline for the ones that do not."""
    writes = {"red", "orange"}
    for a in _actions(plugin_module):
        expected = "filled" if a.get("button_color") in writes else "outline"
        assert a.get("button_variant") == expected, (a["id"], a.get("button_variant"))


# --------------------------------------------------------------------------- #
# The two declarations agree
# --------------------------------------------------------------------------- #
def test_the_manifest_and_the_served_list_hold_the_same_actions(plugin_module):
    served = sorted(a["id"] for a in _actions(plugin_module))
    manifest = sorted(a["id"] for a in _manifest_actions())
    assert served == manifest


@pytest.mark.parametrize(
    "key", ["button_label", "button_color", "button_variant", "confirm", "description"])
def test_the_manifest_and_the_served_list_agree_on_button_metadata(plugin_module, key):
    """plugin.json is what the Plugin Hub and a reader of the repository see;
    plugin.py is what Dispatcharr renders. A reviewer who checks the wrong one
    draws the wrong conclusion about the interface."""
    served = {a["id"]: a.get(key) for a in _actions(plugin_module)}
    manifest = {a["id"]: a.get(key) for a in _manifest_actions()}
    disagree = {k: (served.get(k), manifest.get(k))
                for k in served if served.get(k) != manifest.get(k)}
    assert disagree == {}, f"served vs manifest disagree on {key}: {disagree}"
