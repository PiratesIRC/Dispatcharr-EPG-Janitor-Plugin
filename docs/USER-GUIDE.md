# EPG Janitor user guide

The complete reference: every setting, every action, how matching decides what
to do, and what to check when the answer looks wrong.

The [project front page](../README.md) covers what the plugin is, requirements
and installation.

## Contents

- [Settings reference](#settings-reference)
- [Actions](#actions)
- [Custom aliases](#custom-aliases)
- [How matching works](#how-matching-works)
- [Troubleshooting](#troubleshooting)
- [File locations](#file-locations)
- [Version scheme](#version-scheme)

## Settings reference

| Setting | Type | Default | Description |
|---|---|---|---|
| Channel Profile Names | textarea | *(empty)* | Comma-separated profile names. Used by "Remove EPG from Hidden Channels". |
| Channel Groups | textarea | *(empty)* | Only process channels in these groups. Supports `*` / `?` wildcards (case-insensitive). Leave empty for all groups. |
| Ignore Groups | textarea | *(empty)* | Exclude channels in these groups. Supports `*` / `?` wildcards (case-insensitive). |
| EPG Sources to Match | textarea | *(empty)* | Comma-separated EPG source names, which act as a **filter**, not a priority list. Supports `*` / `?` wildcards (case-insensitive). **Empty = all active sources, including foreign-country ones**, and the matcher has no country awareness, so on a single-region install scope this to your region (e.g. `*-US`, `jesmann-US`, `epgshare locals`) or a UK/AU guide can land on a US channel (see [Foreign or wrong-country EPG on a channel](#foreign-or-wrong-country-epg-on-a-channel)). Disabled EPG sources are skipped; when multiple sources tie on score, the one with the higher **Dispatcharr priority** (set in Dispatcharr's EPG form) wins. |
| Hours to Check Ahead | number | `12` | Time window used to validate that a matched EPG carries program data. |
| Auto-Match Confidence Threshold | number | `95` | 0 to 100, higher is stricter. Matches below this score are rejected. |
| Allow EPG Without Program Data | boolean | `false` | When ON, auto-match accepts EPG entries with no current schedule. Turn ON the first time you auto-match against a freshly added EPG source: Dispatcharr only imports program data for EPG channels already mapped to a Dispatcharr channel, so a new source starts with zero programs and every match would otherwise be rejected. After auto-match assigns the EPG IDs, refresh the source to backfill program data, then turn this OFF again. |
| Heal Fallback EPG Sources | textarea | *(empty)* | Comma-separated sources heal is allowed to pick replacements from. Empty = channel's current source only. |
| Heal Confidence Threshold | number | `95` | Minimum replacement score during Scan & Heal. |
| EPG Name REGEX to Remove | string | *(empty)* | Python regex. Channels whose current EPG matches get their EPG removed. |
| Bad EPG Suffix | string | ` [BadEPG]` | Suffix appended to channels with missing program data. Leading space matters. |
| Also Remove EPG When Adding Suffix | boolean | `false` | When ON, the suffix action also strips the channel's EPG. |
| Ignore Quality Tags | boolean | `true` | Strip `[HD]`, `[4K]`, `[SD]`, `(Backup)` etc. before comparing names. |
| Ignore Regional Tags | boolean | `true` | Strip East/West/Pacific/etc. The regional filter still runs when a lineup explicitly carries a marker. |
| Ignore Geographic Prefixes | boolean | `true` | Strip `US:`, `UK:`, `[CA]` etc. |
| Ignore Miscellaneous Tags | boolean | `true` | Strip `(A)`, `(CX)`, parenthesized noise. |
| Custom Channel Aliases (JSON) | textarea | *(empty)* | JSON object merged over built-in aliases. See [Custom aliases](#custom-aliases). |
| Delete CSV Exports Older Than (Days) | number | `0` | Housekeeping for the CSV files this plugin writes to `/data/exports/`. After each export, this plugin's own exports older than this many days are deleted. `0` keeps every file, so nothing is removed unless you ask for it. The file just written is never deleted and at least one file always survives. Only files named `epg_janitor_*.csv` are considered, because that directory is shared with other plugins. 🗑️ Clear Exports ignores this setting and deletes them all. |

Plus dynamic per-country channel-database toggles (Enable US, UK, CA, DE, and the rest)
generated at runtime based on which `*_channels.json` files ship with the
plugin.

There is one further setting group, the EPG Freshness Watchdog, documented in
[its own section](#epg-freshness-watchdog).

## Actions

Buttons are ordered to follow the typical workflow. Each action shows its
results directly in the action card. A long-running job (large libraries) keeps
going in the background, so click **📊 Status / Results** to watch its progress and
see the results when it finishes.

Button colour tells you the consequence before you press anything:

| Colour | Meaning |
|---|---|
| red | Can remove a guide assignment you rely on. Always asks for confirmation. |
| orange | Writes data or clears state, but removes no guide assignment. |
| green | Runs an operation that writes no channel data. |
| blue | Reads and reports, changing nothing. |

| Button | Colour | What it does |
|---|---|---|
| ✅ Validate | blue | Check settings and confirm database connectivity |
| 🔍 Scan Missing | blue | Find channels with EPG but no program data |
| 📊 Status / Results | blue | Watch a running job's progress, or show the last scan's summary |
| 📄 Export CSV | green | Save the last scan results to `/data/exports/` |
| 👁️ Preview Auto-Match | blue | Weighted-score every channel against EPG candidates, export a CSV, apply nothing |
| 🎯 Apply Auto-Match | red ✳ | Commit the Preview Auto-Match decisions (confidence at or above the threshold only). This OVERWRITES an existing assignment, so a channel already on the right guide can be moved |
| 🧹 Preview Heal | blue | Search for working replacements for broken EPG, export a CSV |
| 🧹 Apply Heal | orange ✳ | Commit the heal replacements. It only touches assignments carrying no program data, and leaves a channel alone when it finds no replacement |
| 🏷️ Suffix Bad EPG | orange ✳ | Rename channels with missing program data to include a visible marker |
| ❌ Remove Bad EPG | red ✳ | Remove EPG assignments from channels with missing program data |
| 🙈 Strip Hidden EPG | red ✳ | Remove EPG from every channel hidden in the selected profile |
| ❌ Remove by REGEX | red ✳ | Remove EPG from channels whose current EPG matches the REGEX |
| ❌ Remove All in Groups | red ✳ | Remove EPG from every channel in specified groups |
| 🗑️ Clear Exports | orange ✳ | Delete every CSV export file this plugin has written. It ignores the retention setting and clears the lot |
| 🐕 Run Watchdog | green | Check every EPG source for freshness immediately, without waiting for the schedule |

✳ = confirmation dialog before execution.

**Every action listed here is manual.** Only the EPG Freshness Watchdog runs on
a schedule. There is no way to schedule auto-match, scan or heal.

## Custom aliases

Override or extend the built-in alias table using the **Custom Channel Aliases
(JSON)** setting. The field is a textarea, so paste multi-line JSON freely:

```json
{
  "FOX News Channel": ["FOX NEWS HD", "FoxNews", "Fox News USA"],
  "HISTORY Channel, The": ["HISTORY", "History Channel HD"],
  "My Local Station": ["WABC", "WABC-TV", "ABC 7 New York"]
}
```

Keys are your **lineup/channel name** as Dispatcharr sees it. Values are arrays
of variants that should be considered equivalent.

Custom aliases are merged on top of the 200+ built-ins, so you only need to
specify additions or overrides. Malformed JSON is logged with a warning and
ignored, and the plugin falls back to built-ins only.

**A custom alias entry REPLACES a built-in key rather than extending it.** If
you add an entry for a name that already has built-in variants, your list is the
whole list for that name. Lookup is case-sensitive on the exact channel name.

**Avoid bare acronyms and single words as variants.** An entry mapping a
network to a short token such as `MLB` will tie at 100 against any regional feed
whose name reduces to the same token, and the tie is broken by an internal
identifier rather than by which one you meant. Use specific variants.

## How matching works

<details>
<summary><strong>Auto-Match scoring pipeline</strong></summary>

For each channel, EPG Janitor computes two scores independently per candidate
EPG entry and takes the higher one:

**Structural (weighted signals):**
- Callsign match (e.g. WABC to WABC): **50 pts**
- State match: **30 pts** + city bonus **20 pts**
- Network keyword (ABC/NBC/CBS/FOX/PBS/CW/ION/MNT/IND in both names): **+10 pts** (only if other structural signals are already present)

**Callsign anchor (high confidence):** a callsign is *high confidence* when it
appears in parentheses (`ABC (WABC)`), at end-of-name (`WABC-DT`), or as the
leading token of a `CALLSIGN (NETWORK)` name (`KGTV (ABC)`, the format used by
feeds like jesmann-US, validated against the known-callsign allowlist described
below). When both sides share the same high-confidence callsign the match is
floored to **95**; a high-confidence callsign *disagreement* hard-rejects the
candidate. Loose mid-name tokens stay low confidence and never anchor. Both
4- and 3-letter parenthesized callsigns qualify (`(KTSM)`, `(WWL)`), and a
parenthesized callsign that is also an English word (`(KING)`, `(WAVE)`) is
anchored when the allowlist confirms it is a real station.

**Fuzzy pipeline:**
- Stage 0: Alias table lookup (≥ 90 pts on hit)
- Stage 1: Exact match after normalization (100 pts)
- Stage 2: Substring match with length-ratio guard (≥ 0.75) and token-overlap guard
- Stage 3: Token-sort Levenshtein, where similarity = 1 minus (distance divided by max length), matching rapidfuzz's definition, with a length-scaled threshold (≥ 85, stricter for short names)

**Sibling guards:** before scoring, numbered and time-shift siblings are
rejected: differing trailing numbers (`HBO 1` vs `HBO 2`), disjoint digit
tokens, `+1`/`+2` time-shift mismatches, and divergent numeric/ordinal tokens
(`BBC One` vs `BBC Two`), so near-identical sibling names cannot false-match.

Regional differentiation: if either the lineup or the EPG carries an
East/West/Pacific marker, candidates are filtered so East does not match
West-only, Pacific is compatible with West, and so on.

Confidence caps at 100. The `Auto-Match Confidence Threshold` setting rejects
anything below it. Only matches whose EPG has actual program data in the
configured time window are applied.

</details>

<details>
<summary><strong>The known-callsign allowlist</strong></summary>

A US callsign is K or W followed by two to four letters, which is the same shape
as many ordinary English words. Regex alone cannot tell `WABC` from `WITH`. The
plugin therefore keeps an allowlist of callsigns known to belong to real
stations, and consults it before promoting a callsign-shaped token to high
confidence.

The allowlist has two sources, merged:

1. **`us_station_callsigns.json`**, shipped with the plugin: every licensed US
   television callsign, built from the FACILITY table of the FCC Licensing and
   Management System. 3037 entries as of the 2026-08-10 dataset.
2. **The loaded channel databases**: the leading callsign of any name in station
   format, such as `KGTV (ABC)` or `WPLG-DT`. These contribute a further 189
   callsigns the FCC table does not list.

Two consequences worth knowing:

- A callsign-shaped English word that is not a real station, such as `KILN` or
  `WHIP`, is never promoted, no matter how the name is written.
- A real station whose callsign is also an English word, such as `KING`, `WAVE`
  or `WHO`, IS promoted when it appears in parentheses, because the allowlist
  vouches for it.

The file is rebuilt by a script in the repository and is not user-editable.

</details>

<details>
<summary><strong>Scan &amp; Heal pipeline</strong></summary>

1. Find channels whose current EPG assignment has no program data in the `Hours to Check Ahead` window.
2. For each broken channel, run the same matching pipeline against the `Heal Fallback EPG Sources` (or the channel's current source).
3. Walk ranked candidates; pick the first one ≥ `Heal Confidence Threshold` that actually has program data.
4. If nothing qualifies, leave the assignment unchanged and record the reason in the CSV.

</details>

<details>
<summary><strong>EPG source selection and priority</strong></summary>

`EPG Sources to Match` is a **filter**, not a priority list. It selects *which*
EPG sources are eligible (by exact name or `*` / `?` wildcard,
case-insensitive); leaving it empty uses all sources, **including
foreign-country sources. The matcher has no country or region gate, so scope
this filter for single-region installs** (see [Foreign or wrong-country EPG on a
channel](#foreign-or-wrong-country-epg-on-a-channel)). From the eligible set:

- **Disabled EPG sources are skipped.** Only sources enabled in Dispatcharr contribute candidate entries (mirrors Dispatcharr's own matcher).
- **Priority comes from Dispatcharr.** Candidates are ordered by each source's `priority` value (set in Dispatcharr's EPG form; higher number = higher priority). When two candidates tie on match score, the one from the higher-priority source wins; ties within the same priority keep their original order.

The run log shows a `Priority order (Dispatcharr):` line listing each source as
`<name> (<priority>)` and, if
any disabled source was filtered out, an `Excluded N EPG entries from inactive EPG
source(s)` line.

</details>

## EPG Freshness Watchdog

Dispatcharr's own EPG refresh has no retry and no freshness awareness: a source
that fails to refresh stays stale until someone notices, and a source whose
guide data runs out reports no error at all. The watchdog checks for both and
refreshes what it finds.

It is **off by default** and does nothing until enabled.

| Setting | Default | What it does |
|---|---|---|
| Enable Scheduled Watchdog | `false` | Master switch. Off means no schedule is created at all. Turning it on is not enough on its own: click ✅ Validate once afterwards, which is what arms the schedule. |
| Check Interval (Hours) | `6` | How often the scheduled check runs. |
| Refresh When Guide Ends Within (Hours) | `12` | A source with less than this much guide data remaining counts as stale. |
| Excluded EPG Source IDs | *(empty)* | Comma-separated EPG source ids the watchdog must never touch. |
| Log a System Event On Self-Heal | `true` | Also record an event when a source recovers, not only when it fails. |

What it does and does not do:

- It audits every active, non-dummy EPG source that has at least one channel mapped to it. A source with no mapped channels is ignored, because its guide data is not fetched in the first place.
- A source counts as stale when its status is an error, or when its remaining guide data falls inside the horizon threshold.
- Recovery is judged by **relative improvement**, an error clearing or the guide horizon advancing, rather than by the source reaching the threshold. A source that was two hours from empty and is now ten hours from empty has recovered, even though ten hours is still inside a twelve-hour threshold.
- It writes system events only. **There is no webhook, no email and no network code of any kind.**

**🐕 Run Watchdog** performs the same check immediately. It is worth
knowing that this button and the schedule take different routes through
Dispatcharr, so the button works even in configurations where scheduled plugin
tasks do not.

## Troubleshooting

### First step: restart the container

**For any plugin issue:** refresh the browser (F5), then restart Dispatcharr:

```bash
docker restart dispatcharr
```

Dispatcharr's hot-reload sometimes leaves a stale Python module in memory after
a plugin update. A hard restart is the most reliable way to apply a fresh
version.

### Low match rate

- Confirm `ignore_quality_tags`, `ignore_regional_tags`, `ignore_geographic_tags`, `ignore_misc_tags` are all ON (default).
- Run **Preview Auto-Match** and inspect the CSV `match_method` column. Score 10 rows are network-keyword-only (generally unmatchable); score 30 is state-only; score 50 is fuzzy fallback.
- For channels that should match but do not, add a `custom_aliases` entry.

### Auto-match skipped channels it should have processed

Auto-match is scoped by **both** `Channel Groups` **and** `Channel Profile
Names`. If a profile is set, only channels in that profile are considered, even
when the group filter would have included more. The run reports as a success
either way, so the skipped channels are silent.

Leave `Channel Profile Names` empty for a full run over the selected groups.

### False positives at score 100

- Check the CSV's `epg_channel_name` column. Common patterns:
  - **Rebrands** (DIY to Magnolia Network, EPIX to MGM+, MSNBC to MS NOW): correct by design. These reflect channel identity changes over time.
  - **Regional collapse** (HBO East to HBO, Cartoon Network West to Cartoon Network): expected when `ignore_regional_tags=true`. Setting it to `false` enables strict regional matching **only when the channel name itself carries a regional marker**. See the warning below.
  - **Over-broad aliases**: remove with a targeted `custom_aliases` override that returns the channel to itself.

### Foreign or wrong-country EPG on a channel

If a channel picks up a guide from the wrong country (for example a US channel
showing a UK schedule), the cause is almost always an **empty `EPG Sources to
Match`** filter. With it empty, *every* active EPG source is eligible, including
foreign-country ones, and the matcher has **no country or region awareness**, so
a channel whose exact name exists only in a foreign source (common for FAST and
single-show channels such as *Mythbusters*, *Ice Road Truckers*, *Modern
Marvels*) matches that foreign guide at 100%.

- **Fix:** set `EPG Sources to Match` to your region's sources (for example a comma list like `epgshare-US2, epgshare locals, epgshare-plex`), then re-run **👁️ Preview Auto-Match** to confirm and **🎯 Apply**. Re-running auto-match with the scoped filter also corrects channels that were previously assigned a foreign guide.
- **Name your good sources explicitly. A wildcard is not a filter.** A pattern like `*US*` also matches a source you meant to exclude, which quietly re-admits it to the candidate pool on the *next* run. If a source is bad, deactivate it rather than relying on the filter.
- **Run one region per pass.** Scoping the groups but leaving foreign sources in the pool still lets a US channel match a UK guide. Match US groups against US sources and UK groups against UK sources separately.
- **Check the CSV header.** Each export's `# EPG Sources to Match:` comment line shows what the run used. `(not set)` means it considered every source, foreign ones included.

> ⚠️ **Before a bulk 🎯 Apply Auto-Match on cable or premium channels, check the preview for East to Pacific moves.**
> Where a source carries both feeds (for example `HBO East` **and** `HBO (Pacific)`), a channel whose own name has **no** regional marker, plain `HBO`, `Bravo`, `TLC` or `Discovery Channel`, can be reassigned from the East feed to the Pacific one, shifting its whole guide by 2 to 3 hours. **`ignore_regional_tags=false` does not prevent this**, because the regional filter only engages when the *channel name* carries a regional marker to compare against.
> Auto-match **overwrites** any existing assignment scoring at or above the confidence threshold, so a healthy East assignment can be replaced. Read the **👁️ Preview** CSV first and confirm no `(Pacific)` or `(W)` targets appear for channels you already have working; if they do, apply selectively or pin those channels by hand.

### "No matching EPG found" for a channel that clearly has EPG

- Verify the EPG entry has program data in the window set by `Hours to Check Ahead`. Without program data, matches are rejected unless `Allow EPG Without Program Data` is ON.
- Confirm the EPG source is not excluded by `EPG Sources to Match`, and that the source is **enabled** in Dispatcharr. Disabled EPG sources are skipped entirely.

### A channel has no guide data, and there are three different reasons

1. **No EPG is assigned.** Match it.
2. **An EPG is assigned but the source was not refreshed afterwards.** Dispatcharr only imports program data for EPG entries that are already mapped to a channel, so a newly assigned entry has none until the source refreshes. Refresh the source.
3. **The upstream feed itself is frozen.** The source refreshes without error and the content never advances. Judging this from the source's status will not work, because a dead feed re-imports successfully forever.

### A channel looks completely unavailable in every source

Check for a rebrand before concluding a channel is not carried. Searching the
old name finds nothing while the channel is fully covered under the new one:
EPIX 2 became `MGM+ Hits HD`, Hallmark Drama became `Hallmark Mystery HD`.

Also check whether a time-shifted feed was matched instead of the main one. A
channel sitting on a `+1` feed has a guide that is correct but an hour out.

### The CSV says a channel has program data and it does not

`has_program_data` in the CSV export is not reliable while **Allow EPG Without
Program Data** is ON. In that mode it reports `Yes` with a `reason` column
reading `[program data check skipped]`. Turn the setting off and re-run to get a
real answer.

### Channels with a dummy EPG source look broken and are not

Dummy EPG program blocks are generated by the guide view as it renders, and are
never stored. Anything counting stored program rows sees zero for a dummy
channel even though the guide displays blocks normally. Scan & Heal reports
these channels as broken but correctly leaves them alone, recording
`NO_REPLACEMENT_FOUND`.

## File locations

- **CSV exports:** `/data/exports/epg_janitor_*.csv`
- **Plugin directory:** `/data/plugins/epg-janitor/` (container path)
- **Logs:** `docker logs dispatcharr | grep -i "epg_janitor"`

## Version scheme

Starting with 1.26.0 the plugin uses a `1.26.{DDD}{HHMM}` version string
(day-of-year plus 24-hour local time), compatible with the sibling plugins.
Example: `1.26.1021323` is day 102 (12 April) at 13:23 local time.
