#!/usr/bin/env python3
"""Refresh the public "EPGs Matched" badge on the README.

WHAT THIS DOES. Adds up how many guide assignments this plugin has written,
reading its own tally inside the Dispatcharr container, and writes a Shields.io
endpoint document to a GitHub Gist. The README badge points at that Gist, so this
script is what makes the public number change.

    python scripts/update_epgs_matched_badge.py            # refresh the Gist
    python scripts/update_epgs_matched_badge.py --dry-run  # print, write nothing
    python scripts/update_epgs_matched_badge.py --create   # first-time Gist setup
    python scripts/update_epgs_matched_badge.py --seed     # write the opening
                                                           # reconstruction, once

WHAT COUNTS AS ONE. One guide assignment written to one channel, confirmed by
Dispatcharr rather than counted from what the matcher proposed. Apply Auto-Match
and Apply Heal both contribute. A preview contributes nothing, because it writes
nothing. A channel re-assigned next month counts again: this is a total of work
performed, not a count of distinct channels that have a guide.

WHERE THE NUMBER COMES FROM. /data/epg_janitor_match_counts.jsonl inside the
container, one JSON object per finished apply, written by the plugin from a
finally block. A run whose tally write failed is missing: the plugin logs a
warning and carries on rather than failing an apply over a counter.

THE OPENING NUMBER IS A RECONSTRUCTION, NOT A MEASUREMENT. The tally starts
empty, so --seed writes one record built by counting rows in the CSV exports
already on disk: rows carrying an EPG id in an applied auto-match export, and
rows marked HEALED in a Scan and Heal export. Those files record what a run
DECIDED, not what Dispatcharr confirmed it wrote, and no count printed inside
them can be trusted either, because until 1.26.2481115 the line naming how many
assignments were written was itself wrong. The seed record says
reconstructed_from_exports in its own action field so the provenance survives.
Everything recorded after the seed is measured.

PRIVACY. The tally holds integers and one fixed action name. No channel name, no
group, no EPG source, no URL, no hostname. Only the summed integer reaches the
Gist. The Gist is unlisted rather than private and the README names it, so treat
the number as public.
"""
import argparse
import csv
import io
import json
import os
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent

CONTAINER = "dispatcharr"
LEDGER = "/data/epg_janitor_match_counts.jsonl"
EXPORTS_DIR = "/data/exports"
GIST_FILENAME = "epg-janitor-epgs-matched.json"
GIST_DESCRIPTION = "EPG Janitor EPGs-matched badge (Shields.io endpoint)"
BADGE_LABEL = "EPGs Matched"
BADGE_COLOUR = "blueviolet"

# gh is installed and authenticated but is NOT on PATH in either shell here, so
# `command -v gh` reports it missing and is not evidence. The path is built from
# LOCALAPPDATA rather than written out in full: this repository is public and a
# literal path names the Windows account for no benefit.
GH = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet",
                  "Packages",
                  "GitHub.cli_Microsoft.Winget.Source_8wekyb3d8bbwe",
                  "bin", "gh.exe")

# Where the Gist id is remembered between runs. It is committed, so a re-clone
# keeps updating the same document rather than silently creating a second one.
# The id is not a secret: the README badge URL names it.
GIST_ID_FILE = ROOT / "scripts" / ".epgs_matched_badge_gist"

# Which export names contributed a written assignment, and how to count one.
_APPLIED_AUTOMATCH = "epg_janitor_automatch_applied_"
_HEAL = "epg_janitor_heal_results_"


def sum_ledger(lines):
    """Total the tally. A damaged line is skipped rather than stopping the sum.

    A half-written record must not make a public number stop moving.
    """
    total = 0
    for line in lines:
        line = (line or "").strip()
        if not line:
            continue
        try:
            record = json.loads(line)
            total += int(record["assignments_written"])
        except (ValueError, TypeError, KeyError):
            continue
    return total


def count_assignments(filename, text):
    """Guide assignments one existing CSV export shows the run writing.

    Only the two export kinds that write an assignment are counted, and only
    this plugin's own files: the export directory is shared with five other
    plugins. The commented preamble is skipped, because a comment line counted
    as data would add a phantom assignment to a public number.
    """
    if filename.startswith(_APPLIED_AUTOMATCH):
        column, wanted = "epg_data_id", None
    elif filename.startswith(_HEAL):
        column, wanted = "status", "HEALED"
    else:
        return 0

    rows = [line for line in text.splitlines() if not line.startswith("#")]
    if not rows:
        return 0
    reader = csv.DictReader(io.StringIO(chr(10).join(rows)))
    if not reader.fieldnames or column not in reader.fieldnames:
        return 0

    counted = 0
    for row in reader:
        value = (row.get(column) or "").strip()
        if wanted is None:
            counted += 1 if value else 0
        else:
            counted += 1 if value == wanted else 0
    return counted


