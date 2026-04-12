#!/usr/bin/env python3
"""Bump EPG-Janitor version to 1.26.{DDD}{HHMM} in plugin.json and plugin.py.
Run from repo root: python3 bump_version.py"""
import re, time, pathlib
v = f"1.26.{time.strftime('%j%H%M')}"
for p in ("EPG-Janitor/plugin.json", "EPG-Janitor/plugin.py"):
    pathlib.Path(p).write_text(re.sub(r"1\.26\.\d+", v, pathlib.Path(p).read_text()))
print(v)
