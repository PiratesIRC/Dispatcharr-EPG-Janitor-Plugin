"""The commented preamble at the top of every CSV this plugin writes.

Reviewed 2026-09-05. Nothing in the preamble was FALSE: every key it reads is a
key this plugin declares, checked mechanically against Plugin._base_fields, and
the plugin has no scheduled export, so no run can misdescribe itself as manual.
The sibling plugin Stream-Mapparr had both of those defects; this one does not.

What was wrong was what the file failed to say, and how it said the rest.

  - It never said what the file IS. A person opening it in a spreadsheet sees
    twenty commented lines and no statement that they are a preamble to skip.
  - It said what the run was CONFIGURED to do and never what it DID, beyond a
    count of channels processed.
  - Booleans reached the reader as Python True, and as the bare string "true"
    when Dispatcharr had stored the value as a string.
  - A setting left at its default printed "(not set)", which reads as "no value
    was used" when in fact the default was used and did affect the run.
  - Thresholds printed as a bare number. "95" does not say out of what, nor
    whether higher is stricter.
  - Four settings were labelled differently from the interface, so a reader
    could not find the setting the line was talking about.
  - Two of the four exports had no preamble at all.
"""
import ast
import os

import pytest
from export_sites import export_writer_functions

PLUGIN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "EPG-Janitor")
PLUGIN_SOURCE = os.path.join(PLUGIN_DIR, "plugin.py")


def _plugin(plugin_module):
    inst = plugin_module.Plugin.__new__(plugin_module.Plugin)
    inst.version = "test"
    return inst


def _header(plugin_module, settings=None, total_channels=0, **kwargs):
    return "\n".join(_plugin(plugin_module)._generate_csv_header_comments(
        settings or {}, total_channels, **kwargs))


def _line(header, prefix):
    for line in header.splitlines():
        if line.strip().startswith(prefix):
            return line
    raise AssertionError(f"no line starting {prefix!r} in:\n{header}")


def _declared_fields(plugin_module):
    return {f["id"]: f for f in plugin_module.Plugin._base_fields
            if not f["id"].startswith("_section_")}


# --------------------------------------------------------------------------- #
# What the file is
# --------------------------------------------------------------------------- #
def test_the_file_says_what_it_is_before_it_says_how_it_was_configured(plugin_module):
    header = _header(plugin_module)
    top = " ".join(header.splitlines()[:6]).lower()
    assert "epg janitor" in top
    assert "csv" in top or "export" in top


def test_the_preamble_tells_the_reader_to_skip_the_comment_lines(plugin_module):
    """A spreadsheet import needs telling, or the preamble arrives as data."""
    top = " ".join(_header(plugin_module).splitlines()[:6]).lower()
    assert "skip" in top or "ignore" in top
    assert "comment" in top or "#" in top


def test_each_report_names_itself(plugin_module):
    header = _header(plugin_module, report_title="Scan and Heal Report")
    assert "Scan and Heal Report" in header.splitlines()[0]


def test_every_preamble_line_is_commented(plugin_module):
    """One uncommented line would be read as data by a spreadsheet import."""
    stray = [line for line in _header(plugin_module).splitlines()
             if line and not line.startswith("#")]
    assert stray == []


def test_the_preamble_is_plain_ascii(plugin_module):
    """A spreadsheet opening a CSV under another codepage turns non-ASCII into
    mojibake, so nothing outside ASCII may reach this file."""
    header = _header(plugin_module, {"selected_groups": "US: NBC"}, 5,
                     results=[("Channels matched", 3)])
    bad = sorted({c for c in header if ord(c) > 127})
    assert not bad, [hex(ord(c)) for c in bad]


# --------------------------------------------------------------------------- #
# What the run did
# --------------------------------------------------------------------------- #
def test_the_preamble_states_what_the_run_did_before_how_it_was_configured(plugin_module):
    header = _header(plugin_module, {}, 42, results=[("Channels matched", 30)])
    lines = header.splitlines()
    did = next(i for i, line in enumerate(lines) if "Channels processed: 42" in line)
    configured = next(i for i, line in enumerate(lines) if "Settings used" in line)
    assert did < configured, header
    assert any("Channels matched: 30" in line for line in lines), header


def test_a_run_that_reports_no_extra_counts_still_states_the_channel_count(plugin_module):
    assert "Channels processed: 7" in _header(plugin_module, {}, 7)


# --------------------------------------------------------------------------- #
# How the settings read
# --------------------------------------------------------------------------- #
def test_settings_read_as_yes_and_no_rather_than_python_booleans(plugin_module):
    header = _header(plugin_module, {"ignore_quality_tags": True,
                                     "allow_epg_without_program_data": False})
    assert "Yes" in _line(header, "#   Ignore Quality Tags:")
    assert "True" not in header and "False" not in header, \
        "raw Python booleans still reach the reader"


