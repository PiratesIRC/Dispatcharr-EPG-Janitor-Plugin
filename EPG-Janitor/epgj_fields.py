"""Settings form layout for Dispatcharr 0.34 and later.

Dispatcharr 0.34.0 added collapsible ``section`` fields, a ``rows`` height for
``text`` fields, ``multiselect`` pick lists and ``table`` fields. All of them need
``manifest_version`` 1 in ``plugin.json``, and Dispatcharr 0.33 and earlier drop
a field of a type they do not know, with only a log warning. So the plugin keeps
its flat form in ``Plugin.fields``, which every version reads, and builds the
0.34 copy here for ``Plugin.get_fields``, which only 0.34 and later call.

Seven settings are drawn under NEW ids in the 0.34 form (``LIST_SETTINGS`` and
``TABLE_SETTINGS``), because a multiselect or table needs a list value and a
stored text value under the same id would break the form. The old text setting
keeps its id: 0.33 still edits it, and ``legacy_settings`` writes the new value
back into the old id's text form before the plugin reads its settings, so every
parser and validator reads one form.

Four of them accept * and ? wildcards (channel groups, ignore groups, EPG
sources to match, heal fallback sources). A 0.34 pick list accepts only the
values in its option list and cannot take a typed value, so their options are
every current name, one prefix pattern per name prefix (``prefix_pattern``), and
every value already saved, pattern or not, so nothing saved is lost. A pattern
the list does not offer can still be typed in the flat text form on 0.33.

This module is pure: no Django, no database. ``Plugin.get_fields`` reads the
names and passes them in.
"""

import copy
import json
import re

# new id: old id. Each pick list stores a list of strings; the old setting holds
# the same values as comma-separated text.
LIST_SETTINGS = {
    "channel_profile_list": "channel_profile_name",
    "watchdog_exclude_source_list": "watchdog_exclude_source_ids",
    "selected_group_list": "selected_groups",
    "ignore_group_list": "ignore_groups",
    "epg_source_list": "epg_sources_to_match",
    "heal_fallback_source_list": "heal_fallback_sources",
}
# Pick lists that take * and ? wildcards: new id -> (name list, noun for labels).
# Group names match case-sensitively when written without a wildcard and source
# names case-insensitively (wildcard_match.expand_patterns, ci_plain).
WILDCARD_LISTS = {
    "selected_group_list": ("groups", "group"),
    "ignore_group_list": ("groups", "group"),
    "epg_source_list": ("sources", "source"),
    "heal_fallback_source_list": ("sources", "source"),
}

# Prefix patterns: the text before the first of these characters, when it is
# 1 to 12 characters with no space and no wildcard or bracket, plus that
# character and *. "US: ABC" gives "US:*", "guru-US" gives "guru-*".
PREFIX_SEPARATORS = ":|-"
PREFIX_MAX_LENGTH = 12
_NOT_IN_PREFIX = "*?[]"
# new id: old id. The table stores a list of {"channel", "aliases"} rows; the old
# setting holds the same thing as a JSON object of name -> list of aliases.
TABLE_SETTINGS = {
    "custom_aliases_rows": "custom_aliases",
}
NEW_ID_BY_OLD_ID = {old: new for new, old in LIST_SETTINGS.items()}
NEW_ID_BY_OLD_ID.update({old: new for new, old in TABLE_SETTINGS.items()})

ALIAS_CHANNEL = "channel"
ALIAS_NAMES = "aliases"

_RELOAD_NOTE = ("The list is read when the plugin loads: after {what}, press the refresh "
                "control on the Plugins page to see it here.")
_PATTERN_NOTE = ("An entry ending in * is a pattern that also covers {nouns} added later: "
                 "{example} picks every {noun} whose name starts with {prefix}. "
                 "A pattern saved before this list existed stays in it.")
_GROUP_NOTES = (_PATTERN_NOTE.format(nouns="groups", example="US:*", noun="group", prefix="US:")
                + " " + _RELOAD_NOTE.format(what="creating a group"))
_SOURCE_NOTES = (_PATTERN_NOTE.format(nouns="sources", example="guru-*", noun="source", prefix="guru-")
                 + " " + _RELOAD_NOTE.format(what="adding a source"))

