"""The tally behind the public "EPGs Matched" badge.

WHAT ONE UNIT IS. One guide assignment written to one channel, confirmed by
Dispatcharr rather than counted from what the matcher proposed. Apply Auto-Match
and Apply Heal both contribute. A preview contributes nothing, because it writes
nothing. A channel re-assigned next month counts again: this is a total of work
performed, not a count of distinct channels.

NOTHING IDENTIFYING MAY GO IN THIS FILE. A public badge is built from the total,
so the record holds integers and one fixed action name. No channel name, no
group, no EPG source, no URL, no hostname. A test below pins that.

IT MUST NEVER BREAK A RUN. The tally is written from a finally, and a failure to
write it is logged and swallowed: losing a counter is not a reason to fail an
apply that already changed the database.
"""
import json

import pytest
from conftest import build_bare_plugin

ALLOWED_KEYS = {"ts", "action", "assignments_written", "source"}
ALLOWED_ACTIONS = {"auto_match", "heal", "reconstructed_from_exports"}


def _plugin(plugin_module, tmp_path, monkeypatch):
    inst = build_bare_plugin(plugin_module)
    monkeypatch.setattr(plugin_module.Plugin, "MATCH_LEDGER_FILE",
                        str(tmp_path / "counts.jsonl"))
    return inst


# --------------------------------------------------------------------------- #
# Writing a record
# --------------------------------------------------------------------------- #
def test_a_finished_apply_appends_one_record(plugin_module, tmp_path, monkeypatch):
    inst = _plugin(plugin_module, tmp_path, monkeypatch)
    inst._record_assignments_written("auto_match", 12)

    lines = (tmp_path / "counts.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["action"] == "auto_match"
    assert record["assignments_written"] == 12


def test_each_run_adds_a_line_rather_than_replacing_the_file(
        plugin_module, tmp_path, monkeypatch):
    inst = _plugin(plugin_module, tmp_path, monkeypatch)
    inst._record_assignments_written("auto_match", 3)
    inst._record_assignments_written("heal", 4)

    lines = (tmp_path / "counts.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert [json.loads(line)["assignments_written"] for line in lines] == [3, 4]


def test_a_run_that_wrote_nothing_records_nothing(plugin_module, tmp_path, monkeypatch):
    """A preview, and an apply that matched nothing, must not add a line: an
    empty record would make the file grow without the number moving."""
    inst = _plugin(plugin_module, tmp_path, monkeypatch)
    inst._record_assignments_written("auto_match", 0)
    assert not (tmp_path / "counts.jsonl").exists()


def test_the_record_holds_nothing_that_identifies_a_channel(
        plugin_module, tmp_path, monkeypatch):
    """The total is published. Anything else in this file is a leak waiting to
    be summed by a script that does not know it is there."""
    inst = _plugin(plugin_module, tmp_path, monkeypatch)
    inst._record_assignments_written("heal", 5)

    record = json.loads((tmp_path / "counts.jsonl").read_text(encoding="utf-8"))
    assert set(record) <= ALLOWED_KEYS, set(record) - ALLOWED_KEYS
    assert record["action"] in ALLOWED_ACTIONS
    assert isinstance(record["assignments_written"], int)
    assert isinstance(record["ts"], int)


def test_a_tally_that_cannot_be_written_never_breaks_the_run(
        plugin_module, tmp_path, monkeypatch):
    """It runs after the database has already been changed."""
    inst = _plugin(plugin_module, tmp_path, monkeypatch)
    monkeypatch.setattr(plugin_module.Plugin, "MATCH_LEDGER_FILE",
                        str(tmp_path / "no" / "such" / "dir" / "counts.jsonl"))
    inst._record_assignments_written("auto_match", 7)


@pytest.mark.parametrize("count", [None, "twelve", -4])
def test_a_count_that_is_not_a_positive_whole_number_is_ignored(
        plugin_module, tmp_path, monkeypatch, count):
    inst = _plugin(plugin_module, tmp_path, monkeypatch)
    inst._record_assignments_written("auto_match", count)
    assert not (tmp_path / "counts.jsonl").exists()


# --------------------------------------------------------------------------- #
# Both applying actions contribute, and only when they applied something
# --------------------------------------------------------------------------- #
def test_both_applying_actions_record_what_they_wrote():
    """Read from the source: the value has to travel from the batch response
    into the tally, and a test on the tally alone cannot see that."""
    import ast

    from export_sites import parse_plugin
    tree = parse_plugin()
    recorded = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for inner in ast.walk(node):
            if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "_record_assignments_written"):
                recorded.add(node.name)
    assert {"_auto_match_channels", "_scan_and_heal_worker"} <= recorded, recorded


def test_the_tally_is_written_from_a_finally():
    """An apply that raises after writing to the database still did the work."""
    import ast

    from export_sites import parse_plugin
    tree = parse_plugin()
    in_finally = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Try) or not node.finalbody:
            continue
        for inner in ast.walk(ast.Module(body=node.finalbody, type_ignores=[])):
            if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "_record_assignments_written"):
                in_finally.add(ast.unparse(inner)[:60])
    assert len(in_finally) >= 2, in_finally


def test_the_recorded_number_is_the_one_dispatcharr_confirmed():
    """Not the number of assignments the run attempted.

    Swapping the confirmed count for len(associations) passed every other test
    here, because both are integers written from the right place. The badge is
    defined as work Dispatcharr accepted, so the value has to come from the
    batch response.
    """
    import ast

    from export_sites import parse_plugin
    tree = parse_plugin()
    passed = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for inner in ast.walk(node):
            if (isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute)
                    and inner.func.attr == "_record_assignments_written"):
                passed[node.name] = ast.unparse(inner.args[1])

    assert passed.get("_auto_match_channels") == "channels_updated", passed
    assert passed.get("_scan_and_heal_worker") == "channels_healed", passed


def test_the_confirmed_count_comes_from_the_batch_response():
    """Guards the test above: it pins variable NAMES, so it would still pass if
    those names were reassigned from something else."""
    import ast

    from export_sites import parse_plugin
    tree = parse_plugin()
    # Per function, not across the whole file: both applying actions assign this
    # name, so a global check stays green while one of them is changed. A
    # mutation proved that.
    for function_name in ("_auto_match_channels", "_scan_and_heal_worker"):
        func = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef) and n.name == function_name)
        sources = {ast.unparse(node.value) for node in ast.walk(func)
                   if isinstance(node, ast.Assign)
                   and "channels_updated" in [getattr(t, "id", None)
                                              for t in node.targets]}
        assert "response.get('channels_updated', 0)" in sources, (function_name, sources)