def _docker(*args, check=True):
    return subprocess.run(["docker", *args], capture_output=True, text=True,
                          check=check)


def read_ledger():
    result = _docker("exec", CONTAINER, "sh", "-c",
                     f"cat {LEDGER} 2>/dev/null || true", check=False)
    return result.stdout.splitlines()


def reconstruct_from_exports():
    """Count what the exports already on disk show was written.

    Returns (total, per-file detail) so the caller can print what it counted
    rather than announcing a number with no working shown.
    """
    listing = _docker("exec", CONTAINER, "sh", "-c",
                      f"ls -1 {EXPORTS_DIR} 2>/dev/null || true", check=False)
    detail = []
    total = 0
    for name in listing.stdout.split():
        if not (name.startswith(_APPLIED_AUTOMATCH) or name.startswith(_HEAL)):
            continue
        body = _docker("exec", CONTAINER, "cat", f"{EXPORTS_DIR}/{name}", check=False)
        counted = count_assignments(name, body.stdout)
        total += counted
        detail.append((name, counted))
    return total, detail


def seed(dry_run=False):
    """Write the one reconstructed opening record, if none exists yet."""
    existing = read_ledger()
    already = [line for line in existing
               if "reconstructed_from_exports" in line]
    if already:
        print("a reconstructed opening record already exists; not writing another")
        return 0

    total, detail = reconstruct_from_exports()
    for name, counted in detail:
        print(f"  {counted:6}  {name}")
    print(f"reconstructed opening total: {total}")
    if dry_run:
        print("dry run: nothing written")
        return total

    record = json.dumps({
        "ts": int(time.time()),
        "action": "reconstructed_from_exports",
        "assignments_written": total,
    })
    # Written as dispatch, never as root: docker exec defaults to root and would
    # leave a file the plugin's own workers cannot append to.
    _docker("exec", "-u", "dispatch", CONTAINER, "sh", "-c",
            f"printf '%s\\n' '{record}' >> {LEDGER}")
    print(f"seed record written to {LEDGER}")
    return total


def read_gist_id():
    if GIST_ID_FILE.exists():
        value = GIST_ID_FILE.read_text(encoding="utf-8").strip()
        if value:
            return value
    return None


def endpoint_document(total):
    return {
        "schemaVersion": 1,
        "label": BADGE_LABEL,
        "message": f"{total:,}",
        "color": BADGE_COLOUR,
    }


def publish(total, create=False, dry_run=False):
    document = json.dumps(endpoint_document(total), indent=2)
    if dry_run:
        print(document)
        return 0

    if not os.path.exists(GH):
        print(f"the GitHub CLI was not found at {GH}", file=sys.stderr)
        return 1

    tmp = ROOT / "scripts" / GIST_FILENAME
    tmp.write_text(document, encoding="utf-8")
    try:
        if create:
            result = subprocess.run(
                [GH, "gist", "create", str(tmp), "--desc", GIST_DESCRIPTION],
                capture_output=True, text=True)
            if result.returncode != 0:
                print(result.stderr, file=sys.stderr)
                return result.returncode
            url = result.stdout.strip().splitlines()[-1]
            gist_id = url.rstrip("/").split("/")[-1]
            GIST_ID_FILE.write_text(gist_id + chr(10), encoding="utf-8")
            print(f"created gist {gist_id}")
            print("badge URL:")
            print(f"  https://img.shields.io/endpoint?url=https://gist."
                  f"githubusercontent.com/PiratesIRC/{gist_id}/raw/{GIST_FILENAME}")
            return 0

        gist_id = read_gist_id()
        if not gist_id:
            print("no gist id recorded; run once with --create", file=sys.stderr)
            return 1
        result = subprocess.run(
            [GH, "gist", "edit", gist_id, "-f", GIST_FILENAME, str(tmp)],
            capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stderr, file=sys.stderr)
            return result.returncode
        print(f"gist {gist_id} updated to {total:,}")
        return 0
    finally:
        if tmp.exists():
            tmp.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would be published, write nothing")
    parser.add_argument("--create", action="store_true",
                        help="create the Gist for the first time")
    parser.add_argument("--seed", action="store_true",
                        help="write the reconstructed opening record, once")
    args = parser.parse_args(argv)

    if args.seed:
        seed(dry_run=args.dry_run)

    total = sum_ledger(read_ledger())
    print(f"total guide assignments written: {total:,}")
    return publish(total, create=args.create, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
