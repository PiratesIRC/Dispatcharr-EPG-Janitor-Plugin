"""Pure decision logic for EPG-Janitor's freshness watchdog. Stdlib only — no Django.

The watchdog periodically re-refreshes EPG sources that have errored or whose guide is
about to run dry, so a stuck refresh (bug-072: epgshare-UK sat status=error for 3 days and
silently blanked UK: All) cannot go unnoticed. Every function operates on SourceState
snapshots and injected callables, so the whole policy is unit-testable without a database
(the Django glue lives in plugin.py).

There is deliberately NO debounce: EPGSource.updated_at is stamped ONLY on a *successful*
refresh, so it cannot mark a failed attempt; the cadence floor is simply the Beat check
interval. Outcome is judged by RELATIVE improvement (error->ok, or the guide horizon
advanced), never against the arming threshold, so a legitimately short-horizon feed is not
perpetually reported "still broken".
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

LOGGER = logging.getLogger("plugins.epg_janitor")


@dataclass
class SourceState:
    id: int
    name: str
    status: str
    horizon: datetime | None


def parse_exclude_ids(raw):
    out = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


def is_candidate(src, exclude_ids):
    """is_active, non-dummy, and has-mapped-channel are enforced by the ORM query in
    plugin.py; the only decision left here is the user's exclude list."""
    return src.id not in exclude_ids


def is_stale(src, now, horizon_threshold_hours):
    if src.status == "error":
        return True
    if src.horizon is not None and src.horizon < now + timedelta(hours=horizon_threshold_hours):
        return True
    return False


def classify_outcome(before, after):
    """Judge by RELATIVE improvement, never against the arming threshold."""
    if after.status == "error":
        return "still_broken"
    if before.status == "error":
        return "recovered"
    if after.horizon is not None and (before.horizon is None or after.horizon > before.horizon):
        return "recovered"
    return "still_broken"


DEFAULTS = {
    "watchdog_enabled": False,
    "watchdog_horizon_threshold_hours": 12,
    "watchdog_check_interval_hours": 6,
    "watchdog_exclude_source_ids": "",
    "watchdog_log_on_recovery": True,
}
_INT_FLOORS = {"watchdog_horizon_threshold_hours": 1, "watchdog_check_interval_hours": 1}


def coerce_settings(settings):
    """Merge the watchdog defaults over the plugin's settings dict and coerce types.
    Extra (non-watchdog) keys pass through untouched."""
    merged = dict(DEFAULTS)
    merged.update(settings or {})
    for key, floor in _INT_FLOORS.items():
        try:
            merged[key] = max(floor, int(merged[key]))
        except (TypeError, ValueError):
            merged[key] = DEFAULTS[key]
    merged["watchdog_enabled"] = bool(merged["watchdog_enabled"])
    merged["watchdog_log_on_recovery"] = bool(merged["watchdog_log_on_recovery"])
    merged["watchdog_exclude_source_ids"] = str(merged.get("watchdog_exclude_source_ids") or "")
    return merged


def run_check(settings, *, collect_states, refresh_source, reread_source, now, log_event):
    """Pure orchestration: audit -> refresh stale -> re-read -> classify -> log. All I/O is
    injected so the loop is unit-testable. Stateless. Returns a summary dict. A refresh that
    raises is logged and NOT counted as refreshed (classification is skipped for it)."""
    cfg = coerce_settings(settings)
    exclude = parse_exclude_ids(cfg["watchdog_exclude_source_ids"])
    horizon_h = cfg["watchdog_horizon_threshold_hours"]

    summary = {"checked": 0, "refreshed": [], "recovered": [], "still_broken": []}

    for src in collect_states():
        if not is_candidate(src, exclude):
            continue
        summary["checked"] += 1
        if not is_stale(src, now, horizon_h):
            continue

        before = src
        try:
            refresh_source(src.id)
        except Exception as exc:
            LOGGER.error("epg_janitor watchdog refresh(%s) failed: %s", src.id, exc)
            continue
        summary["refreshed"].append(src.id)

        after = reread_source(src.id) or before
        outcome = classify_outcome(before, after)
        if outcome == "recovered":
            summary["recovered"].append(src.id)
            if cfg["watchdog_log_on_recovery"]:
                log_event("recovered", before, after)
        else:
            summary["still_broken"].append(src.id)
            log_event("still_broken", before, after)

    return summary
