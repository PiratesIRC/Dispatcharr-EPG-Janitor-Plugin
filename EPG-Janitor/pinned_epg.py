"""Pinned EPG rules: the pure half of the feature. No Django, no database, no I/O.

An operator writes a JSON map of channel name to guide. After each refresh of a
pinned M3U account, Dispatcharr's auto channel sync resets the guide of every
channel it recreates, so the map is applied again. Everything here is a function
of its arguments and is tested with plain dicts. plugin.py does the database
reads and the single write.

Name matching is EXACT after normalisation, and that is the whole rule. Both the
channel name and each map key go through ``match_key``: a leading rank number is
removed, then the matcher's normaliser removes the quality tags (HD, [HD]),
the geographic prefixes (US:, CA:, LAT:) and the miscellaneous tags ((A), (D)).
Regional markers (East, West, Pacific) and callsigns in parentheses are KEPT,
because they tell two feeds apart and a pinned guide must not cross them. The
result is case-folded and compared for equality. There is no fuzzy score.

Event payloads: Dispatcharr's m3u_refresh payload carries stream and channel
URLs with provider credentials in them. ``event_account`` reads one key,
``account_name``, and nothing else.
"""
from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import NamedTuple

from . import epgj_fields

EVENT_NAME = "m3u_refresh"
APPLY_ACTION = "apply_pinned_epg"
PREVIEW_ACTION = "preview_pinned_epg"
ACCOUNT_NAME_LIMIT = 200

# The normaliser flags used for matching. Fixed, not read from the user's
# normalisation toggles, so a pinned map means the same thing whatever those are.
MATCH_FLAGS = {
    "ignore_quality": True,
    "ignore_regional": False,
    "ignore_geographic": True,
    "ignore_misc": True,
}

OUTCOMES = ("apply", "already_correct", "unmatched", "missing_guide", "ambiguous_guide")

_RANK_RE = re.compile(r"^\s*\d+\s+")
_RULE_KEYS = frozenset(("epg_data_id", "tvg_id", "source"))


class MapError(ValueError):
    """The pinned EPG map cannot be used. The text is the operator-facing reason."""


class Rule(NamedTuple):
    """One parsed map entry. Exactly one of epg_data_id and tvg_id is set."""
    channel: str
    epg_data_id: int | None
    tvg_id: str | None
    source_id: int | None
    source_name: str | None


class Resolution(NamedTuple):
    """Where a rule points. problem is "" when epg_id is set, else "missing" or "ambiguous"."""
    epg_id: int | None
    problem: str
    detail: str
    label: str


def match_key(name: str, normalize: Callable[[str], str]) -> str:
    """The comparison key for a channel name or a map key."""
    text = _RANK_RE.sub("", str(name or ""), count=1)
    text = normalize(text) or ""
    return " ".join(text.split()).casefold()


