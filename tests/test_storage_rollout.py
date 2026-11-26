"""Rollout safety: old-code and new-code workers run side by side for one release.

storage.ROLLOUT_DUAL_PATHS is True in this release. While it is, a new-code worker also honors
the old progress file that old-code workers still write (the scan single-flight guard), and it
brings the old match tally new bytes in before every append.
"""
import json
import logging
import os
import time

import pytest
from storage_helpers import Log, make_layout, tmp_legacy


@pytest.fixture
def storage(plugin_impl):
    return plugin_impl.storage


@pytest.fixture
def live_layout(plugin_impl, storage, monkeypatch, tmp_path):
    """A non-legacy layout on PluginConfig, with its legacy copies under tmp_path."""
    cfg = plugin_impl.PluginConfig
    legacy = tmp_legacy(tmp_path)
    monkeypatch.setattr(cfg, "LEGACY_PATHS", dict(legacy), raising=False)
    layout = make_layout(storage, str(tmp_path / "root"))
    monkeypatch.setattr(cfg, "STORAGE_LAYOUT", layout, raising=False)
    monkeypatch.setattr(cfg, "RESULTS_FILE", os.path.join(layout.data_dir, "epg_janitor_results.json"))
    monkeypatch.setattr(cfg, "PROGRESS_FILE", layout.beside(".progress.json"))
    tally = os.path.join(layout.data_dir, "epg_janitor_match_counts.jsonl")
    monkeypatch.setattr(cfg, "MATCH_LEDGER_FILE", tally)
    monkeypatch.setattr(plugin_impl.Plugin, "MATCH_LEDGER_FILE", tally)
    return layout, legacy


def bare(plugin_impl, monkeypatch, progress_path):
    plugin = plugin_impl.Plugin.__new__(plugin_impl.Plugin)
    plugin._progress_path = progress_path
    plugin._report_usage = lambda *a, **k: None
    return plugin


def test_the_tally_tail_from_an_old_worker_lands_before_the_new_record(
        plugin_impl, storage, live_layout, monkeypatch, tmp_path):
    layout, legacy = live_layout
    head = b'{"assignments_written": 2, "action": "heal", "ts": 1}\n'
    tail = b'{"assignments_written": 5, "action": "heal", "ts": 2}\n'
    os.makedirs(os.path.dirname(legacy["MATCH_LEDGER_FILE"]), exist_ok=True)
    with open(legacy["MATCH_LEDGER_FILE"], "wb") as fh:
        fh.write(head)
    storage.migrate(layout, storage.items_for(plugin_impl.PluginConfig, layout), Log(), version="t")
    with open(legacy["MATCH_LEDGER_FILE"], "ab") as fh:  # an old-code worker appends after the copy
        fh.write(tail)

    plugin = bare(plugin_impl, monkeypatch, layout.beside(".progress.json"))
    plugin._record_assignments_written("auto_match", 4)

    new_tally = os.path.join(layout.data_dir, "epg_janitor_match_counts.jsonl")
    lines = open(new_tally, "rb").read().splitlines(keepends=True)
    assert lines[0] == head and lines[1] == tail
    assert json.loads(lines[2])["assignments_written"] == 4
    assert len(lines) == 3, "the tail must be appended once, not on every later record"
    plugin._record_assignments_written("auto_match", 1)
    assert len(open(new_tally, "rb").read().splitlines()) == 4


def write_old_progress(path, status, age_seconds):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"status": status, "action": "scan_missing_epg"}, fh)
    when = time.time() - age_seconds
    os.utime(path, (when, when))


def test_a_fresh_old_running_record_marks_the_scan_busy(plugin_impl, storage, live_layout, monkeypatch):
    layout, legacy = live_layout
    os.makedirs(os.path.dirname(legacy["PROGRESS_FILE"]), exist_ok=True)
    write_old_progress(legacy["PROGRESS_FILE"], "running", age_seconds=5)
    plugin = bare(plugin_impl, monkeypatch, layout.beside(".progress.json"))
    assert plugin._scan_busy() is True


def test_a_stale_old_running_record_does_not_block_scans(plugin_impl, storage, live_layout, monkeypatch):
    layout, legacy = live_layout
    os.makedirs(os.path.dirname(legacy["PROGRESS_FILE"]), exist_ok=True)
    write_old_progress(legacy["PROGRESS_FILE"], "running", age_seconds=3600)
    plugin = bare(plugin_impl, monkeypatch, layout.beside(".progress.json"))
    assert plugin._scan_busy() is False


