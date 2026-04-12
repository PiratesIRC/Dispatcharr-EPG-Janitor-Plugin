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
