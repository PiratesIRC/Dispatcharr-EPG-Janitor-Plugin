"""Deleting this plugin's own CSV exports by age.

/data/exports is SHARED. Measured on the live system it held files from six
plugins: stream_mapparr_ (65), epg_janitor_ (26), event_channel_managarr_ (14),
lineuparr_ (10), iptv_checker_results_ (5) and channel_mapparr_ (4). So the
selection is scoped to this plugin's own filename prefix AND the .csv suffix,
and widening either one is caught here, because the alternative is deleting
another project's data.

Four further rules exist because this deletes files on other people's
installations:

  - it is off unless a positive number of days is set, so nobody loses files
    merely by upgrading;
  - the file just written is never deleted, whatever the arithmetic says;
  - at least one of this plugin's files always survives, so a small number
    cannot empty the directory;
  - it never raises, because it runs immediately after a successful export.

A warning about the shape of these tests: any test of the age rule or of the
off-by-default rule uses SEVERAL old files. With a single file the survivor rule
keeps it regardless, so such a test passes even when the guard it names has been
deleted. That happened in the sibling plugin iptv_checker and only mutation
testing found it.
"""
import ast
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_PY = REPO_ROOT / "EPG-Janitor" / "plugin.py"

DAY = 86400.0
NOW = 1_800_000_000.0
MINE = "epg_janitor_"


@pytest.fixture(scope="session")
def plugin_class(plugin_module):
    return plugin_module.Plugin


@pytest.fixture(scope="session")
def pmod(plugin_module):
    """The plugin.py module object, for patching its module-level names."""
    return sys.modules[plugin_module.Plugin.__module__]


def _entry(name, days_old):
    return (name, NOW - days_old * DAY)


def _plan(plugin_class, entries, days=5, now=NOW, protect=None):
    return plugin_class._csv_exports_to_delete(entries, days, now, protect)


# --- off unless configured --------------------------------------------------

@pytest.mark.parametrize("days", [0, None, "", -1, "abc", 0.0])
def test_no_retention_configured_deletes_nothing(plugin_class, days):
    entries = [_entry(MINE + "a.csv", 400), _entry(MINE + "b.csv", 300),
               _entry(MINE + "c.csv", 500)]
    assert _plan(plugin_class, entries, days=days) == []


# --- the age rule -----------------------------------------------------------

def test_a_file_older_than_the_limit_is_deleted(plugin_class):
    entries = [_entry(MINE + "old.csv", 9), _entry(MINE + "new.csv", 1)]
    assert _plan(plugin_class, entries, days=5) == [MINE + "old.csv"]


def test_a_file_younger_than_the_limit_is_kept(plugin_class):
    entries = [_entry(MINE + "a.csv", 1), _entry(MINE + "b.csv", 4)]
    assert _plan(plugin_class, entries, days=5) == []


def test_the_boundary_is_not_deleted(plugin_class):
    """Exactly five days old is not OLDER than five days."""
    entries = [_entry(MINE + "edge.csv", 5), _entry(MINE + "keep.csv", 0)]
    assert _plan(plugin_class, entries, days=5) == []


def test_just_past_the_boundary_is_deleted(plugin_class):
    entries = [_entry(MINE + "edge.csv", 5.001), _entry(MINE + "keep.csv", 0)]
    assert _plan(plugin_class, entries, days=5) == [MINE + "edge.csv"]


# --- never another plugin's files -------------------------------------------

def test_another_plugins_csv_is_never_deleted(plugin_class):
    """The export directory is shared by six plugins. This is the one that matters."""
    entries = [
        _entry("stream_mapparr_sorted_20260101_000000.csv", 400),
        _entry("event_channel_managarr_report_20260101.csv", 400),
        _entry("lineuparr_matches_20260101.csv", 400),
        _entry("iptv_checker_results_20260101.csv", 400),
        _entry("channel_mapparr_matches_20260101.csv", 400),
        _entry(MINE + "mine.csv", 400),
        _entry(MINE + "recent.csv", 0),
    ]
    assert _plan(plugin_class, entries, days=5) == [MINE + "mine.csv"]


def test_a_file_that_is_not_a_csv_is_never_deleted(plugin_class):
    entries = [
        _entry(MINE + "notes.txt", 400),
        _entry(MINE + "archive.csv.gz", 400),
        _entry(MINE + "real.csv", 400),
        _entry(MINE + "recent.csv", 0),
    ]
    assert _plan(plugin_class, entries, days=5) == [MINE + "real.csv"]


# --- protections ------------------------------------------------------------

def test_the_file_just_written_is_never_deleted(plugin_class):
    entries = [_entry(MINE + "just_written.csv", 400), _entry(MINE + "other.csv", 400),
               _entry(MINE + "third.csv", 500)]
    plan = _plan(plugin_class, entries, days=5, protect=MINE + "just_written.csv")
    assert MINE + "just_written.csv" not in plan
    assert plan == [MINE + "other.csv", MINE + "third.csv"]


