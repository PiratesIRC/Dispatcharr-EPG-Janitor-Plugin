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
