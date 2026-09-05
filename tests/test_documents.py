"""The user guide describes the plugin that exists.

Measured 2026-09-05, checked against the declared fields and actions rather than
by eye, and the guide named several things that were not there:

  - Five watchdog settings were listed under names the form has never used
    ("Enable EPG Watchdog", "Horizon Threshold (hours)", "Log on Recovery").
    A reader searching the settings form for those finds nothing.
  - The watchdog button was called "Run EPG Watchdog Now"; the button says
    "Run Watchdog".
  - The export retention setting was absent entirely.
  - The Type column classified actions in a scheme unrelated to the colours the
    buttons carry, so the guide and the interface described the same action
    two different ways.

These tests compare the documents against the declarations, so a setting or an
action added later cannot stay undocumented and cannot be documented wrongly.
"""
import os

import pytest
from conftest import declared_settings

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE = os.path.join(REPO_ROOT, "docs", "USER-GUIDE.md")
README = os.path.join(REPO_ROOT, "README.md")
# Shipped inside the plugin directory, so it reaches every install.
SHIPPED_README = os.path.join(REPO_ROOT, "EPG-Janitor", "readme.txt")
CHANGELOG = os.path.join(REPO_ROOT, "docs", "CHANGELOG.md")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture(scope="module")
def guide():
    return _read(GUIDE)


def _settings(plugin_module):
    return declared_settings(plugin_module)


def test_every_setting_is_documented_by_the_label_the_form_shows(plugin_module, guide):
    missing = [f["label"] for f in _settings(plugin_module) if f["label"] not in guide]
    assert missing == [], f"settings absent from the user guide: {missing}"


def test_every_action_is_documented_by_the_label_on_its_button(plugin_module, guide):
    missing = [a["button_label"] for a in plugin_module.Plugin.actions
               if a["button_label"] not in guide]
    assert missing == [], f"buttons absent from the user guide: {missing}"


def test_the_guide_gives_each_action_the_colour_its_button_carries(plugin_module, guide):
    """The guide classified actions in a scheme of its own, which disagreed."""
    wrong = []
    for action in plugin_module.Plugin.actions:
        # The row of the actions table, which OPENS with the button label. Any
        # other table row that merely mentions the button is not that row.
        prefix = "| " + action["button_label"] + " |"
        line = next((line for line in guide.splitlines() if line.startswith(prefix)), None)
        assert line is not None, f"{action['id']} has no row in the actions table"
        # The colour column only. Checking the whole row passes when the row's
        # own description happens to contain the colour word, which is how a
        # deliberately wrong colour survived a mutation of this test.
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        colour_cell = cells[1] if len(cells) > 1 else ""
        if action["button_color"] not in colour_cell.split():
            wrong.append((action["id"], action["button_color"], colour_cell))
    assert wrong == [], wrong


def test_the_guide_explains_what_the_button_colours_mean(guide):
    """A colour column is only useful if the key is on the same page."""
    for colour in ("red", "orange", "green", "blue"):
        assert colour in guide


@pytest.mark.parametrize("path", [GUIDE, README, SHIPPED_README, CHANGELOG])
def test_no_user_facing_document_uses_an_em_or_en_dash(path):
    """Standing instruction for documents published from this workspace.

    The en dash is included because the writing gate counts both, and a range
    written "0-100" with an en dash passed an em-dash-only check here.
    """
    text = _read(path)
    dashes = (chr(0x2014), chr(0x2013))
    offenders = [i + 1 for i, line in enumerate(text.splitlines())
                 if any(d in line for d in dashes)]
    assert offenders == [], f"dash on lines {offenders} of {os.path.basename(path)}"


@pytest.mark.parametrize("stale", ["Run EPG Watchdog Now", "Watchdog: check interval",
                                   "Horizon Threshold", "Log on Recovery",
                                   "Enable EPG Watchdog"])
def test_the_guide_does_not_still_name_a_button_or_setting_that_was_renamed(guide, stale):
    """Checking that the NEW name is present cannot catch the old one surviving
    somewhere else in the document, which is what happened."""
    assert stale not in guide, f"the guide still names {stale!r}"


def test_the_colour_key_table_is_present_and_explains_each_colour(guide):
    """Asserting only that the four colour words appear somewhere is vacuous:
    they also appear in the Colour column of the actions table, so deleting the
    key table left the previous version of this test green."""
    for colour in ("red", "orange", "green", "blue"):
        assert f"| {colour} |" in guide, f"the colour key has no row for {colour}"


def test_the_guide_quotes_log_lines_the_plugin_actually_emits(guide):
    """An edit rewrote a quoted log literal into prose and made it wrong: the
    guide said "Excluded N sources" where the plugin logs EPG entries."""
    source = open(os.path.join(REPO_ROOT, "EPG-Janitor", "plugin.py"),
                  encoding="utf-8").read()
    assert "Excluded N sources from inactive EPG" not in guide
    assert "Excluded {excluded} EPG entr" in source, \
        "the log line changed; this test is comparing against a string that is gone"
