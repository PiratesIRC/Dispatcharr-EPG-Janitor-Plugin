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