def test_a_setting_stored_as_a_string_still_reads_as_yes_or_no(plugin_module):
    """Dispatcharr stores some booleans as the strings true and false."""
    header = _header(plugin_module, {"allow_epg_without_programs": "true",
                                     "ignore_quality_tags": "false"})
    assert "Yes" in _line(header, "#   Allow EPG Without Program Data:")
    assert "No" in _line(header, "#   Ignore Quality Tags:")


def test_a_setting_left_at_its_default_shows_the_value_the_run_used(plugin_module):
    """It printed "(not set)", but the default was used and did affect the run."""
    line = _line(_header(plugin_module, {}), "#   Ignore Regional Tags:")
    assert "Yes" in line, line
    assert "not set" not in line, line


def test_an_empty_text_setting_still_reads_as_not_set(plugin_module):
    line = _line(_header(plugin_module, {"ignore_groups": ""}), "#   Ignore Groups:")
    assert "not set" in line


def test_a_setting_whose_leading_space_matters_shows_that_space(plugin_module):
    """Bad EPG Suffix defaults to a leading space, and the form says so.

    Printing it stripped shows the reader a value the run did not use, and hides
    the one character most likely to explain a channel named FoxNews[BadEPG].
    """
    line = _line(_header(plugin_module, {"bad_epg_suffix": " [BadEPG]"}),
                 "#   Bad EPG Suffix:")
    assert '" [BadEPG]"' in line, line


def test_the_confidence_thresholds_say_what_the_number_means(plugin_module):
    """95 of what, and is higher stricter? The number alone answers neither."""
    header = _header(plugin_module, {"automatch_confidence_threshold": 95})
    line = _line(header, "#   Auto-Match Confidence Threshold:")
    assert "100" in line and "strict" in line.lower(), line


def test_an_empty_epg_source_filter_says_that_every_source_is_eligible(plugin_module):
    """Empty means every active source, foreign ones included. That has put a UK
    guide on a US channel here, so the report must not leave it as "(not set)"."""
    line = _line(_header(plugin_module, {"epg_sources_to_match": ""}),
                 "#   EPG Sources to Match:")
    assert "every active" in line.lower(), line


def test_the_export_retention_setting_is_reported(plugin_module):
    """It decides whether older exports still exist, so a reader comparing two
    files needs to know it is on."""
    line = _line(_header(plugin_module, {"csv_retention_days": 0}),
                 "#   Delete CSV Exports Older Than (Days):")
    assert "keep" in line.lower() or "0" in line


def test_every_setting_shown_uses_the_label_it_has_in_the_interface(plugin_module):
    """A reader must be able to find the setting the line names."""
    lines = _header(plugin_module).splitlines()
    start = next(i for i, line in enumerate(lines) if "Settings used" in line)
    shown = [line[4:].split(":")[0].strip() for line in lines[start + 1:]
             if line.startswith("#   ")]
    labels = {f["label"] for f in _declared_fields(plugin_module).values()}
    # The channel-database toggles are built at runtime, one per shipped country
    # file, so they have no entry in the declared list. The preamble reports them
    # under the name their section heading carries.
    labels.add("Channel Databases")
    assert shown, "no settings are reported at all, so this test proves nothing"
    unknown = [s for s in shown if s not in labels]
    assert unknown == [], f"preamble labels that no setting carries: {unknown}"


def test_every_setting_the_preamble_reads_is_a_setting_this_plugin_declares(plugin_module):
    """A wrong key fails silently and forever: it just prints as unset."""
    keys = set(plugin_module.Plugin._REPORTED_SETTINGS)
    declared = set(_declared_fields(plugin_module))
    assert keys, "no settings map found, so this test proves nothing"
    assert keys <= declared, f"preamble reads keys this plugin does not declare: {keys - declared}"


# --------------------------------------------------------------------------- #
# Every export carries a preamble
# --------------------------------------------------------------------------- #
# The detector for "functions that write a CSV export" lives in conftest.py.
# It was copy-pasted into this file and into tests/test_csv_retention.py, and
# the two copies had already drifted: one matched async functions, the other
# did not.


@pytest.mark.parametrize("name", sorted(export_writer_functions()))
def test_every_export_writes_a_preamble(name, export_writers):
    """Two of the four exports had none, so nothing recorded what produced them."""
    node = export_writers[name]
    calls = [c for c in ast.walk(node)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
             and c.func.attr == "_generate_csv_header_comments"]
    assert calls, f"{name} writes a CSV export with no preamble"


