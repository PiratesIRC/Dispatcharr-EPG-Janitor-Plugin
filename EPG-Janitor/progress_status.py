"""Pure, Django-free helpers for EPG-Janitor progress/results presentation.

Lives outside plugin.py so the offline unittest harness (which prepends
EPG-Janitor/ to sys.path) can import and test it without Dispatcharr/Django.
"""


def format_eta(seconds):
    """Human-readable ETA. Negative/zero -> '0s'."""
    s = int(seconds)
    if s <= 0:
        return "0s"
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h}h {m}m"
    if m:
        return f"{m}m {sec}s"
    return f"{sec}s"


import json
import os
import tempfile

IDLE = {"status": "idle"}


def load_progress(path):
    """Return the progress dict, or {'status': 'idle'} if missing/corrupt."""
    try:
        with open(path, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return dict(IDLE)
        return data
    except (FileNotFoundError, json.JSONDecodeError, ValueError, OSError):
        return dict(IDLE)


def save_progress_atomic(path, data):
    """Write data as JSON via temp file + os.replace (atomic, no torn reads)."""
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".epgj_prog_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def normalize_stale_progress(progress):
    """A freshly-loaded process cannot have a live run; force running->idle.

    Returns a new dict (does not mutate the input). Non-running states pass
    through unchanged.
    """
    if progress.get("status") == "running":
        out = dict(progress)
        out["status"] = "idle"
        return out
    return progress


import time as _time
from datetime import datetime

ACTION_LABELS = {
    "preview_auto_match": "Preview Auto-Match",
    "apply_auto_match": "Apply Auto-Match",
    "scan_and_heal_dry_run": "Heal Preview",
    "scan_and_heal_apply": "Apply Heal",
    "scan_missing_epg": "Scan Missing EPG",
}


def _action_label(action):
    return ACTION_LABELS.get(action, "last run")


def _summary_lines(results):
    """Reproduce the legacy get_summary body for a results dict."""
    channels = results.get("channels", [])
    scan_time = results.get("scan_time", "Unknown")
    check_hours = results.get("check_hours", 12)
    selected_groups = results.get("selected_groups", "")
    ignore_groups = results.get("ignore_groups", "")
    total_with_epg = results.get("total_channels_with_epg", 0)

    source_summary = {}
    group_summary = {}
    for ch in channels:
        src = ch.get("epg_source", "Unknown")
        grp = ch.get("channel_group", "No Group")
        source_summary[src] = source_summary.get(src, 0) + 1
        group_summary[grp] = group_summary.get(grp, 0) + 1

    if selected_groups:
        gfi = f" (filtered to: {selected_groups})"
    elif ignore_groups:
        gfi = f" (ignoring: {ignore_groups})"
    else:
        gfi = " (all groups)"

    parts = [
        "Last EPG scan results:",
        f"• Scan time: {scan_time}",
        f"• Checked timeframe: next {check_hours} hours{gfi}",
        f"• Total channels with EPG: {total_with_epg}",
        f"• Channels missing program data: {len(channels)}",
    ]
    if source_summary:
        parts.append("\nMissing data by EPG source:")
        for s, c in sorted(source_summary.items(), key=lambda x: x[1], reverse=True):
            parts.append(f"• {s}: {c} channels")
    if group_summary:
        parts.append("\nMissing data by channel group:")
        for g, c in sorted(group_summary.items(), key=lambda x: x[1], reverse=True)[:5]:
            parts.append(f"• {g}: {c} channels")
        if len(group_summary) > 5:
            parts.append(f"• ... and {len(group_summary) - 5} more groups")
    if channels:
        parts.append(f"\nUse 'Export Results to CSV' to get the full list of {len(channels)} channels.")
    return parts


def build_status_or_summary(progress, results, now=None):
    """Return the user-facing message for the merged Status/Results button.

    - progress.status == 'running' -> live progress + ETA.
    - else -> last-results summary with a timestamp/source header,
      or a friendly prompt if there are no results.
    """
    if now is None:
        now = _time.time()

    if progress.get("status") == "running":
        cur = int(progress.get("current", 0))
        total = int(progress.get("total", 0))
        label = _action_label(progress.get("action"))
        pct = (cur / total * 100) if total > 0 else 0
        start = progress.get("start_time")
        if start is not None and cur > 0:
            elapsed = now - start
            remaining = (elapsed / cur) * (total - cur)
            eta = f"ETA: {format_eta(remaining)}"
        else:
            eta = "ETA: calculating..."
        return f"\U0001f504 {label} {cur}/{total} — {pct:.0f}% | {eta}"

    if not results or not isinstance(results, dict):
        return ("Nothing has been run yet. Use \U0001f441️ Preview Auto-Match "
                "or \U0001f9f9 Heal Preview.")

    finished_at = progress.get("finished_at")
    if finished_at:
        ts = datetime.fromtimestamp(finished_at).strftime("%Y-%m-%d %H:%M")
    else:
        ts = results.get("scan_time", "unknown time")
    label = _action_label(progress.get("action"))
    header = f"\U0001f4ca Last {label} — {ts} (no run in progress)\n"
    return header + "\n".join(_summary_lines(results))
