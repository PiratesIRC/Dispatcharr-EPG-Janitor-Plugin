"""Pure, Django-free helpers for building Dispatcharr action-card notifications.

Lives outside plugin.py so the offline test suite (which prepends EPG-Janitor/
to sys.path) can import and test it without Dispatcharr/Django.

Dispatcharr's action card silently truncates notification text at ~380
characters, so every user-facing message must be a count-based summary, never
an enumeration. These helpers codify that contract in one testable place.
"""

# Dispatcharr's action-card notification display truncates beyond ~380 chars.
NOTIFICATION_CHAR_CAP = 380


def filter_phrase(items, lead, noun, parens=False):
    """Notification-safe filter description: names joined when there are few,
    a bare count when many — keeps messages within the UI's char cap.

    e.g. ``filter_phrase(["A", "B"], "in", "groups")`` -> ``" in groups: A, B"``
    and ``filter_phrase(big_list, "in", "groups")`` -> ``" in 12 groups"``.
    """
    body = (f"{lead} {noun}: {', '.join(items)}" if len(items) <= 3
            else f"{lead} {len(items)} {noun}")
    return f" ({body})" if parens else f" {body}"


def truncate_message(text, limit=NOTIFICATION_CHAR_CAP):
    """Clamp a notification to the UI char cap, appending an ellipsis when cut.

    The Dispatcharr action card truncates silently; doing it here makes the cut
    visible (trailing ``…``) so a clipped message is obvious rather than
    appearing to end mid-sentence.
    """
    if not text:
        return ""
    if len(text) <= limit:
        return text
    if limit <= 1:
        return text[:limit]
    return text[:limit - 1].rstrip() + "…"
