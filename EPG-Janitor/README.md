# EPG Janitor

Keep your Electronic Program Guide clean, accurate, and complete. EPG Janitor operates on channels that already exist in Dispatcharr — it finds broken EPG assignments (no program data), intelligently matches EPGs to channels using callsign/location/network scoring plus a fuzzy pipeline with built-in aliases, and provides bulk cleanup tools for removing EPG from hidden channels or by REGEX.

**Source repo:** https://github.com/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin
**Discord thread:** https://discord.com/channels/1340492560220684331/1420051973994053848

## Requires

Dispatcharr v0.20.0 or newer. Python 3.13+ (bundled). No required dependencies (optionally uses `rapidfuzz` for faster matching if it's present in the environment).

## Key features

- **Auto-Match EPG** — weighted structural scoring (callsign 50 / state 30 / city 20 / network 10) + Lineuparr-style 4-stage fuzzy pipeline (alias → exact → substring → token-sort), takes the higher score. Identical-name matches score 100.
- **Callsign anchoring** — high-confidence US callsign matching for parenthesized (`ABC (WABC)`), end-of-name (`WABC-DT`), and leading `CALLSIGN (NETWORK)` forms (jesmann-US: `KGTV (ABC)`), gated on a known-callsign allowlist from the loaded DBs so callsign-shaped words aren't promoted. A shared high-confidence callsign anchors the match; a disagreement rejects a wrong-station candidate.
- **Sibling guards & smarter normalization** — numbered/time-shift siblings no longer cross-match (`Fox Sports 1`≠`2`, `BBC One`≠`Two`, `ITV2`≠`ITV2 +1`); number-words fold to digits (`BBC Three`=`BBC 3`), CamelCase and dotted compounds split (`97.2` preserved). Similarity is rapidfuzz-parity with optional `rapidfuzz` acceleration.
- **Scan & Heal** — find channels whose current EPG has no program data and walk ranked candidates for a working replacement (respects fallback source allowlist).
- **EPG source selection & priority** — pick eligible sources by name or `*`/`?` wildcard (case-insensitive); only enabled sources are used, and score ties resolve by each source's Dispatcharr `priority` (higher wins).
- **~200 built-in aliases** (FS1/FS2, CSPAN variants, rebrands like EPIX→MGM+, MSNBC→MS NOW, getTV→GREATTV, DIY→Magnolia, Hallmark Movies & Mysteries→Hallmark Mystery, Justice Network→True Crime Network). User-extendable via a JSON `custom_aliases` setting.
- **Regional differentiation** (East/West/Pacific, Pacific ≡ West) — lineup channels with regional markers only match compatible EPG feeds, even when `ignore_regional_tags=true`.
- **Per-category normalization toggles** — quality (`[HD]`, `[4K]`), regional (East/West/Pacific), geographic (`US:`, `[CA]`), misc (`(A)`, `(CX)`) stripped independently.
- **Performance** — pre-normalization cache + per-EPG attribute cache. ~7–8 min for a 21,480-EPG × 2,950-channel run.
- **Bulk management** — remove EPG by REGEX, from hidden channels, or from entire groups. Tag channels with missing program data via configurable suffix.
- **CSV exports** — every dry-run and apply exports results with confidence scores, match method, and reasoning.

## Settings

Organized into sections via UI dividers: Scope, Auto-Match, Scan & Heal, Cleanup & Maintenance, Normalization Toggles, Custom Aliases. Dynamic per-country channel-database toggles (US, UK, CA, DE, ES, FR, IN, MX, NL, AU, BR, NO) auto-generated based on shipped `*_channels.json` files.

## Actions

14 color-coded action buttons grouped by destructiveness (blue outlines for info, cyan for dry-runs, green-filled for apply-style, orange/red-filled for destructive) with confirmation dialogs on anything that mutates channel state. Emoji labels.

## How it differs from other matching plugins

- **Not a channel creator.** EPG Janitor does not create channels or scan M3U sources — it works on channels you already have in Dispatcharr. For provider-lineup-driven channel creation see [Lineuparr](https://github.com/PiratesIRC/Dispatcharr-Lineuparr-Plugin).
- **EPG-first matching.** The weighted pipeline is tuned for matching EPG entries (which often carry callsigns + geographic context for US broadcast) rather than IPTV stream names.
- **Heal semantics.** First-class support for replacing broken EPG assignments with working ones — walks ranked candidates and validates program-data availability before applying.

## Install

Install from the Dispatcharr Plugin Hub (once available) or download the latest release from the source repo and import via **Plugins → Import Plugin** in the Dispatcharr UI.

## License

MIT © 2026 PiratesIRC

---

*All product names, trademarks, and registered trademarks mentioned in this project are the property of their respective owners. Channel alias data is community-compiled from publicly available information and is not affiliated with or endorsed by any broadcaster.*
