"""The opening number for the public "EPGs Matched" badge.

The tally the plugin writes starts empty, so the badge would open at zero. The
operator asked for it to open at a number reconstructed from the CSV exports
already on disk, and this is what that reconstruction does and does not mean.

WHAT IT COUNTS. For each applied auto-match export, a data row carrying an EPG
id, because the apply step assigns every such row. For each Scan and Heal
export, a row whose status is HEALED, because only those are written. Preview
exports count nothing: a preview writes nothing.

WHY IT IS A RECONSTRUCTION AND NOT A MEASUREMENT. These files record what a run
DECIDED, not what Dispatcharr confirmed it wrote, and no count inside them can
be trusted either, because until 1.26.2481115 the line naming how many
assignments were written was itself wrong. So the opening figure is an estimate
built from row counts, and the record carrying it says so in its own action
field. Everything after it is measured.
"""
import importlib.util
import pathlib

import pytest

SCRIPT = (pathlib.Path(__file__).resolve().parent.parent
          / "scripts" / "update_epgs_matched_badge.py")


@pytest.fixture(scope="module")
def badge():
    spec = importlib.util.spec_from_file_location("badge_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


APPLIED = """# EPG Janitor v1 - Auto-Match Applied Report
# Generated: now
channel_id,channel_name,epg_data_id,reason
1,Alpha,1001,matched
2,Beta,,no match
3,Gamma,1003,matched
"""

HEAL = """# EPG Janitor v1 - Scan and Heal Applied Report
channel_id,channel_name,new_epg_id,status
1,Alpha,2001,HEALED
2,Beta,,NO_REPLACEMENT_FOUND
3,Gamma,2003,SKIPPED_LOW_CONFIDENCE
4,Delta,2004,HEALED
"""


def test_an_applied_auto_match_export_counts_rows_that_carry_an_epg_id(badge):
    assert badge.count_assignments("epg_janitor_automatch_applied_1.csv", APPLIED) == 2


def test_a_preview_export_counts_nothing(badge):
    """A preview writes no assignment, so counting it would inflate the total."""
    assert badge.count_assignments("epg_janitor_automatch_preview_1.csv", APPLIED) == 0


def test_a_heal_export_counts_only_the_rows_it_actually_healed(badge):
    assert badge.count_assignments("epg_janitor_heal_results_1.csv", HEAL) == 2


def test_an_export_from_another_plugin_counts_nothing(badge):
    """The export directory is shared with five other plugins."""
    assert badge.count_assignments("stream_mapparr_sorted_1.csv", APPLIED) == 0


def test_a_removal_or_scan_export_counts_nothing(badge):
    """Neither writes a guide assignment."""
    assert badge.count_assignments("epg_janitor_removal_1.csv", APPLIED) == 0
    assert badge.count_assignments("epg_janitor_results_1.csv", APPLIED) == 0


def test_the_comment_preamble_is_never_counted_as_data(badge):
    """Every export opens with commented lines; one counted as a row would add
    a phantom assignment to a public number."""
    only_comments = "# EPG Janitor v1 - Auto-Match Applied Report\n# Generated: now\n"
    assert badge.count_assignments("epg_janitor_automatch_applied_1.csv",
                                   only_comments) == 0


def test_an_export_with_no_epg_id_column_counts_nothing_rather_than_guessing(badge):
    text = "channel_id,channel_name\n1,Alpha\n"
    assert badge.count_assignments("epg_janitor_automatch_applied_1.csv", text) == 0


# --------------------------------------------------------------------------- #
# Summing the tally
# --------------------------------------------------------------------------- #
def test_the_total_adds_up_every_record(badge):
    lines = ['{"ts": 1, "action": "auto_match", "assignments_written": 5}',
             '{"ts": 2, "action": "heal", "assignments_written": 3}']
    assert badge.sum_ledger(lines) == 8


def test_a_damaged_line_is_skipped_rather_than_stopping_the_total(badge):
    """A half-written line must not make the badge stop moving."""
    lines = ['{"assignments_written": 5}', 'not json at all',
             '{"assignments_written": "seven"}', '', '{"assignments_written": 2}']
    assert badge.sum_ledger(lines) == 7


def test_an_empty_tally_totals_zero(badge):
    assert badge.sum_ledger([]) == 0


def test_a_heal_export_from_a_preview_run_counts_nothing(badge):
    """Measured on the live installation: all five Scan and Heal exports on disk
    are preview runs, whose rows carry REPLACEMENT_PREVIEW. Unlike the auto-match
    exports, the heal filename does not say whether the run applied anything, so
    the status column is the only thing that distinguishes them."""
    preview = ("channel_id,channel_name,new_epg_id,status\n"
               "1,Alpha,2001,REPLACEMENT_PREVIEW\n"
               "2,Beta,2002,REPLACEMENT_PREVIEW\n")
    assert badge.count_assignments("epg_janitor_heal_results_1.csv", preview) == 0
