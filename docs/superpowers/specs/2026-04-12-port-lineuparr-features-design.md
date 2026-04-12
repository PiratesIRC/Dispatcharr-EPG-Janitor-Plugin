# Port Lineuparr Features into EPG-Janitor — Design

**Date:** 2026-04-12
**Target version:** EPG-Janitor 0.8.0 (up from 0.7.0a)
**Source plugin:** Lineuparr 1.26.1001146
**Minimum Dispatcharr version:** v0.20.0

## Goal

Port three capability areas from the Lineuparr plugin into EPG-Janitor, adapted for EPG-matching semantics rather than IPTV-stream-matching semantics:

1. A stronger fuzzy matcher (4-stage pipeline, aliases, token-overlap guards, length-scaled thresholds, pre-normalization caching, regional differentiation)
2. An upgraded EPG-matching pipeline that uses the new matcher's ranked results and pre-filters to program-data candidates
3. Dispatcharr v0.20.0+ plugin GUI customizations (button styling, confirm dialogs, emoji labels, `min_dispatcharr_version`)

## Non-goals

- No replacement of EPG-Janitor's existing per-category toggles (`ignore_quality_tags`, `ignore_regional_tags`, `ignore_geographic_tags`, `ignore_misc_tags`) with Lineuparr's four-preset `match_sensitivity` slider. The toggles remain.
- No conversion of existing free-text multi-value fields (`selected_groups`, `ignore_groups`, `epg_sources_to_match`, `channel_profile_name`) to single-select dropdowns — Dispatcharr multi-select support is unclear and converting to single-select is a regression.
- No integration test harness or Dispatcharr-in-container testing. Only pure-Python unit tests for the fuzzy matcher.
- No rewrite of the 12 action methods that don't do fuzzy matching (remove_epg_*, add_bad_epg_suffix, scan_missing_epg, export_results, etc.).

## Strategy: Hybrid

Ported from Lineuparr:
- `fuzzy_matcher.py` — algorithmic upgrades (aliases, guards, caching, ranked matches, regional differentiation)
- `aliases.py` — wholesale copy of the ~200-entry built-in alias table
- `plugin.json` — GUI customizations (button styling, confirms, emoji, `min_dispatcharr_version`)

Preserved from EPG-Janitor:
- Existing settings field shapes (string/number/boolean), all existing values remain valid across upgrade
- The four independent normalization toggles
- EPG-Janitor's richer `QUALITY_PATTERNS`, `REGIONAL_PATTERNS`, `GEOGRAPHIC_PATTERNS`, `MISC_PATTERNS` regex sets (Lineuparr's consolidated patterns miss some bracketed variants)
- The 12 non-matching action methods

## Architecture

### `fuzzy_matcher.py`

Base: Lineuparr's file. Merge in EPG-Janitor's normalization pattern sets. Keep the existing `user_ignored_tags` parameter (category name set: `{"quality", "regional", "geographic", "misc"}`) so the four boolean toggles in plugin.json continue to work.

New / ported members:

- `alias_match(query, candidates, alias_map) -> (matched, score, "alias") | None` — stage 0 of the matching pipeline
- `_length_scaled_threshold(base_threshold, name_length) -> float` — stricter threshold for short names (95% for ≤4 chars, 90% for ≤8 chars)
- `_has_token_overlap(name_a, name_b, mode="basic"|"majority") -> bool` — guards against spurious matches that share only stop words
- `_channel_number_boost(query, candidate, channel_number) -> int` — +5 points when a 3+ digit number appears in the candidate name. Mostly dormant in EPG-Janitor (EPG display names rarely contain channel numbers) but preserved for API compatibility and edge cases.
- `_norm_cache`, `_norm_nospace_cache`, `_processed_cache` — instance-level caches
- `precompute_normalizations(names: Iterable[str]) -> None` — populate the caches before a batch loop
- `_get_cached_norm(name) -> str`, `_get_cached_processed(name) -> str` — cache-aware getters used internally by the pipeline stages
- `match_all_streams(query, candidates, alias_map, channel_number=None, user_ignored_tags=None, min_score=0) -> List[Tuple[str, int, str]]` — returns all matches with `score >= min_score`, sorted by score descending. Tuple shape: `(candidate_name, score, match_type)` where `match_type ∈ {"alias", "exact", "substring", "fuzzy"}`. The caller (not the matcher) applies domain-specific thresholds like `automatch_confidence_threshold` — `min_score=0` returns every candidate that survived the pipeline's guards. Pipeline stages short-circuit: once a candidate hits in an earlier stage, that stage's `match_type` is recorded and later stages are skipped for it.

