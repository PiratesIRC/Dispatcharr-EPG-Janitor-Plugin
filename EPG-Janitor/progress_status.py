"""Pure, Django-free helpers for EPG-Janitor progress/results presentation.

Lives outside plugin.py so the offline unittest harness (which prepends
EPG-Janitor/ to sys.path) can import and test it without Dispatcharr/Django.
"""

import json
import os
import tempfile
import time as _time
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # Python < 3.9 — never the case for Dispatcharr (3.13)
    ZoneInfo = None


def _display_tz():
    """Resolve the TZ for user-facing timestamps.

    Dispatcharr's Django pins ``TIME_ZONE = "UTC"`` and *rewrites* the
    container's ``$TZ`` env var to ``"UTC"`` at startup, so reading
    ``$TZ`` from inside the running process is useless. The authoritative
    user-facing TZ lives in Dispatcharr's own settings via
    ``CoreSettings.get_system_time_zone``. Fall back to ``$TZ`` only if
    Django (or the test harness) isn't available."""
    if ZoneInfo is None:
        return None
    try:
        from core.models import CoreSettings  # local import: Django-optional
        tz_name = CoreSettings.get_system_time_zone()
        if tz_name:
            return ZoneInfo(tz_name)
    except Exception:
        pass
    tz_name = os.environ.get("TZ")
    if tz_name:
        try:
            return ZoneInfo(tz_name)
        except Exception:
            pass
    return None


def format_local_timestamp(unix_ts, fmt="%Y-%m-%d %H:%M %Z"):
    """Format a Unix timestamp in the operator's container TZ."""
    tz = _display_tz()
    if tz is not None:
        return datetime.fromtimestamp(unix_ts, tz=tz).strftime(fmt).strip()
    return datetime.fromtimestamp(unix_ts).strftime(fmt).strip()


def format_local_now(fmt="%Y-%m-%d %H:%M %Z"):
    """``datetime.now()`` formatted in the operator's container TZ."""
    return format_local_timestamp(_time.time(), fmt=fmt)


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


IDLE = {"status": "idle"}


def load_progress(path):
    """Return the progress dict, or {'status': 'idle'} if missing/corrupt."""
    try:
        with open(path) as f:
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


ACTION_LABELS = {
    "preview_auto_match": "Preview Auto-Match",
    "apply_auto_match": "Apply Auto-Match",
    "scan_and_heal_dry_run": "Preview Heal",
    "scan_and_heal_apply": "Apply Heal",
    "scan_missing_epg": "Scan Missing EPG",
}


def _action_label(action):
    return ACTION_LABELS.get(action, "run")


def build_status_or_summary(progress, results, now=None):
    """Return the user-facing message for the Status / Results button.

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

    label = _action_label(progress.get("action"))
    summary = progress.get("summary")
    if isinstance(summary, dict) and summary:
        fin = progress.get("finished_at")
        when = (format_local_timestamp(fin, fmt="%Y-%m-%d %H:%M %Z")
                if fin else "recently")
        lines = [f"\U0001f4ca {label} finished {when} (no run in progress)"]
        order = ["mode", "matched", "applied", "healed", "candidates",
                 "broken", "missing", "total", "total_with_epg", "callsigns"]
        keys = [k for k in order if k in summary]
        keys += [k for k in summary if k not in order]
        for k in keys[:4]:
            lines.append(f"• {k.replace('_', ' ').capitalize()}: {summary[k]}")
        lines.append("Use \U0001f4c4 Export CSV for the full list.")
        return "\n".join(lines)

    if isinstance(results, dict) and results:
        ts = results.get("scan_time", "unknown time")
        n = results.get("total_channels_with_epg", 0)
        m = len(results.get("channels", []))
        return (
            f"\U0001f4ca Last EPG scan — {ts} (no run in progress)\n"
            f"• Total channels with EPG: {n}\n"
            f"• Channels missing program data: {m}\n"
            "Use \U0001f4c4 Export CSV for the full list."
        )

    if progress.get("status") == "done":
        fin = progress.get("finished_at")
        when = (format_local_timestamp(fin, fmt="%Y-%m-%d %H:%M %Z")
                if fin else "recently")
        return f"\U0001f4ca {label} finished {when} (no run in progress)"

    return ("Nothing has been run yet. Use \U0001f50d Scan Missing "
            "or \U0001f441️ Preview Auto-Match.")