NEW_FIELDS = {
    "selected_group_list": {
        "label": "Channel Groups",
        "help_text": ("Only process channels in these groups. Leave empty to include every group. "
                      "Use this or Ignore Groups, not both. " + _GROUP_NOTES),
    },
    "ignore_group_list": {
        "label": "Ignore Groups",
        "help_text": "Skip channels in these groups. Use this or Channel Groups, not both. " + _GROUP_NOTES,
    },
    "epg_source_list": {
        "label": "EPG Sources to Match",
        "help_text": "EPG sources to match against (a filter, not a priority list). " + _SOURCE_NOTES,
    },
    "heal_fallback_source_list": {
        "label": "Heal Fallback EPG Sources",
        "help_text": ("EPG sources that heal may pick replacement guide entries from. Leave empty to "
                      "use EPG Sources to Match, and when that is empty too, every active source. "
                      + _SOURCE_NOTES),
    },
    "channel_profile_list": {
        "label": "Channel Profile Names",
        "help_text": "Only process channels in these channel profiles. Leave empty to include every profile. Actions like 'Remove EPG from Hidden Channels' use the first profile picked. The list is read when the plugin loads: after creating a profile, press the refresh control on the Plugins page to see it here.",
    },
    "watchdog_exclude_source_list": {
        "label": "Excluded EPG Sources",
        "help_text": "EPG sources the watchdog must never touch. The list is read when the plugin loads: after adding a source, press the refresh control on the Plugins page to see it here.",
    },
    "custom_aliases_rows": {
        "label": "Custom Channel Aliases",
        "help_text": "One row per channel name as it appears in your lineup, with its alternate names separated by commas. A row REPLACES the built-in alias list for that channel name rather than adding to it, so include the built-in variants you still want. Leave the table empty to use the built-in aliases only.",
        "columns": {ALIAS_CHANNEL: "Channel name", ALIAS_NAMES: "Aliases, comma-separated"},
    },
}

# Dispatcharr draws help text as one plain paragraph. In the 0.34 form a long
# help text is cut to its first sentences and the rest follows as titled info
# fields right below the field. Keyed by field id: (short help, [(title, text)]).
HELP_PARAGRAPHS = {
    "allow_epg_without_programs": (
        "When ON, auto-match accepts EPG entries even if they carry no current program schedule. Usually OFF.",
        [
            ("When to turn it on", "Turn it ON for the first auto-match against a freshly added EPG source. Dispatcharr only imports program data for EPG channels already mapped to a Dispatcharr channel, so a brand-new source starts with zero programs and every match would be rejected. After the first auto-match assigns EPG IDs, refresh the EPG source to fill in program data, then turn this OFF again."),
        ],
    ),
    "epg_source_list": (
        NEW_FIELDS["epg_source_list"]["help_text"],
        [
            ("Leaving it empty", "An empty value matches against every active source, including foreign-country ones, so on a single-region install scope this to your region to avoid foreign guide matches."),
            ("Priority", "Match priority follows each source's Dispatcharr priority (higher number wins); disabled EPG sources are skipped."),
        ],
    ),
    "csv_retention_days": (
        "After each export, this plugin's own exports older than this many days are deleted. 0 keeps every file, which is the default.",
        [
            ("What is never deleted", "The file just written is never deleted, and at least one file always survives. Only files named epg_janitor_*.csv are touched, because /data/exports is shared with other plugins."),
        ],
    ),
}
HELP_SUFFIX = "_help_"

SECTION_PREFIX = "_section_"
ABOUT_SUFFIX = "_about"

# Groups a typical user rarely opens start closed.
COLLAPSED_SECTIONS = frozenset((
    "_section_databases",
    "_section_normalization",
    "_section_aliases",
    "_section_watchdog",
    "_section_housekeeping",
    "_section_usage",
))

# Starting height, in lines, of text fields.
TEXT_ROWS = {
    "custom_aliases": 6,
}

_SPLIT_RE = re.compile(r"[,\n]+")


def is_section_header(field):
    """True for an ``info`` field whose id marks the start of a settings group."""
    return (isinstance(field, dict) and field.get("type") == "info"
            and str(field.get("id", "")).startswith(SECTION_PREFIX))


