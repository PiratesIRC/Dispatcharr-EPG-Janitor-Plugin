"""Dispatcharr 0.34 task banner: scans run inline inside a Celery task.

On 0.34 every plugin action runs inside Dispatcharr's run_plugin_action Celery
task, and the banner shows the value the task returns. A scan that starts a
daemon thread and returns "started" ends the task at once, so the banner never
shows the real result. Inside a task the scan therefore runs in the calling
thread and returns its real result, and progress goes to the task's
report_progress callable. Outside a task (0.33) the adaptive thread path is
unchanged.
"""

import json
import pathlib
import sys
import threading
import types

import pytest
from conftest import build_bare_plugin

REPO = pathlib.Path(__file__).resolve().parents[1]
PLUGIN_DIR = REPO / "EPG-Janitor"

ASYNC_ACTIONS = {
    "scan_missing_epg",
    "preview_auto_match",
    "apply_auto_match",
    "scan_and_heal_dry_run",
    "scan_and_heal_apply",
}


@pytest.fixture
def module(plugin_module):
    return sys.modules[plugin_module.Plugin.__module__]


class FakeUsage:
    def __init__(self):
        self.calls = []

    def report(self, settings, logger, force=False):
        self.calls.append((settings, force))


@pytest.fixture
def usage(module, monkeypatch):
    fake = FakeUsage()
    monkeypatch.setattr(module, "USAGE", fake, raising=False)
    return fake


@pytest.fixture
def plugin(module, monkeypatch, tmp_path):
    p = build_bare_plugin(module)
    p.scan_progress = {"current": 0, "total": 0, "status": "idle", "start_time": None}
    p._scan_lock = threading.Lock()
    p._sync_scan_active = False
    p._task_reporter = None
    p._progress_path = str(tmp_path / "progress.json")
    p._ADAPTIVE_WAIT_SECONDS = 5
    return p


def _in_a_task(monkeypatch, module):
    monkeypatch.setattr(module.Plugin, "_in_celery_task", staticmethod(lambda: True))


# -- declarations -----------------------------------------------------------

def test_the_scan_actions_are_async_in_plugin_py_and_plugin_json(plugin_module):
    manifest = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))
    served = {a["id"]: a for a in plugin_module.Plugin.actions}
    declared = {a["id"]: a for a in manifest["actions"]}
    for action_id in ASYNC_ACTIONS:
        assert served[action_id].get("async") is True, action_id
        assert declared[action_id].get("async") is True, action_id
    others = [aid for aid in served if aid not in ASYNC_ACTIONS]
    assert not [aid for aid in others if served[aid].get("async")]
    assert not [aid for aid in others if declared[aid].get("async")]


def test_background_tasks_is_declared_in_the_manifest():
    manifest = json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))
    assert "background_tasks" in manifest["capabilities"]
    assert "outbound_network" in manifest["capabilities"]


# -- detecting a Celery task -----------------------------------------------

def test_outside_celery_the_task_check_is_false(module):
    # The tests stub celery with a MagicMock; a stub must never read as a task.
    assert module.Plugin._in_celery_task() is False


def test_a_real_task_id_is_a_task(module, monkeypatch):
    fake = types.SimpleNamespace(current_task=types.SimpleNamespace(
        request=types.SimpleNamespace(id="3f2a9c1e-task")))
    monkeypatch.setitem(sys.modules, "celery", fake)
    assert module.Plugin._in_celery_task() is True


def test_a_task_with_no_id_is_not_a_task(module, monkeypatch):
    fake = types.SimpleNamespace(current_task=types.SimpleNamespace(
        request=types.SimpleNamespace(id=None)))
    monkeypatch.setitem(sys.modules, "celery", fake)
    assert module.Plugin._in_celery_task() is False


def test_no_celery_at_all_is_not_a_task(module, monkeypatch):
    monkeypatch.setitem(sys.modules, "celery", None)
    assert module.Plugin._in_celery_task() is False


# -- inline run inside a task ----------------------------------------------

def test_inside_a_task_the_scan_runs_in_the_calling_thread_and_returns_its_result(
        plugin, module, usage, monkeypatch):
    _in_a_task(monkeypatch, module)
    seen = {}

    def worker():
        seen["thread"] = threading.current_thread().name
        return {"status": "ok", "message": "real result"}

    result = plugin._run_scan_adaptive(worker, {"settings": {}})
    assert result == {"status": "ok", "message": "real result"}
    assert seen["thread"] == threading.current_thread().name
    assert seen["thread"] != "epgj-scan"
    assert plugin._sync_scan_active is False
    assert plugin._task_reporter is None


def test_inside_a_task_progress_reaches_report_progress(plugin, module, usage, monkeypatch):
    _in_a_task(monkeypatch, module)
    calls = []

    def worker():
        plugin._publish_progress("running", action="apply_auto_match", current=1, total=4)
        plugin._publish_progress("done", action="apply_auto_match")
        return {"status": "ok", "message": "done"}

    context = {"settings": {}, "report_progress": lambda pct, msg: calls.append((pct, msg))}
    plugin._run_scan_adaptive(worker, context)
    assert calls == [(25, "Apply Auto-Match 1/4"), (100, "Apply Auto-Match finished")]


def test_a_running_record_without_a_total_sends_no_percent(plugin, module, usage, monkeypatch):
    _in_a_task(monkeypatch, module)
    calls = []

    def worker():
        plugin._publish_progress("running", action="scan_missing_epg", current=0, total=0)
        return {"status": "ok", "message": "done"}

    plugin._run_scan_adaptive(worker, {"report_progress": lambda p, m: calls.append((p, m))})
    assert calls == []


def test_inside_a_task_a_failing_scan_returns_an_error_and_clears_state(
        plugin, module, usage, monkeypatch):
    _in_a_task(monkeypatch, module)

    def worker():
        raise RuntimeError("boom")

    result = plugin._run_scan_adaptive(worker, {"report_progress": lambda p, m: None})
    assert result == {"status": "error", "message": "Scan failed: boom"}
    assert plugin._sync_scan_active is False
    assert plugin._task_reporter is None
    assert plugin._scan_busy() is False


def test_inside_a_task_the_usage_report_runs_once_per_scan(plugin, module, usage, monkeypatch):
    _in_a_task(monkeypatch, module)
    plugin._run_scan_adaptive(lambda: {"status": "ok", "message": "x"}, {})
    assert usage.calls == [(None, False)]


def test_outside_a_task_the_thread_path_runs_and_no_reporter_is_called(
        plugin, module, usage):
    calls = []
    names = []

    def worker():
        names.append(threading.current_thread().name)
        plugin._publish_progress("running", action="apply_auto_match", current=1, total=2)
        return {"status": "ok", "message": "real"}

    result = plugin._run_scan_adaptive(worker, {"report_progress": lambda p, m: calls.append(p)})
    assert result == {"status": "ok", "message": "real"}
    assert names == ["epgj-scan"]
    assert calls == []


def test_the_actions_pass_their_context_to_the_scan(plugin, module, usage, monkeypatch):
    _in_a_task(monkeypatch, module)
    calls = []

    def fake_matcher(settings, logger, dry_run=False):
        plugin._publish_progress("done", action="apply_auto_match")
        return {"status": "ok", "message": "m"}

    monkeypatch.setattr(plugin, "_auto_match_channels", fake_matcher)
    context = {"report_progress": lambda p, m: calls.append(p)}
    result = plugin.apply_auto_match_action({}, None, context)
    assert result == {"status": "ok", "message": "m"}
    assert calls == [100]