def parse_map(text: str, normalize: Callable[[str], str]) -> dict[str, Rule]:
    """The map as {match key: Rule}. Empty text is an empty map.

    Raises MapError with a reason for every malformed entry, including two names
    that normalise to the same key, which would make the rule ambiguous.
    """
    raw = str(text or "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise MapError(f"Pinned EPG map is not valid JSON ({exc.msg} at line {exc.lineno}).") from exc
    if not isinstance(data, dict):
        raise MapError("Pinned EPG map must be a JSON object of channel name to rule.")

    rules: dict[str, Rule] = {}
    owner: dict[str, str] = {}
    for name, rule in data.items():
        channel = str(name).strip()
        if not channel:
            raise MapError("A channel name in the pinned EPG map is empty.")
        key = match_key(channel, normalize)
        if not key:
            raise MapError(f"The channel name '{channel}' has no text left to match once tags are removed.")
        if key in owner:
            raise MapError(f"The channel names '{owner[key]}' and '{channel}' both match the same channel "
                           f"name; keep one of them.")
        owner[key] = channel
        rules[key] = _parse_rule(channel, rule)
    return rules


def _parse_rule(channel: str, rule) -> Rule:
    where = f"'{channel}'"
    if isinstance(rule, bool):
        raise MapError(f"The rule for {where} must be an EPG id number or an object, not true or false.")
    if isinstance(rule, int):
        if rule <= 0:
            raise MapError(f"The rule for {where} must be a positive EPG id.")
        return Rule(channel, rule, None, None, None)
    if not isinstance(rule, dict):
        raise MapError(f"The rule for {where} must be an EPG id number or an object with tvg_id or epg_data_id.")

    unknown = sorted(set(rule) - _RULE_KEYS)
    if unknown:
        raise MapError(f"The rule for {where} has an unknown key '{unknown[0]}'; allowed keys are "
                       f"epg_data_id, tvg_id and source.")
    if "epg_data_id" in rule:
        if "tvg_id" in rule or "source" in rule:
            raise MapError(f"The rule for {where} sets both epg_data_id and tvg_id; use one of them.")
        value = rule["epg_data_id"]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise MapError(f"epg_data_id for {where} must be a positive whole number.")
        return Rule(channel, value, None, None, None)

    if "tvg_id" not in rule:
        raise MapError(f"The rule for {where} needs tvg_id or epg_data_id.")
    tvg_id = rule["tvg_id"]
    if not isinstance(tvg_id, str) or not tvg_id.strip():
        raise MapError(f"tvg_id for {where} must be a non-empty text value.")

    source = rule.get("source")
    source_id = None
    source_name = None
    if source is not None and source != "":
        if isinstance(source, bool):
            raise MapError(f"source for {where} must be an EPG source name or id.")
        if isinstance(source, int) and source > 0:
            source_id = source
        elif isinstance(source, str) and source.strip().isdigit():
            source_id = int(source.strip())
        elif isinstance(source, str) and source.strip():
            source_name = source.strip()
        else:
            raise MapError(f"source for {where} must be an EPG source name or id.")
    return Rule(channel, None, tvg_id.strip(), source_id, source_name)


def event_account(params) -> str | None:
    """The account an event is for, or None when params is not an event at all.

    None means a button press. An event that is not m3u_refresh gives "", which
    no pinned account matches. The payload is read for account_name only.
    """
    if not isinstance(params, dict) or "event" not in params:
        return None
    if params.get("event") != EVENT_NAME:
        return ""
    payload = params.get("payload")
    if not isinstance(payload, dict):
        return ""
    value = payload.get("account_name")
    if not isinstance(value, str):
        return ""
    return value.strip()[:ACCOUNT_NAME_LIMIT]


def is_trigger_account(account: str, accounts_text) -> bool:
    """True when the account is named in the pinned accounts setting. Exact match,
    case-insensitive, after stripping both sides."""
    name = str(account or "").strip().casefold()
    if not name:
        return False
    return name in {entry.casefold() for entry in epgj_fields.split_list(accounts_text)}


def resolve_rule(rule: Rule, epg_rows) -> Resolution:
    """Find the one EPG entry a rule names.

    epg_rows are dicts with id, tvg_id, source_id and source_name. A tvg_id held
    by more than one source is refused unless the rule names the source, because
    picking one silently would be a guess.
    """
    rows = list(epg_rows)
    if rule.epg_data_id is not None:
        found = [row for row in rows if row.get("id") == rule.epg_data_id]
        if not found:
            return Resolution(None, "missing", f"EPG entry {rule.epg_data_id} does not exist", "")
        return Resolution(rule.epg_data_id, "", "", _label(found[0]))

    found = [row for row in rows if row.get("tvg_id") == rule.tvg_id]
    where = f"tvg_id {rule.tvg_id}"
    if rule.source_id is not None:
        found = [row for row in found if row.get("source_id") == rule.source_id]
        where += f" in source {rule.source_id}"
    elif rule.source_name:
        wanted = rule.source_name.casefold()
        found = [row for row in found if str(row.get("source_name") or "").casefold() == wanted]
        where += f" in source {rule.source_name}"
    if not found:
        return Resolution(None, "missing", f"no EPG entry with {where}", "")
    if len(found) > 1:
        return Resolution(None, "ambiguous",
                          f"{len(found)} EPG entries have {where}; name the source in the rule", "")
    return Resolution(found[0]["id"], "", "", _label(found[0]))


def _label(row) -> str:
    return f"{row.get('tvg_id') or ''} ({row.get('source_name') or 'no source'}) [id {row.get('id')}]"


def plan(channels, rules: dict[str, Rule], resolutions: dict[str, Resolution],
         normalize: Callable[[str], str]):
    """Decide what each in-scope channel should do.

    channels are dicts with id, name, epg_id and epg_label. Returns
    (rows, summary, associations). Only "apply" rows become associations, so a
    channel is never written to a missing guide and never cleared: the only value
    ever written is a resolved EPG id.
    """
    rows = []
    matched_keys = set()
    for channel in channels:
        key = match_key(channel["name"], normalize)
        rule = rules.get(key)
        row = {
            "channel_id": channel["id"],
            "channel_name": channel["name"],
            "matched_key": "",
            "current_epg_id": channel.get("epg_id"),
            "current_epg_label": channel.get("epg_label") or "",
            "target_epg_id": None,
            "target_label": "",
            "outcome": "unmatched",
            "detail": "",
        }
        if rule is not None:
            matched_keys.add(key)
            row["matched_key"] = rule.channel
            resolution = resolutions.get(key)
            if resolution is None or resolution.problem:
                row["outcome"] = "ambiguous_guide" if resolution and resolution.problem == "ambiguous" \
                    else "missing_guide"
                row["detail"] = resolution.detail if resolution else "no guide was looked up"
            else:
                row["target_epg_id"] = resolution.epg_id
                row["target_label"] = resolution.label
                row["outcome"] = ("already_correct" if resolution.epg_id == channel.get("epg_id")
                                  else "apply")
        rows.append(row)

    summary = {name: sum(1 for row in rows if row["outcome"] == name) for name in OUTCOMES}
    summary["channels"] = len(rows)
    summary["rules_without_channel"] = sum(1 for key in rules if key not in matched_keys)
    associations = [{"channel_id": row["channel_id"], "epg_data_id": row["target_epg_id"]}
                    for row in rows if row["outcome"] == "apply"]
    return rows, summary, associations
