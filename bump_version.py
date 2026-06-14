#!/usr/bin/env python3
"""Bump EPG-Janitor version to 1.26.{DDD}{HHMM} in plugin.json, plugin.py,
and fuzzy_matcher.py (kept in lockstep — same scheme).
Run from repo root: python3 bump_version.py"""
import re, time, pathlib
v = f"1.26.{time.strftime('%j%H%M')}"
for p in ("EPG-Janitor/plugin.json", "EPG-Janitor/plugin.py", "EPG-Janitor/fuzzy_matcher.py"):
    # Only rewrite the version declaration (keyed) — never prose/docstrings or other 1.26.x fields.
    # Read/write as UTF-8 (fuzzy_matcher.py carries emoji/Unicode) and force LF
    # newlines so the .gitattributes LF policy doesn't surface a CRLF phantom diff.
    path = pathlib.Path(p)
    path.write_text(
        re.sub(r'((?:"version"|version|__version__)\s*[:=]\s*)"1\.26\.\d+"',
               rf'\g<1>"{v}"', path.read_text(encoding="utf-8")),
        encoding="utf-8", newline="\n")
print(v)
