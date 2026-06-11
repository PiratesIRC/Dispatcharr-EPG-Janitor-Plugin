"""Offline stream -> channel match-simulation harness for EPG-Janitor.

Standalone developer tool. NOT part of the shipped plugin package.
Imports the live fuzzy_matcher / aliases modules in-place so simulations
always reflect current matcher code.
"""
import argparse
import csv
import io
import json
import logging
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_PLUGIN_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "EPG-Janitor")
)
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)

from aliases import CHANNEL_ALIASES  # noqa: E402
from fuzzy_matcher import FuzzyMatcher  # noqa: E402

_EXTINF_RE = re.compile(r'^#EXTINF:[^,]*,(?P<name>.*)$')
_ATTR_RE = re.compile(r'(?P<key>[\w-]+)="(?P<val>[^"]*)"')


@dataclass
class StreamEntry:
    display_name: str
    tvg_name: str
    group_title: str
    tvg_id: str

    @property
    def query_name(self) -> str:
        return self.display_name or self.tvg_name


def parse_m3u(text: str) -> list[StreamEntry]:
    text = text.lstrip("﻿")
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("#EXTINF:"):
            continue
        m = _EXTINF_RE.match(line)
        if not m:
            continue
        display_name = m.group("name").strip()
        attrs = {a.group("key"): a.group("val") for a in _ATTR_RE.finditer(line)}
        entries.append(StreamEntry(
            display_name=display_name,
            tvg_name=attrs.get("tvg-name", ""),
            group_title=attrs.get("group-title", ""),
            tvg_id=attrs.get("tvg-id", ""),
        ))
    return entries


_CHANNEL_COL_CANDIDATES = ("channel_name", "channel name", "name")


