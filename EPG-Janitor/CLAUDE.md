# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

EPG Janitor is a **Dispatcharr plugin** (Python) that manages Electronic Program Guide (EPG) data for TV channels. It identifies channels with EPG assignments but missing program data, provides auto-matching, healing of broken EPG assignments, and bulk EPG management.

- **Repository**: https://github.com/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin
- **Version**: 0.6.1
- **Runtime**: Python 3.13+, runs inside Dispatcharr (Django-based)
- **No build step** — plugin is loaded directly by Dispatcharr's plugin system

## Development

There is no formal build, lint, or test infrastructure. The plugin runs within Dispatcharr and is tested manually through its UI actions. Most actions have dry-run/preview variants for safe testing before applying changes.

To develop: copy the `EPG-Janitor/` directory into Dispatcharr's plugins folder. Configuration is done via the Dispatcharr UI.

## Architecture

### Plugin System Contract

Dispatcharr discovers the plugin via `plugin.json`, which declares the module path (`epg_janitor.plugin`), class (`Plugin`), and actions. The single entry point is:

```python
Plugin.run(action, params, context)
```

This routes to one of 14 action methods based on the `action` string parameter.

### Two Main Files

- **`plugin.py`** (~3,200 lines) — The `Plugin` class. Contains all action methods, API integration, matching orchestration, settings/field definitions, CSV export, and UI interaction logic. Actions follow the naming convention `*_action()` (e.g., `scan_missing_epg_action`, `apply_auto_match_action`).

- **`fuzzy_matcher.py`** (~730 lines) — The `FuzzyMatcher` class. Reusable across multiple Dispatcharr plugins. Handles channel name normalization, callsign extraction (US broadcast), multi-stage matching (exact → substring → fuzzy token-sort), and loading of per-country channel databases from `*_channels.json` files.

### Key Patterns

- **Action methods** are the public interface: `preview_auto_match_action()`, `scan_and_heal_dry_run_action()`, etc. Every destructive action has a preview/dry-run counterpart.
- **Private helpers** prefixed with `_`: `_get_api_token()`, `_get_api_data()`, `_post_api_data()`, `_patch_api_data()` handle REST API communication with JWT token caching.
- **Django model imports** (`Channel`, `ChannelProfile`, `ChannelProfileMembership`, `ProgramData`) are used for direct DB queries alongside REST API calls.
- **Settings** are defined in `_base_fields` list and exposed via the `fields` property, rendered by Dispatcharr's UI.

### Channel Databases

11 country-specific JSON files (`US_channels.json`, `UK_channels.json`, etc.) contain broadcast and premium channel data used by FuzzyMatcher. US is the largest at ~3.7 MB. Format:

```json
{"channels": [{"channel_name": "...", "callsign": "...", "type": "broadcast (OTA)"}]}
```

### Matching Pipeline

1. Callsign-based matching for US broadcast/OTA channels (weighted scoring)
2. Name normalization — strips quality tags `[HD]`, regional indicators, geographic prefixes, misc tags via categorized regex patterns in `fuzzy_matcher.py`
3. Multi-stage fuzzy matching: exact match → substring → token-sort ratio
4. Confidence scoring on 0–100 scale with configurable thresholds

### Logging

- Plugin: `logging.getLogger("plugins.epg_janitor")`
- FuzzyMatcher: `logging.getLogger("plugins.fuzzy_matcher")`
- Format: `"%(levelname)s %(name)s %(message)s"`

### Versioning

- Plugin uses semver (`0.6.1`)
- FuzzyMatcher uses Julian date format: `YY.DDD.HHMM` (e.g., `25.330.1600`)

## Upgrade Notes: 0.7.0a → 1.26.0

Behavior changes users may notice:

- **Regional filtering when `ignore_regional_tags=False`**: in 0.7.0a this setting only affected normalization. In 1.26.0 it also enables active filtering — "HBO East" will no longer match "HBO West", and "X Pacific" will only match Pacific variants. Users who want the old "preserve region in name but match across regions" behavior should set `ignore_regional_tags=True` (the default).
- **Alias-backed fuzzy fallback**: the fuzzy fallback stage inside `_find_best_epg_match` now consults a ~200-entry built-in alias table (`aliases.py`) plus any user-supplied `custom_aliases` JSON before falling back to substring/token-sort matching. The callsign/state/city/network scoring pipeline is unchanged — aliases only improve the "premium channel without callsign" path. Run **Preview Auto-Match** after upgrade to review any newly surfaced matches.
- **Performance**: auto-match on large EPG databases is noticeably faster thanks to normalization caching (`precompute_normalizations()`), which the fuzzy fallback now uses.
- **No database migration** — all 0.7.0a settings keep their names and semantics.
- **Versioning scheme**: version numbering adopts Lineuparr-style `1.YY.*`. 1.26.0 is the first release on this scheme; a `1.YY.MMDDHHMM` build suffix may be appended at ship time.

## Architecture additions in 1.26.0

- `aliases.py` — built-in `CHANNEL_ALIASES` dict (copied from the Lineuparr plugin). User-extendable via the `custom_aliases` plugin setting (JSON object merged on top of built-ins).
- `fuzzy_matcher.FuzzyMatcher.match_all_streams(query, candidates, alias_map, channel_number=None, user_ignored_tags=None, min_score=0)` — new ranked-matches API. Pipeline: alias → exact → substring → fuzzy token-sort, with length-scaled thresholds and token-overlap guards. Returns `[(name, score, match_type), ...]` sorted descending. Regional differentiation (East/West/Pacific) runs unless `"regional"` is in `user_ignored_tags`.
- `fuzzy_matcher.FuzzyMatcher.precompute_normalizations(names)` — one-shot cache warmer. `_auto_match_channels` and `_scan_and_heal_worker` call it once before their channel loops.
- `Plugin._build_alias_map(settings)` — merges `CHANNEL_ALIASES` with the user's `custom_aliases` JSON; logs-and-ignores malformed input.
- Legacy methods preserved: `extract_callsign`, `_load_channel_databases`, `reload_databases`, `normalize_callsign`, `extract_tags`, `find_best_match`, `match_broadcast_channel`, `get_category_for_channel`, `build_final_channel_name`. The weighted-scoring pipeline in `_find_best_epg_match` (callsign/state/city/network) is unchanged.

## Plugin.json updates in 1.26.0

- `min_dispatcharr_version: "v0.20.0"`
- New field: `custom_aliases` (JSON string)
- 14 actions now declare `button_variant`, `button_color`, and (for destructive actions) `confirm.message`. Emoji labels apply across the board.
