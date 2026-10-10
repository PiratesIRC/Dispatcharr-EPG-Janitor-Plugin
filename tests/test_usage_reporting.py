"""EPG-Janitor reports its EPGs Matched total through the vendored usage client.

Report sites: the run() wrapper around the whole action, unknown actions included
(unforced, and skipped while a background scan is still running),
_record_assignments_written after the ledger file is closed (forced, and only
when the write succeeded), _run_scan_adaptive's worker thread when it finishes
(forced), and the scheduled watchdog task (a finally on its existing try). The
checkbox sits in its own section at the end of the form.
"""
import ast
import json
import pathlib
import sys
import threading
import time
import types

import pytest
from conftest import build_bare_plugin

PLUGIN_PY = pathlib.Path(__file__).resolve().parent.parent / "EPG-Janitor" / "plugin.py"


@pytest.fixture
def module(plugin_module):
    """plugin.py itself. The package __init__ re-exports only Plugin."""
    return sys.modules[plugin_module.Plugin.__module__]


class FakeUsage:
    def __init__(self, on_report=None):
        self.calls = []
        self.on_report = on_report

    def report(self, settings=None, logger=None, force=False):
        if self.on_report:
            self.on_report()
        self.calls.append((settings, force))


class ExplodingUsage:
    def report(self, settings=None, logger=None, force=False):
        raise RuntimeError("boom")


def _lines(path):
    """Line count of the ledger, 0 while it does not exist yet. A hook that raises
    here would be swallowed by report() before it records the call."""
    return path.read_text(encoding="utf-8").count("\n") if path.exists() else 0


@pytest.fixture
def usage(module, monkeypatch):
    fake = FakeUsage()
    monkeypatch.setattr(module, "USAGE", fake, raising=False)
    return fake


@pytest.fixture
def plugin(module, monkeypatch):
    p = build_bare_plugin(module)
    p.scan_progress = {"current": 0, "total": 0, "status": "idle", "start_time": None}
    p.fuzzy_matcher = types.SimpleNamespace(country_codes=None,
                                            reload_databases=lambda **k: True)
    monkeypatch.setattr(module, "watchdog_sync_schedule", lambda settings: None)
    monkeypatch.setattr(p, "_get_channel_databases", lambda: [])
    return p


@pytest.fixture
def ledger(module, tmp_path, monkeypatch):
    path = tmp_path / "counts.jsonl"
    monkeypatch.setattr(module.Plugin, "MATCH_LEDGER_FILE", str(path))
    return path


def test_the_reporter_is_configured_for_epg_janitor(module):
    u = module.USAGE
    assert (u.plugin, u.counter, u.label) == ("epg-janitor", "epgs_matched", "EPGs Matched")


def test_the_total_sums_the_assignments_written(module, ledger):
    ledger.write_text(json.dumps({"assignments_written": 5}) + "\n"
                      + json.dumps({"assignments_written": 7}) + "\n", encoding="utf-8")
    assert module.USAGE.total_fn() == 12


def test_settings_are_read_under_the_plugin_key(module, monkeypatch):
    seen = []
    monkeypatch.setattr(module, "load_plugin_settings",
                        lambda key, logger=None: seen.append(key) or {})
    module.USAGE.settings_fn()
    assert seen == ["epg-janitor"]


def test_an_action_reports_once_with_the_live_settings(plugin, usage):
    settings = {"x": 1}
    plugin.validate_settings_action = lambda s, logger: {"status": "success", "message": "ok"}
    result = plugin.run("validate_settings", {}, {"settings": settings, "logger": None})
    assert result == {"status": "success", "message": "ok"}
    assert usage.calls == [(settings, False)]


def test_an_action_that_returns_an_error_still_reports(plugin, usage):
    settings = {"x": 1}
    plugin.validate_settings_action = lambda s, logger: {"status": "error", "message": "no", "error": "no"}
    result = plugin.run("validate_settings", {}, {"settings": settings, "logger": None})
    assert result["status"] == "error"
    assert usage.calls == [(settings, False)]


def test_an_action_that_raises_still_reports(plugin, usage):
    settings = {"x": 1}

    def explode(s, logger):
        raise RuntimeError("handler failed")

    plugin.validate_settings_action = explode
    result = plugin.run("validate_settings", {}, {"settings": settings, "logger": None})
    assert result["status"] == "error"
    assert usage.calls == [(settings, False)]