Retained for backward compatibility (thin wrapper):

- `fuzzy_match(query, candidates, user_ignored_tags=None, remove_cinemax=False) -> (matched, score, match_type)` — delegates to `match_all_streams()` with an empty alias map (so legacy callers see no surprise alias hits) and returns `matches[0]` when non-empty, or `("", 0, "none")` sentinel when empty. Avoids a flag-day rewrite of the callsites we don't intend to migrate in this port.

Regional differentiation interaction with `ignore_regional_tags`:

| Setting value | Normalization | Match-time filtering |
|---|---|---|
| `True` (default) | Strip East/West/Pacific/Central/Mountain/Atlantic | No-op — all candidates eligible |
| `False` | Preserve East/West (strip Pacific/Central/Mountain/Atlantic) | Apply Lineuparr's rules: East ≠ West-only; Pacific matches only Pacific; regionless prefers regionless, rejects Pacific/West |

The second row is a behavior change from EPG-Janitor 0.7.0a. Called out in migration notes below.

### `aliases.py` (new file)

Wholesale copy of Lineuparr's 200-entry built-in alias table. Exposes one top-level constant:

```python
BUILT_IN_ALIASES: Dict[str, List[str]] = {
    "FOX News Channel": ["FOX NEWS HD", "FoxNews", "Fox News USA"],
    ...
}
```

A `custom_aliases` plugin.json string field accepts a JSON object with the same shape. Effective alias map at match time:

```python
effective = {**BUILT_IN_ALIASES, **json.loads(settings.custom_aliases or "{}")}
```

Malformed JSON: warn-log and fall back to built-ins only. Do not crash the action.

### `plugin.py` — refactored code paths

Two hot paths change. Everything else is untouched.

**`_auto_match_channels()` / `_find_best_epg_match()`** (called from `preview_auto_match_action` and `apply_auto_match_action`):

1. Pre-compute EPG IDs with program data inside `check_hours` (already done today; keep).
2. Build effective alias map once.
3. Call `matcher.precompute_normalizations(all_epg_display_names)` before the channel loop.
4. Per channel: call `matcher.match_all_streams(channel.name, epg_names, alias_map, channel_number=None, user_ignored_tags=ignored_set, min_score=automatch_confidence_threshold)`. Because the matcher returns results sorted desc and already above the threshold, the caller takes `matches[0]` (or records "no match" if the list is empty).
5. The match-type from the pipeline (`alias`/`exact`/`substring`/`fuzzy`) is recorded in CSV output.

**Heal flow (`_scan_and_heal_*_action`)**:

