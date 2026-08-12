#!/usr/bin/env python3
"""Rebuild EPG-Janitor/us_station_callsigns.json from an FCC LMS database dump.

WHAT THE FILE IS FOR. FuzzyMatcher._get_known_callsigns builds an allowlist of
real US station callsigns and uses it in two places: it promotes a leading
"CALLSIGN (NETWORK)" token to high confidence (Priority 3), and it rescues a
callsign that is also a common English word when that word appears in
parentheses (Priorities 1 and 1b). Both need MEMBERSHIP only, never a station
record, so this file is a sorted list of callsigns and nothing else.

Until 2026-08-12 the allowlist was derived only from the station-format names
inside the shipped channel databases, which yielded 2857 callsigns against the
3037 the FCC licenses. The 397 that only the FCC knows about could not reach
high confidence at all.

WHERE THE INPUT COMES FROM. The FACILITY table of the FCC Licensing and
Management System, downloaded by hand from

    https://enterpriseefiling.fcc.gov/dataentry/public/tv/lmsDatabase.html

as a dated zip such as 08-10-2026_LMS_Dump.zip. Unpack it and point this script
at the facility.dat inside. Measured on the 2026-08-10 dump: 180831 records, 32
pipe delimited columns, a header row, and a row terminator of "^|" followed by a
newline. It covers every broadcast service, so AM and FM radio are the bulk.

THE SELECTION RULES, and why this is shorter than the sibling plugin's builder.
Channel-Maparr builds a LOOKUP TABLE keyed by base callsign, so it must parse
the network affiliation field, refuse to let a vague affiliation overwrite a
specific one, and stop an unaffiliated record shadowing a real affiliate that
shares its base callsign. None of that applies to a membership set: a set holds
no affiliation and cannot shadow anything. What remains is:

1. Television services only. The rest of the dump is AM and FM radio.

2. Licensed facilities only. Every other status is an application, a
   cancellation or a void record.

3. The callsign must be K or W followed by two to four letters, optionally with
   a broadcast suffix. This also disposes of cancelled licences for free: the
   FCC republishes a cancelled licence with a "D" prepended to the callsign, and
   a D-prefixed callsign cannot match a pattern anchored on K or W. Measured on
   the 2026-08-10 dump: zero such records reach the pattern.

4. Never drop a callsign the previous file had. A rebuild that silently removes
   a working station is a regression rather than an upgrade, and the FCC data is
   not maintained to a standard: the sibling plugin measured 65 stations present
   but no longer licensed and 7 absent altogether between two dumps. Carried
   entries are listed separately so the count is visible rather than implied.

The output is written with LF line endings because .gitattributes pins the data
files to LF, and a CRLF rewrite breaks a hash-pinned test on Linux while looking
correct on Windows.

Usage:
    python scripts/build_station_callsigns.py <path-to-facility.dat> [--dry-run]
"""
import argparse
import json
import pathlib
import re
import sys

# Row terminator used by the LMS dump. It is not a plain newline, and splitting
# on a newline silently produces garbage columns rather than an error.
ROW_TERMINATOR = "^|\n"

# Television service codes. Everything else in the dump is radio.
TV_SERVICE_CODES = frozenset({"DTV", "DCA", "LPD", "LPT", "LPX", "TV", "TX", "ACA"})

# Only a licensed facility is a station.
LICENSED_STATUS = "LICEN"

# A US television callsign, with the broadcast suffix stripped. Anchored on K or
# W, which is what makes rule 3 above dispose of cancelled D-prefixed records.
BASE_CALLSIGN = re.compile(r"^([KW][A-Z]{2,4})(?:-(?:TV|CD|LP|DT|LD|FM|AM)\d?)?$")

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
OUTPUT = REPO_ROOT / "EPG-Janitor" / "us_station_callsigns.json"


def parse_dump(path):
    """Return the set of licensed television base callsigns in the dump."""
    text = path.read_text(encoding="utf-8", errors="replace")
    rows = text.split(ROW_TERMINATOR)
    header = rows[0].split("|")
    column = {name: i for i, name in enumerate(header)}
    for required in ("callsign", "service_code", "facility_status"):
        if required not in column:
            raise SystemExit(f"column {required!r} missing: this does not look like facility.dat")

    callsigns = set()
    considered = 0
    for row in rows[1:]:
        cells = row.split("|")
        if len(cells) < len(header):
            continue
        considered += 1
        if cells[column["service_code"]].strip().upper() not in TV_SERVICE_CODES:
            continue
        if cells[column["facility_status"]].strip().upper() != LICENSED_STATUS:
            continue
        match = BASE_CALLSIGN.match(cells[column["callsign"]].strip().upper())
        if match:
            callsigns.add(match.group(1))
    return callsigns, considered


def load_previous():
    """Return the callsigns in the existing output file, or an empty set."""
    if not OUTPUT.exists():
        return set()
    data = json.loads(OUTPUT.read_text(encoding="utf-8"))
    return set(data.get("callsigns", [])) | set(data.get("carried_over", []))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("facility_dat", help="path to facility.dat from an unpacked LMS dump")
    parser.add_argument("--dry-run", action="store_true", help="report without writing")
    args = parser.parse_args()

    path = pathlib.Path(args.facility_dat)
    if not path.exists():
        raise SystemExit(f"no such file: {path}")

    licensed, considered = parse_dump(path)
    previous = load_previous()
    carried = sorted(previous - licensed)
    added = sorted(licensed - previous)

    print(f"records considered:      {considered}")
    print(f"licensed TV callsigns:   {len(licensed)}")
    print(f"previous file held:      {len(previous)}")
    print(f"new in this dump:        {len(added)}")
    print(f"carried over, no longer licensed: {len(carried)}")
    if carried:
        print("   " + ", ".join(carried[:20]) + (" ..." if len(carried) > 20 else ""))

    payload = {
        "_source": f"FCC LMS FACILITY table, {path.name}",
        "_what": "Base callsigns of licensed US television stations. Membership only: "
                 "FuzzyMatcher._get_known_callsigns uses this to vouch that a "
                 "callsign-shaped token is a real station. Rebuild with "
                 "scripts/build_station_callsigns.py; do not hand-edit.",
        "callsigns": sorted(licensed),
        "carried_over": carried,
    }
    text = json.dumps(payload, indent=1, ensure_ascii=False) + "\n"

    encoded = text.encode("utf-8")
    if args.dry_run:
        print(f"\ndry run, not written. would be {len(encoded)} bytes")
        return 0

    OUTPUT.write_bytes(encoded)
    print(f"\nwrote {OUTPUT} ({len(encoded)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