def test_an_old_record_that_is_not_running_does_not_block(plugin_impl, storage, live_layout, monkeypatch):
    layout, legacy = live_layout
    os.makedirs(os.path.dirname(legacy["PROGRESS_FILE"]), exist_ok=True)
    write_old_progress(legacy["PROGRESS_FILE"], "done", age_seconds=1)
    plugin = bare(plugin_impl, monkeypatch, layout.beside(".progress.json"))
    assert plugin._scan_busy() is False


def test_the_old_progress_file_is_ignored_once_the_flag_is_off(plugin_impl, storage, live_layout, monkeypatch):
    layout, legacy = live_layout
    os.makedirs(os.path.dirname(legacy["PROGRESS_FILE"]), exist_ok=True)
    write_old_progress(legacy["PROGRESS_FILE"], "running", age_seconds=5)
    monkeypatch.setattr(storage, "ROLLOUT_DUAL_PATHS", False)
    plugin = bare(plugin_impl, monkeypatch, layout.beside(".progress.json"))
    assert plugin._scan_busy() is False


def test_the_new_progress_record_still_marks_the_scan_busy(plugin_impl, storage, live_layout, monkeypatch):
    layout, legacy = live_layout
    os.makedirs(os.path.dirname(layout.beside(".progress.json")), exist_ok=True)
    with open(layout.beside(".progress.json"), "w", encoding="utf-8") as fh:
        json.dump({"status": "running"}, fh)
    plugin = bare(plugin_impl, monkeypatch, layout.beside(".progress.json"))
    assert plugin._scan_busy() is True


def scan_plugin(plugin_impl, monkeypatch, layout):
    """A bare plugin that can publish progress (bare() omits scan_progress)."""
    os.makedirs(os.path.dirname(layout.beside(".progress.json")), exist_ok=True)
    plugin = bare(plugin_impl, monkeypatch, layout.beside(".progress.json"))
    plugin.scan_progress = {"current": 0, "total": 0, "status": "idle", "start_time": None}
    return plugin


def read_status(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["status"]


def test_a_new_scan_writes_its_progress_to_the_old_file_as_well(plugin_impl, storage, live_layout, monkeypatch):
    layout, legacy = live_layout
    os.makedirs(os.path.dirname(legacy["PROGRESS_FILE"]), exist_ok=True)
    plugin = scan_plugin(plugin_impl, monkeypatch, layout)
    plugin._publish_progress("running", action="scan_missing_epg", current=1, total=4)
    assert read_status(legacy["PROGRESS_FILE"]) == "running"
    assert read_status(layout.beside(".progress.json")) == "running"
    plugin._publish_progress("done", action="scan_missing_epg", summary={"channels": 4})
    assert read_status(legacy["PROGRESS_FILE"]) == "done"
    assert read_status(layout.beside(".progress.json")) == "done"


def test_no_old_file_is_written_once_the_rollout_flag_is_off(plugin_impl, storage, live_layout, monkeypatch):
    layout, legacy = live_layout
    os.makedirs(os.path.dirname(legacy["PROGRESS_FILE"]), exist_ok=True)
    monkeypatch.setattr(storage, "ROLLOUT_DUAL_PATHS", False)
    plugin = scan_plugin(plugin_impl, monkeypatch, layout)
    plugin._publish_progress("running", action="scan_missing_epg", current=1, total=4)
    assert not os.path.exists(legacy["PROGRESS_FILE"])
    assert read_status(layout.beside(".progress.json")) == "running"


def test_a_failed_old_write_is_logged_and_does_not_stop_the_scan(
        plugin_impl, storage, live_layout, monkeypatch, caplog):
    layout, legacy = live_layout
    os.makedirs(legacy["PROGRESS_FILE"])  # a directory where the old file goes: the replace fails
    plugin = scan_plugin(plugin_impl, monkeypatch, layout)
    with caplog.at_level(logging.WARNING, logger=plugin_impl.LOGGER.name):
        plugin._publish_progress("running", action="scan_missing_epg", current=1, total=4)
    assert read_status(layout.beside(".progress.json")) == "running"
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING and "progress" in r.getMessage()]
    assert warnings, "the failed old-path write must be logged at WARNING"


def test_a_done_new_record_does_not_hide_a_fresh_old_running_record(plugin_impl, storage, live_layout, monkeypatch):
    layout, legacy = live_layout
    os.makedirs(os.path.dirname(legacy["PROGRESS_FILE"]), exist_ok=True)
    os.makedirs(os.path.dirname(layout.beside(".progress.json")), exist_ok=True)
    with open(layout.beside(".progress.json"), "w", encoding="utf-8") as fh:
        json.dump({"status": "done"}, fh)
    write_old_progress(legacy["PROGRESS_FILE"], "running", age_seconds=5)
    plugin = bare(plugin_impl, monkeypatch, layout.beside(".progress.json"))
    assert plugin._scan_busy() is True
