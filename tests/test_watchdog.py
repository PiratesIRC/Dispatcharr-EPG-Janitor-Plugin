"""Unit tests for EPG-Janitor's freshness watchdog pure logic (epg_watchdog.py).

Stdlib-only module; no Django needed. tests/__init__.py puts the plugin dir on sys.path.
"""
from datetime import datetime, timedelta, timezone

import epg_watchdog as wd

NOW = datetime(2026, 7, 17, 11, 0, tzinfo=timezone.utc)


def _src(**kw):
    base = dict(id=22, name="epgshare-UK", status="success", horizon=None)
    base.update(kw)
    return wd.SourceState(**base)


# ---- candidate / stale / classify ----------------------------------------

def test_parse_exclude_ids():
    assert wd.parse_exclude_ids("22, 40 ,x, 7") == {22, 40, 7}
    assert wd.parse_exclude_ids("") == set()
    assert wd.parse_exclude_ids(None) == set()


def test_candidate_gate_is_exclude_only():
    assert wd.is_candidate(_src(id=22), set()) is True
    assert wd.is_candidate(_src(id=22), {22}) is False
    assert wd.is_candidate(_src(id=7), {22, 40}) is True


def test_is_stale_on_error():
    assert wd.is_stale(_src(status="error", horizon=NOW + timedelta(days=2)), NOW, 12) is True


def test_is_stale_on_horizon_and_boundary():
    assert wd.is_stale(_src(horizon=NOW + timedelta(hours=6)), NOW, 12) is True
    assert wd.is_stale(_src(horizon=NOW + timedelta(hours=48)), NOW, 12) is False
    # exact boundary: strict '<' means horizon == now+threshold is NOT stale
    assert wd.is_stale(_src(horizon=NOW + timedelta(hours=12)), NOW, 12) is False


def test_null_horizon_judged_by_status_only():
    assert wd.is_stale(_src(status="success", horizon=None), NOW, 12) is False
    assert wd.is_stale(_src(status="error", horizon=None), NOW, 12) is True


def test_classify_outcome_relative():
    good = _src(status="success", horizon=NOW + timedelta(days=2))
    # error -> success is recovered even with a still-short horizon
    assert wd.classify_outcome(_src(status="error", horizon=NOW + timedelta(hours=1)),
                               _src(status="success", horizon=NOW + timedelta(hours=1))) == "recovered"
    # horizon advanced = recovered
    assert wd.classify_outcome(_src(horizon=NOW + timedelta(hours=3)), good) == "recovered"
    # still error = still_broken
    assert wd.classify_outcome(_src(status="error"),
                               _src(status="error", horizon=NOW + timedelta(days=2))) == "still_broken"
    # refresh didn't help (same short horizon, was success) = still_broken
    same = _src(status="success", horizon=NOW + timedelta(hours=3))
    assert wd.classify_outcome(same, same) == "still_broken"
    # was empty, now populated = recovered
    assert wd.classify_outcome(_src(horizon=None),
                               _src(horizon=NOW + timedelta(days=1))) == "recovered"
    # success -> error regression = still_broken
    assert wd.classify_outcome(good, _src(status="error")) == "still_broken"


# ---- coerce_settings ------------------------------------------------------

def test_coerce_settings_defaults_and_clamp():
    s = wd.coerce_settings({})
    assert s["watchdog_enabled"] is False
    assert s["watchdog_horizon_threshold_hours"] == 12
    assert s["watchdog_check_interval_hours"] == 6
    assert s["watchdog_log_on_recovery"] is True
    assert s["watchdog_exclude_source_ids"] == ""
    c = wd.coerce_settings({"watchdog_horizon_threshold_hours": 0,
                            "watchdog_check_interval_hours": -3,
                            "watchdog_enabled": True})
    assert c["watchdog_horizon_threshold_hours"] == 1
    assert c["watchdog_check_interval_hours"] == 1
    assert c["watchdog_enabled"] is True


def test_coerce_settings_passes_through_foreign_keys():
    s = wd.coerce_settings({"selected_groups": "US: All", "enable_db_US": True})
    assert s["selected_groups"] == "US: All"       # non-watchdog keys survive


# ---- run_check (injected fakes) ------------------------------------------

def _run(*, collect, reread, refresh, logs, settings):
    return wd.run_check(settings, collect_states=collect, refresh_source=refresh,
                        reread_source=reread, now=NOW,
                        log_event=lambda kind, b, a: logs.append((kind, b.id)))


def test_run_check_refreshes_and_recovers():
    dry = _src(status="error", horizon=NOW + timedelta(hours=1))
    good = _src(status="success", horizon=NOW + timedelta(days=2))
    refreshed, logs = [], []
    summary = _run(collect=lambda: [dry], reread=lambda sid: good,
                   refresh=lambda sid: refreshed.append(sid), logs=logs, settings={})
    assert refreshed == [22]
    assert summary["recovered"] == [22] and summary["refreshed"] == [22]
    assert logs == [("recovered", 22)]


def test_run_check_healthy_source_counted_not_refreshed():
    healthy = _src(status="success", horizon=None)
    refreshed = []
    summary = _run(collect=lambda: [healthy], reread=lambda sid: healthy,
                   refresh=lambda sid: refreshed.append(sid), logs=[], settings={})
    assert refreshed == []
    assert summary == {"checked": 1, "refreshed": [], "recovered": [], "still_broken": []}


def test_run_check_refresh_exception_swallowed_not_counted():
    broken = _src(status="error")

    def boom(sid):
        raise RuntimeError("connect failed")

    logs = []
    summary = _run(collect=lambda: [broken], reread=lambda sid: broken,
                   refresh=boom, logs=logs, settings={})
    assert summary["refreshed"] == []
    assert summary["still_broken"] == []
    assert logs == []


def test_run_check_still_broken_logs():
    broken = _src(status="error")
    logs = []
    summary = _run(collect=lambda: [broken],
                   reread=lambda sid: _src(status="error"),
                   refresh=lambda sid: None, logs=logs, settings={})
    assert summary["refreshed"] == [22] and summary["still_broken"] == [22]
    assert logs == [("still_broken", 22)]


def test_run_check_excludes_source():
    broken = _src(status="error")
    refreshed = []
    summary = _run(collect=lambda: [broken], reread=lambda sid: broken,
                   refresh=lambda sid: refreshed.append(sid), logs=[],
                   settings={"watchdog_exclude_source_ids": "22"})
    assert refreshed == [] and summary["checked"] == 0


def test_run_check_recovery_log_suppressed_when_disabled():
    dry = _src(status="error")
    good = _src(status="success", horizon=NOW + timedelta(days=2))
    logs = []
    summary = _run(collect=lambda: [dry], reread=lambda sid: good,
                   refresh=lambda sid: None, logs=logs,
                   settings={"watchdog_log_on_recovery": False})
    assert summary["recovered"] == [22]
    assert logs == []


def test_run_check_empty_source_list():
    summary = _run(collect=lambda: [], reread=lambda sid: None,
                   refresh=lambda sid: None, logs=[], settings={})
    assert summary == {"checked": 0, "refreshed": [], "recovered": [], "still_broken": []}
