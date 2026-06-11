# tools/match_sim.py — Stream→Channel match simulation

Offline developer tool (not shipped in the plugin package). Drives the real
`FuzzyMatcher` over an EPG-Janitor CSV export + a provider `.m3u` to produce
tuning reports.

## Usage

    python3 tools/match_sim.py \
      --channels path/to/epg_janitor_export.csv \
      --streams  path/to/provider.m3u \
      [--threshold 80] [--top-n 5] [--margin 15] \
      [--channel-col "Channel Name"] [--group-filter REGEX] \
      [--custom-aliases aliases.json] \
      [--countries US,UK] \
      [--no-ignore-regional]   # toggles: quality/regional/geographic/misc \
      [--out tools/sim-out]

Defaults mirror the plugin's production defaults. Reports land in
`tools/sim-out/<timestamp>/`: `per_stream_matches.csv`, `unmatched.csv`,
`low_confidence.csv`, `top_n.csv`, `summary.txt`.

Channels are the matcher query (the alias table is keyed by canonical channel
names); results are inverted to a per-stream view.

Note: a stream that scores above zero but below `threshold - margin` appears
only in `per_stream_matches.csv` (with `passed=False`) — not in
`unmatched.csv` (zero candidates) nor `low_confidence.csv` (the borderline
band). Treat `per_stream_matches.csv` as the complete truth table.