def test_at_least_one_file_always_survives(plugin_class):
    """Every file is old. Keeping the newest stops a small number emptying it."""
    entries = [_entry(MINE + "a.csv", 400), _entry(MINE + "b.csv", 300),
               _entry(MINE + "c.csv", 500)]
    plan = _plan(plugin_class, entries, days=5)
    assert MINE + "b.csv" not in plan, "the newest of this plugin's files must survive"
    assert plan == [MINE + "a.csv", MINE + "c.csv"]


def test_a_single_old_file_is_kept(plugin_class):
    assert _plan(plugin_class, [_entry(MINE + "only.csv", 400)], days=5) == []


def test_the_survivor_is_not_counted_from_another_plugins_files(plugin_class):
    """A newer foreign file must not license deleting all of ours."""
    entries = [_entry("stream_mapparr_sorted_x.csv", 0), _entry(MINE + "mine.csv", 400)]
    assert _plan(plugin_class, entries, days=5) == []


# --- total over its input ---------------------------------------------------

def test_an_empty_directory_is_fine(plugin_class):
    assert _plan(plugin_class, [], days=5) == []


@pytest.mark.parametrize("mtime", [None, "not a number"])
def test_an_unreadable_timestamp_is_left_alone(plugin_class, mtime):
    entries = [(MINE + "odd.csv", mtime), _entry(MINE + "recent.csv", 0)]
    assert _plan(plugin_class, entries, days=5) == []


def test_a_timestamp_that_is_not_a_number_cannot_become_the_survivor(plugin_class):
    """Keeping it would let it stand in as the file that survives.

    Comparisons against a not-a-number value are all false, so it would win the
    "newest" test and every real file would be deleted instead of one surviving.
    """
    entries = [(MINE + "odd.csv", float("nan")),
               _entry(MINE + "old_a.csv", 400),
               _entry(MINE + "old_b.csv", 300)]

    plan = _plan(plugin_class, entries, days=5)

    assert plan == [MINE + "old_a.csv"]
    assert MINE + "old_b.csv" not in plan, "the newest real file must survive"
    assert MINE + "odd.csv" not in plan


# --- the part that touches the filesystem -----------------------------------

def _seed(directory, name, days_old, now):
    import os
    path = directory / name
    path.write_text("x", encoding="utf-8")
    stamp = now - days_old * DAY
    os.utime(path, (stamp, stamp))
    return path


def test_pruning_removes_only_the_old_files_of_this_plugin(
        plugin_class, monkeypatch, tmp_path):
    import time

    now = time.time()
    monkeypatch.setattr(plugin_class, "EXPORTS_DIR", str(tmp_path))
    old = _seed(tmp_path, MINE + "old.csv", 30, now)
    recent = _seed(tmp_path, MINE + "recent.csv", 1, now)
    foreign = _seed(tmp_path, "stream_mapparr_sorted_x.csv", 30, now)

    removed = plugin_class._prune_csv_exports(5)

    assert removed == 1
    assert not old.exists()
    assert recent.exists()
    assert foreign.exists(), "another plugin's file was deleted"


def test_pruning_protects_the_file_just_written(plugin_class, monkeypatch, tmp_path):
    import time

    now = time.time()
    monkeypatch.setattr(plugin_class, "EXPORTS_DIR", str(tmp_path))
    just_written = _seed(tmp_path, MINE + "just.csv", 30, now)
    other = _seed(tmp_path, MINE + "other.csv", 30, now)

    plugin_class._prune_csv_exports(5, protect=MINE + "just.csv")

    assert just_written.exists()
    assert not other.exists()


def test_pruning_a_missing_directory_does_not_raise(plugin_class, monkeypatch, tmp_path):
    monkeypatch.setattr(plugin_class, "EXPORTS_DIR", str(tmp_path / "gone"))
    assert plugin_class._prune_csv_exports(5) == 0


def test_pruning_survives_a_file_it_cannot_delete(
        plugin_class, pmod, monkeypatch, tmp_path):
    """It runs after a successful export and must never turn one into a failure."""
    import time

    now = time.time()
    monkeypatch.setattr(plugin_class, "EXPORTS_DIR", str(tmp_path))
    _seed(tmp_path, MINE + "a.csv", 30, now)
    _seed(tmp_path, MINE + "b.csv", 30, now)
    _seed(tmp_path, MINE + "keep.csv", 0, now)

    def boom(path):
        raise OSError("permission denied")

    monkeypatch.setattr(pmod.os, "remove", boom)

    assert plugin_class._prune_csv_exports(5) == 0