1. Same preparation as above.
2. Per broken channel: call `match_all_streams(..., min_score=heal_confidence_threshold)`. Walk the ranked list and select the first candidate that (a) has program data and (b) lives in `heal_fallback_sources` (or the current assignment's source).
3. If no candidate qualifies, leave the assignment unchanged. Record reason in CSV.

This ranked-fallback behavior is the main reason for adopting `match_all_streams()` over the single-best-match API.

### `plugin.json`

Add/change:

- `"version": "0.8.0"` (from `"0.7.0a"`)
- `"min_dispatcharr_version": "v0.20.0"`
- New field: `{"id": "custom_aliases", "label": "Custom Channel Aliases (JSON)", "type": "string", "default": ""}`
- Action enrichments per this table:

| Category | button_variant | button_color | confirm? | Actions |
|---|---|---|---|---|
| Informational | outline | blue | no | validate_settings, get_summary, scan_missing_epg |
| Dry-run / preview | outline | cyan | no | preview_auto_match, scan_and_heal_dry_run, export_results |
| Non-destructive apply | filled | green | yes | apply_auto_match, scan_and_heal_apply |
| Destructive (channel edits) | filled | orange | yes | add_bad_epg_suffix, remove_epg_from_hidden |
| Destructive (EPG removal) | filled | red | yes (strong wording) | remove_epg_assignments, remove_epg_by_regex, remove_all_epg_from_groups |
| File cleanup | outline | red | yes | clear_csv_exports |

Emoji labels applied to all 14 actions (Lineuparr style).

Free-text multi-value fields (`selected_groups`, `ignore_groups`, `epg_sources_to_match`, `channel_profile_name`) stay as `type: "string"`. Not converted to select.

### Tests

New `tests/test_fuzzy_matcher.py`, stdlib `unittest`, no external deps. Structure:

- `TestNormalization` — each category toggle on/off, bracketed and parenthesized variants, Unicode, callsign extraction, provider-prefix stripping
- `TestAliasStage` — built-in hit, custom override wins, malformed custom JSON ignored
- `TestLengthScaledThreshold` — short-name tightening at boundaries (4, 5, 8, 9 chars)
- `TestTokenOverlap` — basic vs majority mode, stop-word filtering
- `TestRegionalDifferentiation` — `ignore_regional_tags=True` keeps everything; `ignore_regional_tags=False` applies East/West/Pacific rules
- `TestMatchAllStreams` — ranked ordering, threshold cutoff, 4-stage short-circuiting
- `TestCaching` — `precompute_normalizations()` populates caches; subsequent calls hit cache

Target 30–50 focused tests. Run with `python -m unittest discover tests` from the plugin root.

## Migration & compatibility

- All existing plugin.json settings keep their types and semantics. Existing user settings remain valid after upgrade.
- Behavior change: users who previously set `ignore_regional_tags=False` will see Lineuparr-style regional filtering kick in (East can no longer match West-only channels, etc.). Document in CLAUDE.md under an "Upgrade notes" section.
- Behavior change: auto-match will be faster on large EPG databases (pre-normalization caching) and more accurate (alias stage + token-overlap guard). May surface matches that were previously missed — users should re-run **Preview Auto-Match** after upgrade.
- No Dispatcharr DB schema change.
- Rollback: drop in the 0.7.0a files; no migrations to undo.

## Risks

- **Alias file mismatch.** Lineuparr's aliases are authored against provider lineup channel names; EPG-Janitor matches against EPG display names. Mismatches should be rare because alias *values* (the variants) are the same IPTV/EPG naming variations, but edge cases exist. Mitigation: `custom_aliases` override and the token-overlap guard.
- **Normalization regression.** Lineuparr's consolidated patterns miss some bracketed variants EPG-Janitor currently strips. Mitigation: keep EPG-Janitor's pattern sets verbatim; only adopt Lineuparr's pipeline logic.
- **No integration test.** Manual verification only (per project convention). Mitigation: ranked-fallback heal and auto-match both have dry-run variants already — recommend running those before apply on production data.

## Out-of-scope items deferred

- Dynamic select fields (profiles, groups, EPG sources)
- Match sensitivity preset slider
- Tests beyond the fuzzy matcher
- Bumping `min_dispatcharr_version` beyond v0.20.0

## Success criteria

- `python -m unittest discover tests` passes on Python 3.13 with stdlib only.
- Existing plugin.json settings load without error in Dispatcharr v0.20.0+.
- Preview Auto-Match on a known EPG database returns a match set equal to or a superset of 0.7.0a results at the same `automatch_confidence_threshold`.
- Scan & Heal (Dry Run) reports at least as many healable channels as 0.7.0a thanks to ranked fallback.
- All 14 actions render in the Dispatcharr UI with the new colors, confirm dialogs, and emoji labels.