def parse_channels_csv(text: str, channel_col: str = None) -> list:
    text = text.lstrip("﻿")
    data_lines = [ln for ln in text.splitlines() if not ln.lstrip().startswith("#")]
    if not data_lines:
        raise ValueError("CSV has no non-comment rows")
    reader = csv.DictReader(io.StringIO("\n".join(data_lines)))
    headers = reader.fieldnames or []
    if channel_col is not None:
        if channel_col not in headers:
            raise ValueError(
                f"--channel-col {channel_col!r} not in CSV headers: {headers}"
            )
        col = channel_col
    else:
        col = next(
            (h for h in headers if h.strip().lower() in _CHANNEL_COL_CANDIDATES),
            None,
        )
        if col is None:
            raise ValueError(
                f"Could not auto-detect a channel-name column in {headers}; "
                f"pass --channel-col"
            )
    seen, out = set(), []
    for row in reader:
        name = (row.get(col) or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return out


_LOG = logging.getLogger("match_sim")


def build_alias_map(custom_aliases_text: str) -> dict:
    effective = dict(CHANNEL_ALIASES)
    raw = (custom_aliases_text or "").strip()
    if not raw:
        return effective
    try:
        custom = json.loads(raw)
    except (json.JSONDecodeError, TypeError, ValueError):
        _LOG.warning("custom_aliases is not valid JSON; using built-ins only")
        return effective
    if not isinstance(custom, dict):
        _LOG.warning(
            "custom_aliases must be a JSON object, got %s; using built-ins only",
            type(custom).__name__,
        )
        return effective
    for key, value in custom.items():
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            _LOG.warning("custom_aliases entry %r is not a list of strings; skipping", key)
            continue
        effective[key] = list(value)
    return effective


def simulate(channel_names: list, stream_names: list, matcher,
             alias_map: dict, user_ignored_tags: list) -> dict:
    """Return {stream_name: [(channel, score, match_type), ...] sorted desc}.

    Channels are the query (alias_map is keyed by canonical channel names),
    streams are candidates. Results are inverted into a per-stream view; for
    a given stream the same channel may appear at most once (best score kept).
    """
    matcher.precompute_normalizations(list(channel_names) + list(stream_names))
    # stream -> {channel: (score, mtype)}  (keep best score per channel)
    acc = {s: {} for s in stream_names}
    for channel in channel_names:
        ranked = matcher.match_all_streams(
            channel, stream_names, alias_map,
            channel_number=None, user_ignored_tags=user_ignored_tags,
            min_score=0,
        )
        for stream_name, score, mtype in ranked:
            if stream_name not in acc:
                continue
            prev = acc[stream_name].get(channel)
            if prev is None or score > prev[0]:
                acc[stream_name][channel] = (score, mtype)
    per_stream = {}
    for stream_name in stream_names:
        rows = [
            (ch, sc, mt) for ch, (sc, mt) in acc[stream_name].items()
        ]
        rows.sort(key=lambda r: r[1], reverse=True)
        per_stream[stream_name] = rows
    return per_stream


def write_reports(per_stream, out_root, threshold, margin, top_n, run_config):
    out_dir = Path(out_root) / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True, exist_ok=True)

    def best(rows):
        return rows[0] if rows else None

    type_counts = Counter()
    hist = Counter()
    n_pass = n_low = n_unmatched = 0

    with (out_dir / "per_stream_matches.csv").open("w", newline="") as f, \
         (out_dir / "unmatched.csv").open("w", newline="") as fu, \
         (out_dir / "low_confidence.csv").open("w", newline="") as fl, \
         (out_dir / "top_n.csv").open("w", newline="") as ft:
        w = csv.writer(f)
        wu = csv.writer(fu)
        wl = csv.writer(fl)
        wt = csv.writer(ft)
        w.writerow(["stream_name", "best_channel", "score", "match_type",
                    "threshold", "passed"])
        wu.writerow(["stream_name"])
        wl.writerow(["stream_name", "best_channel", "score", "match_type"])
        wt.writerow(["stream_name", "rank", "candidate", "score", "match_type"])

        for stream_name, rows in per_stream.items():
            b = best(rows)
            if b is None:
                n_unmatched += 1
                w.writerow([stream_name, "", "", "", threshold, False])
                wu.writerow([stream_name])
                continue
            ch, sc, mt = b
            passed = sc >= threshold
            w.writerow([stream_name, ch, sc, mt, threshold, passed])
            type_counts[mt] += 1
            hist[min(int(sc) // 10 * 10, 100)] += 1
            if passed:
                n_pass += 1
            elif sc >= threshold - margin:
                n_low += 1
                wl.writerow([stream_name, ch, sc, mt])
            for rank, (c, s, m) in enumerate(rows[:top_n], start=1):
                wt.writerow([stream_name, rank, c, s, m])

    total = len(per_stream)
    matched = total - n_unmatched
    rate = (matched / total * 100) if total else 0.0
    lines = [
        f"Total streams: {total}",
        f"Matched (>=1 candidate): {matched} ({rate:.1f}%)",
        f"Passed threshold ({threshold}): {n_pass}",
        f"Low confidence [{threshold - margin},{threshold}): {n_low}",
        f"Unmatched: {n_unmatched}",
        "",
        "By match_type: " + ", ".join(
            f"{k}={v}" for k, v in sorted(type_counts.items())
        ),
        "Score histogram (10-pt buckets): " + ", ".join(
            f"{b}-{b + 9}:{hist[b]}" for b in sorted(hist)
        ),
        "",
        "Run config: " + ", ".join(
            f"{k}={v}" for k, v in sorted(run_config.items())
        ),
    ]
    (out_dir / "summary.txt").write_text("\n".join(lines) + "\n")
    return out_dir


def _read(path):
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


def main(argv=None):
    p = argparse.ArgumentParser(description="EPG-Janitor stream->channel match simulation")
    p.add_argument("--channels", required=True)
    p.add_argument("--streams", required=True)
    p.add_argument("--threshold", type=int, default=80)
    p.add_argument("--top-n", type=int, default=5)
    p.add_argument("--margin", type=int, default=15)
    p.add_argument("--channel-col", default=None)
    p.add_argument("--group-filter", default=None)
    p.add_argument("--custom-aliases", default=None)
    p.add_argument("--countries", default=None,
                   help="Comma-separated country codes; empty string loads none")
    p.add_argument("--out", default=os.path.join("tools", "sim-out"))
    for tag in ("quality", "regional", "geographic", "misc"):
        p.add_argument(f"--ignore-{tag}", dest=f"ignore_{tag}",
                       action="store_true", default=True)
        p.add_argument(f"--no-ignore-{tag}", dest=f"ignore_{tag}",
                       action="store_false")
    args = p.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s %(message)s")

    try:
        channels_text = _read(args.channels)
        streams_text = _read(args.streams)
    except OSError as e:
        _LOG.error("Cannot read input: %s", e)
        return 2

    try:
        channel_names = parse_channels_csv(channels_text, args.channel_col)
    except ValueError as e:
        _LOG.error("Channel CSV error: %s", e)
        return 2

    entries = parse_m3u(streams_text)
    if args.group_filter:
        try:
            rx = re.compile(args.group_filter)
        except re.error as e:
            _LOG.error("Invalid --group-filter regex: %s", e)
            return 2
        entries = [e for e in entries if rx.search(e.group_title)]
    stream_names = []
    seen = set()
    for e in entries:
        q = e.query_name.strip()
        if q and q not in seen:
            seen.add(q)
            stream_names.append(q)

    if not channel_names:
        _LOG.error("No channel names parsed")
        return 2
    if not stream_names:
        _LOG.error("No stream names after parsing/filter")
        return 2

    custom_text = _read(args.custom_aliases) if args.custom_aliases else ""
    alias_map = build_alias_map(custom_text)

    user_ignored_tags = [
        t for t in ("quality", "regional", "geographic", "misc")
        if getattr(args, f"ignore_{t}")
    ]

    matcher = FuzzyMatcher(plugin_dir=_PLUGIN_DIR,
                           match_threshold=args.threshold, logger=_LOG)
    # FuzzyMatcher.__init__ does NOT auto-load country DBs, and the
    # match_all_streams pipeline (alias/exact/substring/fuzzy) does not consult
    # them (they only feed the legacy callsign path). Only load DBs when the
    # user explicitly names countries; an empty/omitted --countries skips load.
    if args.countries:
        codes = [c.strip().upper() for c in args.countries.split(",") if c.strip()]
        if codes:
            matcher.reload_databases(country_codes=codes)

    per_stream = simulate(channel_names, stream_names, matcher,
                          alias_map, user_ignored_tags)

    run_config = {
        "threshold": args.threshold, "margin": args.margin,
        "top_n": args.top_n,
        "ignored_tags": "|".join(user_ignored_tags) or "none",
        "alias_entries": len(alias_map),
        "channels": len(channel_names), "streams": len(stream_names),
    }
    out_dir = write_reports(per_stream, args.out, args.threshold,
                            args.margin, args.top_n, run_config)
    _LOG.info("Reports written to %s", out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