def test_pruning_survives_a_file_that_vanished_between_listing_and_asking(
        plugin_class, pmod, monkeypatch, tmp_path):
    import time

    now = time.time()
    monkeypatch.setattr(plugin_class, "EXPORTS_DIR", str(tmp_path))
    _seed(tmp_path, MINE + "a.csv", 30, now)
    _seed(tmp_path, MINE + "keep.csv", 0, now)

    def gone(path):
        raise OSError("no such file")

    monkeypatch.setattr(pmod.os.path, "getmtime", gone)

    assert plugin_class._prune_csv_exports(5) == 0


# --- wired into every export -------------------------------------------------

# The detector for "functions that write a CSV export" lives in conftest.py,
# shared with tests/test_csv_header.py.


def test_every_function_that_writes_an_export_also_prunes(export_writers):
    missing = []
    for name, node in sorted(export_writers.items()):
        calls = [inner for inner in ast.walk(node)
                 if isinstance(inner, ast.Call)
                 and isinstance(inner.func, ast.Attribute)
                 and inner.func.attr in ("_prune_csv_exports", "_prune_after_export")]
        if not calls:
            missing.append(name)
    assert missing == [], (
        f"these functions write a CSV export but never prune: {missing}"
    )


def test_every_pruning_call_protects_the_file_it_just_wrote(export_writers):
    """Passing the new file's name in is the only thing that protects it."""
    unprotected = []
    for name, node in sorted(export_writers.items()):
        for inner in ast.walk(node):
            if (isinstance(inner, ast.Call)
                    and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "_prune_csv_exports"):
                if not any(kw.arg == "protect" for kw in inner.keywords):
                    unprotected.append(name)
    assert unprotected == []


# --- the setting -------------------------------------------------------------

def test_the_retention_setting_is_declared_and_defaults_to_off(plugin_class):
    field = [f for f in plugin_class._base_fields
             if f["id"] == "csv_retention_days"]
    assert len(field) == 1, "csv_retention_days is not declared in Plugin._base_fields"
    assert field[0]["type"] == "number"
    assert field[0]["default"] == 0, "the default must keep every file"


def test_pruning_touches_no_files_at_all_when_retention_is_off(
        plugin_class, pmod, monkeypatch, tmp_path):
    """Off is the default, and the export directory is shared with five other
    plugins, so listing it and stat-ing every entry on every export was work
    done only to discover the feature is disabled."""
    monkeypatch.setattr(plugin_class, "EXPORTS_DIR", str(tmp_path))

    def refuse(*args, **kwargs):
        raise AssertionError("the export directory was read while retention is off")

    monkeypatch.setattr(pmod.os, "listdir", refuse)
    monkeypatch.setattr(pmod.os.path, "getmtime", refuse)

    assert plugin_class._prune_csv_exports(0) == 0
    assert plugin_class._prune_csv_exports("") == 0
    assert plugin_class._prune_csv_exports(None) == 0


def test_an_unreadable_retention_value_is_logged_rather_than_silently_ignored(
        plugin_class, pmod, monkeypatch):
    """Chosen zero and unreadable value both switch the feature off, and nothing
    distinguished them. A number field round-tripping as "7.0" raises in int(),
    so the feature would be off while the export preamble reports that every
    file is kept, which reinforces the wrong conclusion."""
    warnings = []
    monkeypatch.setattr(pmod.LOGGER, "warning", lambda msg, *a, **k: warnings.append(msg))

    assert plugin_class._retention_days("7.0") == 0
    assert warnings, "an unreadable retention value was swallowed with no log line"

    warnings.clear()
    assert plugin_class._retention_days(0) == 0
    assert warnings == [], "a deliberate 0 must not warn"


def test_the_preamble_reads_the_retention_setting_through_the_shared_parser():
    """A third reading of the same setting can decide the feature is on while
    the other two decide it is off."""
    import ast

    from export_sites import parse_plugin
    tree = parse_plugin()
    func = next(n for n in ast.walk(tree)
                if isinstance(n, ast.FunctionDef) and n.name == "_report_setting_value")
    # Assert on the CALL. A text search for "_retention_days" also matches the
    # setting id "csv_retention_days", which appears in this same function, so
    # the search passes even when the call has been removed. A mutation proved
    # that: replacing the call left this test green. The same substring trap is
    # recorded in this project's notes from an earlier occurrence.
    calls = [n for n in ast.walk(func)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
             and n.func.attr == "_retention_days"]
    assert calls, \
        "the preamble parses the retention setting itself instead of using the shared parser"


def test_both_places_that_pick_this_plugins_exports_use_one_helper():
    """The age rule and the Clear Exports button each decided independently
    which files belong to this plugin. A change to the naming would have had to
    be made in both, and the two would disagree in between."""
    import ast

    from export_sites import parse_plugin
    tree = parse_plugin()
    users = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for inner in ast.walk(node):
            if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "_is_our_export"):
                users.add(node.name)
    assert {"_csv_exports_to_delete", "clear_csv_exports_action"} <= users, users
