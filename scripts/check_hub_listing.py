"""Compare the Dispatcharr Plugin Hub listing against what this plugin ships.

Run this BEFORE opening a pull request against Dispatcharr/Plugins. A standard
mode listing is a copy of the plugin's source inside the Hub repository, made
from a file list, and a file list can be incomplete. Two failure modes:

- a missing MODULE fails at import, so a Hub install does not load at all;
- a missing DATA FILE usually degrades quietly, which is worse to diagnose.

Measured 2026-08-12: the listing carried 24 files against 26 shipped. Absent were
epg_watchdog.py, which plugin.py imports unconditionally, and
us_station_callsigns.json. The listing was internally consistent because it pinned
an older version predating both, so the omission would only have caused harm at the
moment of a version bump. That is exactly when this script is meant to be run.

tests/test_shipped_files.py checks the same requirement offline against git. This
checks the Hub, which needs the network, so it is a script rather than a test.

Usage:
    python scripts/check_hub_listing.py

Reads the Hub over the public API; no token needed for a public repository, but
one is used when GITHUB_TOKEN is set, because unauthenticated requests are rate
limited. Exits non-zero when the listing would ship an incomplete plugin.
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

HUB_REPO = "Dispatcharr/Plugins"
SLUG = "epg-janitor"
PACKAGE = "EPG-Janitor"


def hub_api(path):
    request = urllib.request.Request(
        f"https://api.github.com/repos/{HUB_REPO}/{path}",
        headers={"Accept": "application/vnd.github+json",
                 "User-Agent": "epg-janitor-hub-check"})
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        request.add_header("Authorization", f"token {token}")
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def git_text(*args):
    """Run git and decode as UTF-8 explicitly.

    Never pass text=True here. On Windows that decodes with the cp1252 default
    and plugin.json contains emoji, which raises UnicodeDecodeError inside a
    reader thread and leaves stdout as None, so the failure surfaces later as a
    confusing TypeError rather than at the read.
    """
    raw = subprocess.run(["git", *args], capture_output=True, check=True).stdout
    return raw.decode("utf-8")


def shipped_files():
    out = git_text("ls-tree", "--name-only", f"HEAD:{PACKAGE}")
    return {line.strip() for line in out.splitlines() if line.strip()}


def main():
    try:
        listing = hub_api(f"contents/plugins/{SLUG}")
    except urllib.error.HTTPError as exc:
        print(f"could not read the Hub listing: HTTP {exc.code}")
        return 2
    except urllib.error.URLError as exc:
        print(f"could not reach the Hub: {exc.reason}")
        return 2

    hub_names = {entry["name"] for entry in listing}
    manifest = next((e for e in listing if e["name"] == "plugin.json"), None)
    if manifest is None:
        print("the listing has no plugin.json, so it is not a listing this script understands")
        return 2

    ours = shipped_files()

    # source_type decides whether the source files even belong in the listing.
    raw = urllib.request.urlopen(manifest["download_url"], timeout=30).read()
    hub_manifest = json.loads(raw.decode("utf-8"))
    source_type = hub_manifest.get("source_type", "local")
    hub_version = hub_manifest.get("version")

    local_version = json.loads(
        git_text("show", f"HEAD:{PACKAGE}/plugin.json"))["version"]

    print(f"Hub listing : {len(hub_names)} file(s), version {hub_version}, source_type {source_type}")
    print(f"this plugin : {len(ours)} file(s), version {local_version}")
    print()

    if source_type == "external":
        print("External mode: the Hub downloads the release archive, so the file")
        print("list above does not need to match. Check instead that source_url")
        print("resolves for the version being published, and that no source files")
        print("were left behind by a previous standard-mode listing:")
        leftovers = sorted(hub_names - {"plugin.json", "README.md", "logo.png"})
        if leftovers:
            print(f"  LEFTOVER source files still in the listing: {leftovers}")
            return 1
        print("  no leftover source files")
        return 0

    missing = sorted(ours - hub_names)
    stale = sorted(hub_names - ours)

    if missing:
        print("MISSING from the Hub listing (this plugin ships them):")
        for name in missing:
            note = " <-- imported by plugin.py; a Hub install FAILS AT IMPORT without it" \
                if name.endswith(".py") else ""
            print(f"  {name}{note}")
    else:
        print("nothing missing from the Hub listing")

    if stale:
        print("\nIn the Hub listing but no longer shipped (delete these):")
        for name in stale:
            print(f"  {name}")

    if hub_version == local_version and (missing or stale):
        print("\nNote: the versions already match, so the listing claims to be current"
              "\nwhile its file set is not.")

    return 1 if (missing or stale) else 0


if __name__ == "__main__":
    sys.exit(main())
