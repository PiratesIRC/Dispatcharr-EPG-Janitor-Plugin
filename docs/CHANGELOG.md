# Changelog

What changed in each version, described in terms of what you will notice rather
than which functions moved.

Versions use a `1.26.{DDD}{HHMM}` string: day-of-year plus 24-hour local time.
The [Releases page](https://github.com/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin/releases)
carries the downloadable archive for each.

## 1.26.2281111 — 16 August 2026

- **Channel names with a bracketed group in the middle now match correctly.**
  This is the same defect that 1.26.2241232 fixed for quality tags, in a second
  place that was missed. Removing a bracketed group such as `(Southern
  California)` or `(TEN)` removed the spaces around it too, so `Big Ten Network
  (Southern California) Alternate` became `Big 10 NetworkAlternate` and
  `Penthouse (TEN) On Demand` became `PenthouseOn Demand`. Two words glued
  together match nothing, and a single-word custom ignore tag could not reach a
  glued word either. Bracketed groups are now replaced with a space. Measured
  against every channel and guide name on a live installation: 101 of 25,231
  names normalise differently, every one of them a name that was previously
  glued, and no name loses or gains any text.
- **Failures are now visible instead of looking like success.** Every action
  that could fail returned its explanation in the field Dispatcharr renders as a
  green notice that closes itself after four seconds, and set nothing in the
  field it renders as a persistent red one. Forty such returns now populate
  both, so a failed run leaves a message on screen.
- **The help text under five settings was wrong or incomplete**, because it had
  been edited in the published manifest rather than in the code that Dispatcharr
  actually reads. Most visibly, the note explaining that leaving **EPG Sources
  to Match** empty will match foreign-country guides had never been shown to
  anyone. The two are now identical, and a test keeps them that way.

## 1.26.2241232 — 12 August 2026

- **Channel names with a quality tag in the middle now match correctly. This is
  the change that 1.26.2241113 said it made and did not.** Stripping a tag such
  as `FHD` or `[HD]` removed the spaces around it too, so `SKY NEWS FHD rec`
  became `SKY NEWSrec` and `CNN [HD] USA` became `CNNUSA`. Two words glued
  together match nothing, and a glued word could not be reached by a custom
  ignore tag either, so that setting appeared to do nothing on exactly the names
  the gluing had damaged. Tags are now replaced with a space. Measured against
  the shipped channel databases: 134 of 43,469 names normalise differently, all
  of them names that were previously glued.

## 1.26.2241113 — 12 August 2026

- **A new optional job keeps your guide from running dry: the EPG Freshness
  Watchdog.** Every few hours it checks each active EPG source and, if one is in
  error or its guide is about to run out, it re-triggers Dispatcharr's own
  refresh and writes what it did to System Events. It never edits channels and
  it is **off by default**. Five settings control it, under a new "EPG Freshness
  Watchdog" section: turn it on, how often it checks (6 hours), how close to
  running out a source has to be before it acts (12 hours), source IDs it must
  never touch, and whether to log successful repairs as well as failures. There
  is also a "Run EPG Watchdog Now" button if you would rather not wait for the
  schedule. After enabling it, click Validate Settings once to arm the schedule.

- **Every licensed US television station now anchors a match.** The allowlist
  that decides whether a callsign-shaped token is a real station used to be
  built only from the names inside the shipped channel databases, which covered
  2857 callsigns. It now also reads a shipped list of every callsign the FCC
  licenses, 3037 of them. The 397 stations that only the FCC knew about could
  not reach high confidence before and now can. Callsign-shaped English words
  such as `KILN` and `WHIP` are still rejected, and real stations whose callsign
  is an English word, such as `KING` and `WAVE`, are still accepted.

- **This version claimed to fix quality tags in the middle of a channel name. It
  did not.** The change was made in a component shared with the sibling plugins,
  but EPG Janitor keeps its own copy of the function in question, so the shared
  fix never ran here. Names such as `SKY NEWS FHD rec` still normalised to
  `SKY NEWSrec` in this version. It is genuinely fixed in 1.26.2241232 above.
  The entry is left here rather than deleted, because this version was released
  and published with the claim in it.

- **The front page is shorter and there is a proper user guide.** The README had
  grown into both an introduction and a full reference. The reference half now
  lives in `docs/USER-GUIDE.md`, which also covers the watchdog and the callsign
  allowlist, and this changelog is published alongside it.

## 1.26.1930615 — 12 July 2026

- **Invisible Unicode characters no longer break matching.** Zero-width
  formatting characters embedded in a channel name are stripped before
  comparison, so a name that looked identical but would not match now does.

## 1.26.1791309 — 28 June 2026

- **Rebrand and abbreviation aliases.** Common channel rebrands and
  abbreviations now resolve to their current EPG names: `FXM` to FX Movie
  Channel, `HBO2` to HBO Hits, `HBO Zone` to HBO Movies, `HBO Signature` to HBO
  Drama, `EPIX` to MGM+, `DIY` to Magnolia, `MoreMax` to Cinemax Hits.
- **Shared matcher core.** The fuzzy-matching primitives moved into a single
  shared component used across the sibling plugins, ending the drift between
  them. This is an internal change: matching behaviour is frozen by tests that
  fail if any result moves.

## 1.26.1711049, 1.26.1711217, 1.26.1711237 — 20 June 2026

Three release builds on one day. Packaging and version-consistency fixes; no
behaviour change.

## 1.26.1660712 — 15 June 2026

Matcher accuracy and coverage.

- **`CALLSIGN (NETWORK)` anchoring.** US over-the-air affiliates now match
  against feeds that name stations `KGTV (ABC)` or `WPLG-DT (CBS)`, the format
  used by sources such as jesmann-US.
- **Three-letter and word-shaped callsigns.** Grandfathered three-letter
  callsigns in parentheses (`(WWL)`, `(WJZ)`, `(KYW)`, `(WRC)`) and real
  word-shaped callsigns (`(KING)`, `(WAVE)`) now anchor to their `CALLSIGN-DT`
  EPG entries instead of being missed. This closed a gap that had left
  major-market affiliates in New Orleans, Baltimore, Philadelphia, Washington DC
  and Seattle unmatched.
- **Sibling-channel precision.** Numbered, time-shifted and ordinal siblings no
  longer cross-match: `Fox Sports 1` against `Fox Sports 2`, `BBC One` against
  `BBC Two`, `ITV2` against `ITV2 +1`.
- **Corrected similarity scoring.** The Levenshtein ratio now matches the
  standard definition, removing inflated scores that had let near-identical
  siblings slip past the threshold. The optional `rapidfuzz` library, when
  present, accelerates this by 20 to 50 times without changing any score.
- **Smarter name normalization.** Number words fold to digits (`BBC Three`
  equals `BBC 3`), CamelCase splits (`DangerTV` becomes `Danger TV`), dotted
  compounds split (`JusticeCentral.TV`), while radio frequencies such as `97.2`
  are preserved. Fixes a case where `USA Network` was over-stripped to
  `Network`. Streaming-platform source tags (Pluto, Tubi, Roku and similar) are
  stripped for matching.
- **Box-bar delimiters and non-ASCII names.** Names using Unicode box-bar
  prefixes, the `UK┃Discovery` and `US│ESPN` style used by some IPTV bouquets,
  have that prefix stripped for matching. Names in Cyrillic, CJK and Arabic are
  preserved through normalization instead of being blanked out, while the `+`
  brand marker in Discovery+ and Disney+ is kept.
- **Norway channel database** added.

## 1.26.1420824 — 22 May 2026

- **Adaptive action execution.** A long-running job no longer holds the browser
  request open. Fast jobs still return their result directly; slow ones continue
  in the background and report progress through the Status / Results action.
- Verified against Dispatcharr v0.25.

## 1.26.1021323, 1.26.1021336, 1.26.1021352 — 12 April 2026

The 1.26.0 rewrite.

- **New fuzzy matching pipeline** with an alias table, ported from the Lineuparr
  plugin: alias lookup, then exact, then substring, then token-sort comparison,
  with thresholds that tighten for short names.
- **EPG matching overhaul** combining that pipeline with weighted structural
  scoring over callsign, state, city and network.
- **Dispatcharr v0.20.0 interface**: section dividers, help text, placeholders,
  textarea inputs for multi-value fields, and colour-coded action buttons with
  confirmation dialogs.
- **Performance cache** for normalized names.
- Added a licence and the plugin metadata required for submission to the
  official Dispatcharr Plugins repository.

## 0.7.0a — 9 March 2026

Compatibility with the Dispatcharr 0.2x series.

## 0.6.1 — 17 December 2025

## 0.6.0 — 13 November 2025

Token caching for API access.

## 0.5 — 9 November 2025

Fixed the groups validation endpoint.

## 0.4 — 6 November 2025

**Scan & Heal** added: find channels whose EPG assignment has no program data
and replace it with a working alternative.

## 0.3 — 24 October 2025

## 0.2, 0.2.1 — 29 September 2025

## 0.1 — 23 September 2025

Initial release.