def test_an_action_that_takes_a_context_reports_once(plugin, usage):
    settings = {"x": 1}
    plugin.apply_auto_match_action = lambda s, logger, c=None: {"status": "ok", "message": "started"}
    result = plugin.run("apply_auto_match", {}, {"settings": settings, "logger": None})
    assert result == {"status": "ok", "message": "started"}
    assert usage.calls == [(settings, False)]


def test_an_unknown_action_reports_once(plugin, usage):
    settings = {"x": 1}
    plugin.run("no_such_action", {}, {"settings": settings, "logger": None})
    assert usage.calls == [(settings, False)]


def test_a_context_without_settings_reports_with_none(plugin, usage):
    plugin.validate_settings_action = lambda s, logger: {"status": "success", "message": "ok"}
    plugin.run("validate_settings", {}, {"logger": None})
    assert usage.calls == [(None, False)]


def test_a_recorded_apply_reports_forced_after_the_ledger_is_closed(plugin, module, ledger, monkeypatch):
    lines_seen = []
    fake = FakeUsage(on_report=lambda: lines_seen.append(_lines(ledger)))
    monkeypatch.setattr(module, "USAGE", fake, raising=False)
    plugin._record_assignments_written("auto_match", 9)
    assert fake.calls == [(None, True)]
    assert lines_seen == [1]


def test_a_background_scan_reports_once_when_it_finishes(plugin, module, ledger, usage, monkeypatch, tmp_path):
    release = threading.Event()
    lines_at_report = []
    usage.on_report = lambda: lines_at_report.append(_lines(ledger))

    def worker(settings, logger, dry_run=False):
        release.wait(5)
        # An apply records its ledger line; that write alone forces a send.
        plugin._record_assignments_written("auto_match", 3)
        return {"status": "ok", "message": "done"}

    monkeypatch.setattr(plugin, "_auto_match_channels", worker)
    plugin._ADAPTIVE_WAIT_SECONDS = 0
    plugin._scan_lock = threading.Lock()
    plugin._progress_path = str(tmp_path / "progress.json")
    result = plugin.run("apply_auto_match", {}, {"settings": {"x": 1}, "logger": None})
    assert result["status"] == "ok"
    assert usage.calls == [], "run() must not report while the scan thread is still running"
    release.set()
    for _ in range(500):
        if len(usage.calls) >= 2:
            break
        time.sleep(0.01)
    # The ledger writer forces its send; the scan's own finish does not.
    assert usage.calls == [(None, True), (None, False)]
    assert lines_at_report == [1, 1]


@pytest.mark.parametrize("count", [0, -3, "x", None])
def test_no_recorded_count_means_no_report(plugin, usage, ledger, count):
    plugin._record_assignments_written("auto_match", count)
    assert usage.calls == []
    assert not ledger.exists()


def test_a_failed_ledger_write_does_not_report(plugin, module, usage, tmp_path, monkeypatch):
    monkeypatch.setattr(module.Plugin, "MATCH_LEDGER_FILE", str(tmp_path / "no-dir" / "counts.jsonl"))
    plugin._record_assignments_written("heal", 4)
    assert usage.calls == []


def test_a_reporter_that_raises_never_breaks_the_ledger(plugin, module, ledger, monkeypatch):
    monkeypatch.setattr(module, "USAGE", ExplodingUsage(), raising=False)
    plugin._record_assignments_written("heal", 4)
    assert ledger.read_text(encoding="utf-8").count("\n") == 1


def test_the_scheduled_watchdog_helper_reports_without_settings(module, monkeypatch):
    fake = FakeUsage()
    monkeypatch.setattr(module, "USAGE", fake, raising=False)
    module._report_scheduled_usage()
    assert fake.calls == [(None, False)]


def test_the_scheduled_watchdog_reports_in_a_finally():
    """The Celery decorator is stubbed in tests, so the task cannot be called. Read the source.

    This proves the source text only: the call sits in a top-level finally of the task.
    It does not prove that the task runs.
    """
    tree = ast.parse(PLUGIN_PY.read_text(encoding="utf-8"))
    task = next(n for n in tree.body
                if isinstance(n, ast.FunctionDef) and n.name == "epg_janitor_watchdog_check")
    tops = [n for n in task.body if isinstance(n, ast.Try)]
    finals = [ast.unparse(s) for t in tops for s in t.finalbody]
    assert "_report_scheduled_usage()" in finals, finals


def test_the_form_ends_with_the_usage_section_and_checkbox(plugin, module):
    fields = plugin.fields
    assert fields[-1] == module.with_usage_field([], module.USAGE)[0]
    assert fields[-2]["id"] == "_section_usage" and fields[-2]["type"] == "info"
    assert [f.get("id") for f in fields].count("share_usage_counts") == 1