def split_list(value):
    """A comma- or newline-separated setting as a list of trimmed, non-empty
    entries. The plugin's own parsers split on the same two characters."""
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    if value is None:
        return []
    return [part.strip() for part in _SPLIT_RE.split(str(value)) if part.strip()]


# ---- custom aliases: JSON text <-> table rows ------------------------------

def alias_rows_from_json(text):
    """The custom_aliases JSON as table rows, or None when it cannot be shown as
    a table without losing something: malformed JSON, not an object, a value
    that is not a list of strings, or an alias that contains a comma (the table
    cell joins aliases with commas). Empty text gives an empty table."""
    raw = str(text or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(parsed, dict):
        return None
    rows = []
    for name, aliases in parsed.items():
        if not isinstance(aliases, list) or not all(isinstance(a, str) for a in aliases):
            return None
        if any("," in a for a in aliases):
            return None
        rows.append({ALIAS_CHANNEL: str(name), ALIAS_NAMES: ", ".join(a.strip() for a in aliases)})
    return rows


def alias_json_from_rows(rows):
    """Table rows as the custom_aliases JSON text. A row with an empty channel
    name is dropped. Two rows for one channel name are merged in order, with a
    repeated alias kept once. No rows gives an empty string."""
    merged = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get(ALIAS_CHANNEL) or "").strip()
        if not name:
            continue
        aliases = merged.setdefault(name, [])
        for alias in str(row.get(ALIAS_NAMES) or "").split(","):
            alias = alias.strip()
            if alias and alias not in aliases:
                aliases.append(alias)
    return json.dumps(merged, ensure_ascii=False) if merged else ""


# ---- run-time write-back ---------------------------------------------------

def legacy_settings(settings):
    """Return a copy of ``settings`` with every pick-list or table value written
    back into its old text setting, so the rest of the plugin reads one form.

    Only a new id holding a list counts; anything else leaves the old setting
    alone. Dispatcharr 0.34 fills a new id that was never saved with its field
    default, which get_fields builds from the old setting, so the two agree.
    """
    out = dict(settings or {})
    for new_id, old_id in LIST_SETTINGS.items():
        value = out.get(new_id)
        if isinstance(value, list):
            out[old_id] = ", ".join(split_list(value))
    for new_id, old_id in TABLE_SETTINGS.items():
        value = out.get(new_id)
        if isinstance(value, list):
            out[old_id] = alias_json_from_rows(value)
    return out


# ---- building the 0.34 form ------------------------------------------------

def _options(names, extra=(), forbidden=",\n"):
    """Sorted pick-list options from ``names`` plus every ``extra`` value.

    Names are deduplicated case-insensitively, keeping the first spelling seen.
    A name containing a character in ``forbidden`` is left out, because the text
    setting it is written back into could not hold it. An ``extra`` value is
    never left out: Dispatcharr rejects a save holding a value that is not an
    option, so every value already saved must be one.
    """
    seen = {}
    for name in names or ():
        name = str(name or "").strip()
        if name and not any(c in name for c in forbidden):
            seen.setdefault(name.casefold(), name)
    for name in extra or ():
        name = str(name or "").strip()
        if name:
            seen.setdefault(name.casefold(), name)
    return [{"label": n, "value": n} for n in sorted(seen.values(), key=str.casefold)]


def _canonical(values, names):
    """Each value spelled as the matching name (case-insensitive), else as typed.
    The plugin matches profile names case-insensitively, so this changes no
    behaviour; it only makes a saved value show as the selected option."""
    by_key = {str(n).casefold(): str(n) for n in names or ()}
    return [by_key.get(v.casefold(), v) for v in values]


def is_pattern(value):
    """True when wildcard_match treats the value as a glob."""
    return "*" in value or "?" in value


def prefix_pattern(name):
    """The prefix pattern offered for a name, or None. See PREFIX_SEPARATORS.
    The pattern always matches the name it came from."""
    name = str(name or "")
    found = [name.find(c) for c in PREFIX_SEPARATORS if c in name]
    if not found:
        return None
    end = min(found)
    head = name[:end].strip()
    if (not head or len(head) > PREFIX_MAX_LENGTH or any(c.isspace() for c in head)
            or any(c in head for c in _NOT_IN_PREFIX)):
        return None
    return name[:end + 1] + "*"