# --------------------------------------------------------------------------- #
# Defects found by review, 2026-09-05
# --------------------------------------------------------------------------- #
def _results_of(writers, function_name):
    """The (label, value) pairs one export site passes to the preamble."""
    node = writers[function_name]
    for call in ast.walk(node):
        if (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                and call.func.attr == "_generate_csv_header_comments"):
            for keyword in call.keywords:
                if keyword.arg != "results":
                    continue
                # The argument may be a list literal or several joined with +,
                # so collect every two-element tuple inside it.
                return [(ast.unparse(t.elts[0]), ast.unparse(t.elts[1]))
                        for t in ast.walk(keyword.value)
                        if isinstance(t, ast.Tuple) and len(t.elts) == 2]
    raise AssertionError(f"{function_name} passes no results to the preamble")


def test_a_multi_line_setting_value_stays_on_one_commented_line(plugin_module):
    """Five settings are split on newlines, so a textarea holding one group per
    line is supported input. Interpolated raw, its continuation lines carry no
    #, a spreadsheet reads them as data, and the analysis tool in tools/ reads
    the first of them as the column header row."""
    value = "US: NBC" + chr(10) + "UK: All" + chr(10) + "AU: All"
    header = _header(plugin_module, {"selected_groups": value})

    stray = [line for line in header.splitlines() if line and not line.startswith("#")]
    assert stray == [], stray
    line = _line(header, "#   Channel Groups:")
    assert "US: NBC" in line and "UK: All" in line and "AU: All" in line, line


def test_the_heal_report_counts_the_replacements_it_actually_wrote(export_writers):
    """It reported every candidate found, including the ones below the
    confidence threshold that Scan and Heal deliberately does not write."""
    results = dict(_results_of(export_writers, "_scan_and_heal_worker"))
    written = results["'Replacements written'"]
    assert "replacements_found" not in written, written
    assert "channels_healed" in written, written


def test_the_auto_match_report_does_not_claim_work_it_has_not_done(export_writers):
    """Its preamble is written before the assignments are applied, and the apply
    can still fail, so no line may say assignments were written."""
    labels = [label for label, _value in _results_of(export_writers, "_auto_match_channels")]
    assert "'Assignments written'" not in labels, labels


def test_the_auto_match_report_counts_the_rows_it_will_actually_apply(export_writers):
    """It counted matches carrying program data; the apply loop takes every row
    with an epg_data_id, which is a different and larger set."""
    results = dict(_results_of(export_writers, "_auto_match_channels"))
    assignments = [v for k, v in results.items() if "assignments" in k.lower()]
    assert len(assignments) == 1, results
    assert "validated_matches" not in assignments[0], assignments[0]
    assert "epg_data_id" in assignments[0], assignments[0]


def test_export_retention_runs_after_the_assignments_are_applied(export_writers):
    """Deleting older exports before an apply that then fails throws away the
    history while this run produced nothing usable."""
    node = export_writers["_auto_match_channels"]
    prune = [c.lineno for c in ast.walk(node)
             if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
             and c.func.attr in ("_prune_csv_exports", "_prune_after_export")]
    apply_calls = [c.lineno for c in ast.walk(node)
                   if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                   and c.func.attr == "_batch_set_epg"]
    assert prune and apply_calls, (prune, apply_calls)
    assert min(prune) > max(apply_calls), (prune, apply_calls)


def test_a_boolean_is_rendered_through_the_coercion_the_rest_of_the_class_uses(plugin_module):
    """The class already had _get_bool_setting for exactly this. A second rule
    in the same class drifts from the first."""
    assert not hasattr(plugin_module.Plugin, "_yes_no"), \
        "a second boolean coercion is back in the class"
    header = _header(plugin_module, {"ignore_quality_tags": "on",
                                     "ignore_misc_tags": 0})
    assert "Yes" in _line(header, "#   Ignore Quality Tags:")
    assert "No" in _line(header, "#   Ignore Miscellaneous Tags:")


def test_the_preamble_records_which_channel_databases_were_enabled(plugin_module):
    """They decide which names the matcher may draw from, so a reader asking why
    a channel did not match needs them."""
    header = _header(plugin_module, {"enable_db_US": True, "enable_db_UK": True,
                                     "enable_db_AU": False})
    line = _line(header, "#   Channel Databases:")
    assert "US" in line and "UK" in line, line
    assert "AU" not in line, line


def test_the_preamble_says_so_when_no_database_toggle_was_ever_saved(plugin_module):
    line = _line(_header(plugin_module, {}), "#   Channel Databases:")
    assert "default" in line.lower(), line


def test_no_export_code_hardcodes_the_export_directory(plugin_module):
    """The directory has a class constant. A second copy of the literal means a
    change to one moves some of the code and not the rest."""
    source = open(PLUGIN_SOURCE, encoding="utf-8").read()
    occurrences = source.count('"/data/exports')
    assert occurrences == 1, (
        f'the export directory literal appears {occurrences} times; only the '
        f'EXPORTS_DIR constant may hold it')
