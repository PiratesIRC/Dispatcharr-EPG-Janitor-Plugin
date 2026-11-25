"""The carry-over copies old state into the data directory once and never destroys anything.

Proven here: a new file wins over an old one, an old file is never deleted, renamed or edited,
the match tally and the usage install id arrive byte-identical, and migrated.json records the
pass. Every path is under tmp_path.
"""
import os
import pytest

from storage_helpers import Log, make_cfg, make_layout, tmp_legacy


@pytest.fixture
def storage(plugin_impl):
    return plugin_impl.storage


def build(storage, tmp_path, monkeypatch):
    """Bind a fake non-legacy layout with real old files under tmp_path; return (cfg, layout, legacy)."""
    legacy = tmp_legacy(tmp_path)
    cfg = make_cfg(dict(legacy))
    cfg.LEGACY_PATHS = dict(legacy)
    layout = make_layout(storage, str(tmp_path / "root"))
    monkeypatch.setattr(storage._ps, "resolve", lambda *a, **k: layout)
    monkeypatch.setattr(storage._ps, "REFUSE_REAL_DATA", True)
    return cfg, layout, legacy


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


def items(storage, cfg, layout):
    return storage.items_for(cfg, layout)


def reset_flags(storage):
    """migrate skips a data dir it already settled in this process; clear that per test."""
    state = storage._ps._state(storage.SPEC)
    state.migrated_dirs.clear()


def test_a_new_file_wins_and_the_old_file_is_untouched(storage, monkeypatch, tmp_path):
    cfg, layout, legacy = build(storage, tmp_path, monkeypatch)
    reset_flags(storage)
    write(legacy["RESULTS_FILE"], b'{"old": true}\n')
    new_results = os.path.join(layout.data_dir, "epg_janitor_results.json")
    write(new_results, b'{"new": true}\n')
    old_stat = os.stat(legacy["RESULTS_FILE"])

    storage.migrate(layout, items(storage, cfg, layout), Log(), version="t")

    with open(new_results, "rb") as fh:
        assert fh.read() == b'{"new": true}\n'
    with open(legacy["RESULTS_FILE"], "rb") as fh:
        assert fh.read() == b'{"old": true}\n'
    now = os.stat(legacy["RESULTS_FILE"])
    assert (now.st_size, now.st_mtime_ns) == (old_stat.st_size, old_stat.st_mtime_ns)


def test_an_old_file_is_copied_and_never_deleted_or_edited(storage, monkeypatch, tmp_path):
    cfg, layout, legacy = build(storage, tmp_path, monkeypatch)
    reset_flags(storage)
    write(legacy["RESULTS_FILE"], b'{"scan": 1}\n')

    result = storage.migrate(layout, items(storage, cfg, layout), Log(), version="t")

    new_results = os.path.join(layout.data_dir, "epg_janitor_results.json")
    assert open(new_results, "rb").read() == b'{"scan": 1}\n'
    assert open(legacy["RESULTS_FILE"], "rb").read() == b'{"scan": 1}\n'
    assert new_results in result.copied
    assert result.failed == []


def test_the_match_tally_and_install_id_arrive_byte_identical(storage, monkeypatch, tmp_path):
    cfg, layout, legacy = build(storage, tmp_path, monkeypatch)
    reset_flags(storage)
    tally = b'{"assignments_written": 3, "ts": 1, "action": "auto_match"}\n'
    write(legacy["MATCH_LEDGER_FILE"], tally)
    install = b"0123456789abcdef0123456789abcdef"
    old_usage = os.path.join(legacy["USAGE_DATA_DIR"], "epg-janitor")
    write(os.path.join(old_usage, "install_id"), install)

    result = storage.migrate(layout, items(storage, cfg, layout), Log(), version="t")

    new_tally = os.path.join(layout.data_dir, "epg_janitor_match_counts.jsonl")
    assert open(new_tally, "rb").read() == tally
    new_install = os.path.join(layout.data_dir, "usage", "epg-janitor", "install_id")
    assert open(new_install, "rb").read() == install
    assert open(os.path.join(old_usage, "install_id"), "rb").read() == install
    assert not result.install_id_blocked
    # The tally's offset is recorded, so the tail sync starts after the copied bytes.
    offsets = storage._ps._load_offsets(os.path.join(layout.data_dir, "epg_janitor_match_counts.offsets.json"))
    assert offsets == {legacy["MATCH_LEDGER_FILE"]: len(tally)}


def test_the_progress_file_is_carried_beside_the_data_dir(storage, monkeypatch, tmp_path):
    cfg, layout, legacy = build(storage, tmp_path, monkeypatch)
    reset_flags(storage)
    write(legacy["PROGRESS_FILE"], b'{"status": "done"}')

    storage.migrate(layout, items(storage, cfg, layout), Log(), version="t")

    assert open(layout.beside(".progress.json"), "rb").read() == b'{"status": "done"}'
    assert not os.path.exists(os.path.join(layout.data_dir, "progress.json"))


def test_migrated_json_and_markers_are_written_on_a_clean_pass(storage, monkeypatch, tmp_path):
    cfg, layout, legacy = build(storage, tmp_path, monkeypatch)
    reset_flags(storage)
    write(legacy["RESULTS_FILE"], b"{}\n")

    storage.migrate(layout, items(storage, cfg, layout), Log(), version="1.2.3")

    import json
    record = json.loads(open(os.path.join(layout.data_dir, "migrated.json"), encoding="utf-8").read())
    assert record["version"] == "1.2.3"
    assert record["failed"] == []
    assert record["copied"] and record["copied"][0]["source"] == legacy["RESULTS_FILE"]
    assert os.path.exists(layout.beside(".migrated"))
    assert os.path.exists(layout.beside(".active"))


def test_a_failed_copy_keeps_the_markers_unwritten(storage, monkeypatch, tmp_path):
    cfg, layout, legacy = build(storage, tmp_path, monkeypatch)
    reset_flags(storage)
    write(legacy["RESULTS_FILE"], b"{}\n")
    real = storage._ps._read_bytes

    def flaky(path):
        if path == legacy["RESULTS_FILE"]:
            raise OSError("unreadable")
        return real(path)

    monkeypatch.setattr(storage._ps, "_read_bytes", flaky)
    result = storage.migrate(layout, items(storage, cfg, layout), Log(), version="t")

    assert result.failed == ["epg_janitor_results.json"]
    assert not os.path.exists(layout.beside(".migrated"))


def test_the_tally_copy_stops_at_its_last_newline(storage, monkeypatch, tmp_path):
    """An old worker may be mid-write: only complete lines are copied, and the offset says so."""
    cfg, layout, legacy = build(storage, tmp_path, monkeypatch)
    reset_flags(storage)
    complete = b'{"assignments_written": 7, "action": "heal", "ts": 3}\n'
    partial = b'{"assignments_written": 9, "act'
    write(legacy["MATCH_LEDGER_FILE"], complete + partial)

    storage.migrate(layout, items(storage, cfg, layout), Log(), version="t")

    new_tally = os.path.join(layout.data_dir, "epg_janitor_match_counts.jsonl")
    assert open(new_tally, "rb").read() == complete
    offsets = storage._ps._load_offsets(os.path.join(layout.data_dir, "epg_janitor_match_counts.offsets.json"))
    assert offsets == {legacy["MATCH_LEDGER_FILE"]: len(complete)}
    assert open(legacy["MATCH_LEDGER_FILE"], "rb").read() == complete + partial