def _pattern_label(pattern, noun):
    head = pattern[:-1]
    if pattern.endswith("*") and head and not is_pattern(head):
        return f"{pattern} (every {noun} whose name starts with {head})"
    return f"{pattern} (wildcard pattern)"


def _wildcard_options(names, saved, noun, case_sensitive):
    """Options for a wildcard pick list: patterns first, then names, each sorted.

    Patterns are every pattern in ``saved`` plus the prefix pattern of each
    name; a saved spelling wins over a derived one that differs only in case
    (patterns match case-insensitively). Names are every name plus every saved
    value that is not a pattern, deduplicated exactly when ``case_sensitive``
    (group names) and case-insensitively otherwise. A saved value is never left
    out, because Dispatcharr refuses a save holding a value that is not an
    option. A saved name not found in ``names`` is labelled so.
    """
    def name_key(value):
        return value if case_sensitive else value.casefold()

    patterns, literals, known = {}, {}, set()
    for value in saved or ():
        value = str(value or "").strip()
        if not value:
            continue
        if is_pattern(value):
            patterns.setdefault(value.casefold(), value)
        else:
            literals.setdefault(name_key(value), value)
    for name in names or ():
        name = str(name or "").strip()
        if not name or any(c in name for c in ",\n"):
            continue
        known.add(name_key(name))
        literals.setdefault(name_key(name), name)
        pattern = prefix_pattern(name)
        if pattern:
            patterns.setdefault(pattern.casefold(), pattern)
    options = [{"label": _pattern_label(p, noun), "value": p}
               for p in sorted(patterns.values(), key=str.casefold)]
    for value in sorted(literals.values(), key=lambda v: (v.casefold(), v)):
        label = value if name_key(value) in known else f"{value} (not found)"
        options.append({"label": label, "value": value})
    return options


def _wildcard_field(new_id, old_value, stored, names):
    kind, noun = WILDCARD_LISTS[new_id]
    case_sensitive = kind == "groups"
    default = split_list(old_value)
    if not case_sensitive:
        by_key = {str(n).strip().casefold(): str(n).strip() for n in names or ()}
        default = [v if is_pattern(v) else by_key.get(v.casefold(), v) for v in default]
    meta = NEW_FIELDS[new_id]
    return {
        "id": new_id, "label": meta["label"], "type": "multiselect",
        "default": default,
        "options": _wildcard_options(names, default + (stored or []), noun, case_sensitive),
        "help_text": meta["help_text"],
    }


def _source_options(sources, extra_ids=()):
    """Options for the watchdog exclude list: value is the source id as text,
    label is 'id - name'. A saved id no longer in the database stays an option."""
    options = []
    known = set()
    for source_id, name in sorted(sources or (), key=lambda s: int(s[0])):
        value = str(int(source_id))
        if value in known:
            continue
        known.add(value)
        options.append({"label": f"{value} - {name}", "value": value})
    for value in extra_ids or ():
        if value not in known:
            known.add(value)
            options.append({"label": f"{value} - (not found)", "value": value})
    return options


def _exclude_ids(value):
    """Saved exclude ids as text, digits only, in order and without repeats.
    The watchdog's own parser ignores anything that is not a whole number."""
    out = []
    for part in split_list(value):
        if part.isdigit() and str(int(part)) not in out:
            out.append(str(int(part)))
    return out


def _stored_list(settings, new_id):
    value = (settings or {}).get(new_id)
    return split_list(value) if isinstance(value, list) else None


def _stored_rows(settings, new_id):
    value = (settings or {}).get(new_id)
    return [r for r in value if isinstance(r, dict)] if isinstance(value, list) else None


