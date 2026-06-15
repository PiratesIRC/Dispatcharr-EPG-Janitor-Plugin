EPG Janitor — keep your Electronic Program Guide clean, accurate, and complete.

FEATURES
- Auto-Match EPG to channels using callsign/location/network scoring + Lineuparr-style fuzzy pipeline (alias, exact, substring, token-sort) with ~200 built-in aliases
- Callsign anchoring incl. the leading CALLSIGN (NETWORK) format (e.g. KGTV (ABC), as used by jesmann-US), gated on a known-callsign allowlist; numbered/time-shift sibling guards prevent cross-matches (Fox Sports 1 vs 2, ITV2 vs ITV2 +1)
- Scan & Heal broken EPG assignments with ranked-fallback replacement
- EPG source selection by name or * / ? wildcard; only enabled sources used, score ties resolved by Dispatcharr source priority (higher wins)
- Find channels with EPG assigned but no program data ("No Program Information Available")
- Bulk operations: remove EPG by REGEX, from hidden channels, or from entire groups
- Suffix-tag channels with missing program data for easy visual flagging
- Per-category normalization toggles (quality, regional, geographic, misc)
- Custom alias JSON for user overrides
- CSV exports for every scan/match run

Requires Dispatcharr v0.20.0+.

Full documentation, release notes, and issue tracker:
https://github.com/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin
