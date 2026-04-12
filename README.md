# Dispatcharr EPG Janitor Plugin

## Keep your Electronic Program Guide clean, accurate, and complete

[![Dispatcharr plugin](https://img.shields.io/badge/Dispatcharr-plugin-8A2BE2)](https://github.com/Dispatcharr/Dispatcharr)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin)

[![GitHub Release](https://img.shields.io/github/v/release/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin?include_prereleases&logo=github)](https://github.com/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin/releases)
[![Downloads](https://img.shields.io/github/downloads/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin/total?color=success&label=Downloads&logo=github)](https://github.com/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin/releases)

![Top Language](https://img.shields.io/github/languages/top/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin)
![Repo Size](https://img.shields.io/github/repo-size/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin)
![Last Commit](https://img.shields.io/github/last-commit/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin)
![License](https://img.shields.io/github/license/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin)

## Warning: Backup Your Database
Before installing or using this plugin, it is **highly recommended** that you create a backup of your Dispatcharr database. This plugin modifies EPG assignments on channels and can rename channels.

**[Click here for instructions on how to back up your database.](https://dispatcharr.github.io/Dispatcharr-Docs/troubleshooting/?h=backup#how-can-i-make-a-backup-of-the-database)**

## Features

- **Auto-Match EPG to Channels:** Intelligent weighted scoring combines US broadcast callsign detection, state/city/network matching, and a Lineuparr-style fuzzy pipeline (alias → exact → substring → token-sort) with length-scaled thresholds to minimize false positives
- **Scan & Heal Broken EPG:** Detect channels whose EPG assignment has no program data and replace it with a working alternative, walking ranked candidates and respecting user-configured fallback sources
- **Built-in Alias Table:** 200+ channel alias mappings for common naming variations (CNN US, FOX News Channel, FS1 ↔ Fox Sports 1, NHL Network ↔ NHL, MS NOW ↔ MSNBC, etc.)
- **Custom Aliases:** User-configurable JSON alias overrides merged on top of the built-in table
- **East/West/Pacific Filtering:** Regional channel variants are routed to the correct regional EPG feeds (Pacific ≡ West)
- **Per-Category Normalization Toggles:** Independent controls for quality tags (`[HD]`, `[4K]`), regional indicators (East/West/Pacific), geographic prefixes (`US:`, `[CA]`), and miscellaneous tags (`(A)`, `(CX)`)
- **Missing Program Data Scanner:** Find every channel with an EPG assignment but no actual program schedule
- **Bulk EPG Management:** Remove EPG assignments by REGEX pattern, from hidden channels, or from entire groups
- **Bad EPG Suffix Tagging:** Add a configurable suffix (e.g. `[BadEPG]`) to channels with missing program data for easy visual flagging
- **Channel Database Selector:** Per-country channel databases (US, UK, CA, DE, ES, FR, IN, MX, NL, AU, BR) toggled independently to speed up matching
- **CSV Preview/Export:** Every auto-match and heal run exports results with confidence scores, match method, and reasoning
- **Dispatcharr v0.20.0+ UI:** Section dividers, help text, placeholders, textarea inputs for multi-value fields, color-coded action buttons with confirmation dialogs
- **Direct ORM Integration:** Runs inside Dispatcharr — no API credentials needed

## Requirements

- Dispatcharr v0.20.0 or newer
- Python 3.13+ (bundled with Dispatcharr)
- No external dependencies — stdlib only

## Installation

1. Download the latest `EPG-Janitor.zip` from the [Releases](https://github.com/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin/releases) page.
2. Log in to Dispatcharr's web UI.
3. Navigate to **Plugins** → **Import Plugin** and upload the zip.
4. Enable the plugin after installation.

### Updating the Plugin

1. **Remove Old Plugin** — Navigate to **Plugins**, click the trash icon next to EPG Janitor, confirm.
2. **Restart Dispatcharr** — Log out, then `docker restart dispatcharr` (or equivalent).
3. **Install the New Version** — Log back in, Import the new zip, enable.
4. **Your settings are preserved** — Dispatcharr stores plugin settings in its database separately from plugin code. Updates do not clear your configuration.

## Settings Reference

| Setting | Type | Default | Description |
|---|---|---|---|
| Channel Profile Names | textarea | *(empty)* | Comma-separated profile names. Used by "Remove EPG from Hidden Channels". |
| Channel Groups | textarea | *(empty)* | Only process channels in these groups. Leave empty for all groups. |
| Ignore Groups | textarea | *(empty)* | Exclude channels in these groups. |
| EPG Sources to Match | textarea | *(empty)* | Comma-separated EPG source names. Empty = all sources. |
| Hours to Check Ahead | number | `12` | Time window used to validate that a matched EPG carries program data. |
| Auto-Match Confidence Threshold | number | `95` | 0–100. Matches below this score are rejected. |
| Allow EPG Without Program Data | boolean | `false` | When ON, auto-match accepts EPG entries with no current schedule. |
| Heal Fallback EPG Sources | textarea | *(empty)* | Comma-separated sources heal is allowed to pick replacements from. Empty = channel's current source only. |
| Heal Confidence Threshold | number | `95` | Minimum replacement score during Scan & Heal. |
| EPG Name REGEX to Remove | string | *(empty)* | Python regex. Channels whose current EPG matches get their EPG removed. |
| Bad EPG Suffix | string | ` [BadEPG]` | Suffix appended to channels with missing program data. Leading space matters. |
| Also Remove EPG When Adding Suffix | boolean | `false` | When ON, the suffix action also strips the channel's EPG. |
| Ignore Quality Tags | boolean | `true` | Strip `[HD]`, `[4K]`, `[SD]`, `(Backup)` etc. before comparing names. |
| Ignore Regional Tags | boolean | `true` | Strip East/West/Pacific/etc. The regional filter still runs when a lineup explicitly carries a marker. |
| Ignore Geographic Prefixes | boolean | `true` | Strip `US:`, `UK:`, `[CA]` etc. |
| Ignore Miscellaneous Tags | boolean | `true` | Strip `(A)`, `(CX)`, parenthesized noise. |
| Custom Channel Aliases (JSON) | textarea | *(empty)* | JSON object merged over built-in aliases. See [Custom Aliases](#custom-aliases). |

Plus dynamic per-country channel-database toggles (Enable US, UK, CA, DE, …) generated at runtime based on which `*_channels.json` files ship with the plugin.

## Actions

| Button | Type | What it does |
|---|---|---|
| ✅ Validate Settings | informational | Check settings and confirm DB connectivity |
| 📊 View Last Results | informational | Show summary of the last scan |
| 🔍 Scan Missing | informational | Find channels with EPG but no program data |
| 👁️ Preview Auto-Match | dry-run | Weighted-score every channel vs EPG candidates, export CSV, no changes applied |
| 🧹 Heal Preview | dry-run | Search for working replacements for broken EPG, export CSV |
| 📄 Export CSV | file write | Save the last scan results to `/data/exports/` |
| 🎯 Apply Auto-Match | destructive ✳ | Commit the Preview Auto-Match decisions (confidence ≥ threshold only) |
| 🧹 Apply Heal | destructive ✳ | Commit the heal replacements |
| 🏷️ Suffix Bad EPG | destructive ✳ | Rename channels with missing program data to include a visible marker |
| 👁️‍🗨️ Strip Hidden EPG | destructive ✳ | Remove EPG from every channel hidden in the selected profile |
| ❌ Remove Bad EPG | destructive ✳ | Remove EPG assignments from channels with missing program data |
| ❌ Remove by REGEX | destructive ✳ | Remove EPG from channels whose current EPG matches the REGEX |
| ❌ Remove All in Groups | destructive ✳ | Remove EPG from every channel in specified groups |
| 🗑️ Clear Exports | file cleanup ✳ | Delete this plugin's CSV export files |

✳ = confirmation dialog before execution.

## Custom Aliases

Override or extend the built-in alias table using the **Custom Channel Aliases (JSON)** setting. The field is a textarea — paste multi-line JSON freely:

```json
{
  "FOX News Channel": ["FOX NEWS HD", "FoxNews", "Fox News USA"],
  "HISTORY Channel, The": ["HISTORY", "History Channel HD"],
  "My Local Station": ["WABC", "WABC-TV", "ABC 7 New York"]
}
```

Keys are your **lineup/channel name** as Dispatcharr sees it. Values are arrays of variants that should be considered equivalent.

Custom aliases are merged on top of the 200+ built-ins, so you only need to specify additions or overrides. Malformed JSON is logged with a warning and ignored — the plugin falls back to built-ins only.

## How Matching Works

<details>
<summary><strong>Auto-Match scoring pipeline</strong></summary>

For each channel, EPG-Janitor computes two scores independently per candidate EPG entry and takes the higher one:

**Structural (weighted signals):**
- Callsign match (e.g. WABC ↔ WABC): **50 pts**
- State match: **30 pts** + city bonus **20 pts**
- Network keyword (ABC/NBC/CBS/FOX/PBS/CW/ION/MNT/IND in both names): **+10 pts** (only if other structural signals are already present)

**Fuzzy (Lineuparr-ported pipeline):**
- Stage 0: Alias table lookup (≥ 95 pts on hit)
- Stage 1: Exact match after normalization (100 pts)
- Stage 2: Substring match with length-ratio guard (≥ 0.75) and token-overlap guard
- Stage 3: Token-sort Levenshtein with length-scaled threshold (≥ 85, stricter for short names)

Regional differentiation: if either the lineup or the EPG carries an East/West/Pacific marker, candidates are filtered so East doesn't match West-only, Pacific is compatible with West, and so on.

Confidence caps at 100. The `Auto-Match Confidence Threshold` setting rejects anything below it. Only matches whose EPG has actual program data in the configured time window are applied.

</details>

<details>
<summary><strong>Scan & Heal pipeline</strong></summary>

1. Find channels whose current EPG assignment has no program data in the `Hours to Check Ahead` window.
2. For each broken channel, run the same matching pipeline against the `Heal Fallback EPG Sources` (or the channel's current source).
3. Walk ranked candidates; pick the first one ≥ `Heal Confidence Threshold` that actually has program data.
4. If nothing qualifies, leave the assignment unchanged and record the reason in the CSV.

</details>

## Troubleshooting

### First step: restart the container
**For any plugin issue:** refresh the browser (F5), then restart Dispatcharr:

```bash
docker restart dispatcharr
```

Dispatcharr's hot-reload sometimes leaves a stale Python module in memory after a plugin update. A hard restart is the most reliable way to apply a fresh version.

### Low match rate
- Confirm `ignore_quality_tags`, `ignore_regional_tags`, `ignore_geographic_tags`, `ignore_misc_tags` are all ON (default).
- Run **Preview Auto-Match** and inspect the CSV `match_method` column. Score 10 rows are network-keyword-only (generally unmatchable); score 30 is state-only; score 50 is fuzzy fallback.
- For channels that should match but don't, add a `custom_aliases` entry.

### False positives at score 100
- Check the CSV's `epg_channel_name` column. Common patterns:
  - **Rebrands** (DIY → Magnolia Network, EPIX → MGM+, MSNBC → MS NOW): correct by design. These reflect channel identity changes over time.
  - **Regional collapse** (HBO East → HBO, Cartoon Network West → Cartoon Network): expected when `ignore_regional_tags=true`. Set it to `false` for strict regional matching.
  - **Over-broad aliases**: remove with a targeted `custom_aliases` override that returns the channel to itself.

### "No matching EPG found" for a channel that clearly has EPG
- Verify the EPG entry has program data in the window set by `Hours to Check Ahead`. Without program data, matches are rejected unless `Allow EPG Without Program Data` is ON.
- Confirm the EPG source isn't excluded by `EPG Sources to Match`.

## File Locations

- **CSV Exports:** `/data/exports/epg_janitor_*.csv`
- **Plugin Directory:** `/app/plugins/epg-janitor/` (container path)
- **Logs:** `docker logs dispatcharr | grep -i "epg_janitor"`

## Version Scheme

Starting with 1.26.0 the plugin adopts a `1.26.{DDD}{HHMM}` version string (day-of-year + 24h local time), compatible with Lineuparr and Stream-Mapparr. Example: `1.26.1021323` = day 102 (Apr 12) at 13:23 local.

## Credits

- Fuzzy matching pipeline ported from the [Lineuparr](https://github.com/PiratesIRC/Dispatcharr-Lineuparr-Plugin) plugin
- Weighted structural scoring (callsign/state/city/network) is EPG-Janitor original
- Alias table seeded from Lineuparr's community-curated channel aliases

## License

MIT — see [LICENSE](LICENSE) if included.

---

*All product names, trademarks, and registered trademarks mentioned in this project are the property of their respective owners. Channel alias data is community-compiled from publicly available information and is not affiliated with or endorsed by any broadcaster.*

## Changelog

See the [Releases page](https://github.com/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin/releases) for version history. A concise Discord-formatted changelog for 1.26.0 is posted in the [plugin's Discord thread](https://discord.com/channels/1340492560220684331/1420051973994053848).

## Official Plugin Hub

EPG-Janitor is submitted to the [Dispatcharr Plugins](https://github.com/Dispatcharr/Plugins) official repository — see [PR #34](https://github.com/Dispatcharr/Plugins/pull/34). Once merged, you'll be able to install this plugin directly from Dispatcharr's Plugin Hub without downloading the zip manually.