def pick_list_fields(flat_fields, settings=None, profile_names=(), sources=(), group_names=()):
    """Return the flat form with the pick lists and the alias table under their
    new ids. The input is not modified.

    ``settings`` are the SAVED settings (no defaults filled in). A new field's
    default is built from the old text setting, so an install that never saved
    the new field shows its existing values. ``profile_names`` are channel
    profile names, ``sources`` are (id, name) pairs of EPG sources and
    ``group_names`` are channel group names.
    """
    settings = settings or {}
    names_by_kind = {"groups": list(group_names or ()),
                     "sources": [name for _, name in sources or ()]}
    out = []
    for field in flat_fields or []:
        if not isinstance(field, dict):
            continue
        field_id = field.get("id")
        if field_id not in NEW_ID_BY_OLD_ID:
            out.append(copy.deepcopy(field))
            continue

        new_id = NEW_ID_BY_OLD_ID[field_id]
        meta = NEW_FIELDS[new_id]
        old_value = settings.get(field_id, field.get("default", ""))

        if new_id in WILDCARD_LISTS:
            names = names_by_kind[WILDCARD_LISTS[new_id][0]]
            out.append(_wildcard_field(new_id, old_value, _stored_list(settings, new_id), names))
            continue

        if new_id == "channel_profile_list":
            default = _canonical(split_list(old_value), profile_names)
            stored = _stored_list(settings, new_id) or []
            out.append({
                "id": new_id, "label": meta["label"], "type": "multiselect",
                "default": default, "options": _options(profile_names, default + stored),
                "help_text": meta["help_text"],
            })
            continue

        if new_id == "watchdog_exclude_source_list":
            default = _exclude_ids(old_value)
            stored = _exclude_ids(_stored_list(settings, new_id) or [])
            out.append({
                "id": new_id, "label": meta["label"], "type": "multiselect",
                "default": default, "options": _source_options(sources, default + stored),
                "help_text": meta["help_text"],
            })
            continue

        # custom_aliases: a table when the saved JSON converts cleanly or a table
        # value is already saved; otherwise the JSON text box stays, so nothing
        # the operator wrote is hidden or lost.
        default = alias_rows_from_json(old_value)
        if default is None and _stored_rows(settings, new_id) is None:
            out.append(copy.deepcopy(field))
            continue
        columns = [
            {"id": ALIAS_CHANNEL, "label": meta["columns"][ALIAS_CHANNEL], "type": "string"},
            {"id": ALIAS_NAMES, "label": meta["columns"][ALIAS_NAMES], "type": "string"},
        ]
        # A table draws only its label, not its help text, so the explanation
        # goes in an info field above it and the table itself has no label.
        out.append({"id": new_id + ABOUT_SUFFIX, "label": meta["label"], "type": "info",
                    "description": meta["help_text"]})
        out.append({"id": new_id, "label": "", "type": "table", "columns": columns,
                    "default": default or []})
    return out


def sectioned_fields(flat_fields):
    """Return the form rearranged into collapsible sections.

    Each section header becomes a ``section`` marker with the same id, and every
    field after it, up to the next header, gets ``"section": <that id>``. A
    header's explanation moves to an ``info`` field at the top of its section,
    because a marker shows only its label. Fields before the first header stay
    ungrouped. The input is not modified.
    """
    out = []
    current = None
    for field in flat_fields or []:
        if not isinstance(field, dict):
            continue
        if is_section_header(field):
            current = field["id"]
            out.append({
                "id": current,
                "label": field.get("label") or current,
                "type": "section",
                "collapsed": current in COLLAPSED_SECTIONS,
            })
            text = field.get("description") or field.get("help_text") or field.get("value")
            if text:
                out.append({"id": current + ABOUT_SUFFIX, "label": "", "type": "info",
                            "description": text, "section": current})
            continue
        item = copy.deepcopy(field)
        if current is not None:
            item["section"] = current
        if item.get("type") == "text" and item.get("id") in TEXT_ROWS:
            item["rows"] = TEXT_ROWS[item["id"]]
        out.append(item)
        out.extend(_split_help(item, current))
    return out


def _split_help(item, section):
    """Cut a long help text to its short form (in place) and return the rest as
    titled info fields that follow the field."""
    spec = HELP_PARAGRAPHS.get(item.get("id"))
    if not spec:
        return []
    short, paragraphs = spec
    item["description" if item.get("type") == "info" else "help_text"] = short
    extra = []
    for number, (title, text) in enumerate(paragraphs, start=1):
        info = {"id": f"{item['id']}{HELP_SUFFIX}{number}", "label": title,
                "type": "info", "description": text}
        if section is not None:
            info["section"] = section
        extra.append(info)
    return extra


def build_form(flat_fields, settings=None, profile_names=(), sources=(), group_names=()):
    """The complete 0.34 form: pick lists and table, then sections."""
    return sectioned_fields(pick_list_fields(
        flat_fields, settings, profile_names, sources, group_names))
