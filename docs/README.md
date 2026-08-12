# EPG Janitor documentation

Three pages, split by who is reading.

Everything else in this folder is a working note kept out of the published
repository on purpose.

## If you are running Dispatcharr

**[User guide](USER-GUIDE.md)** is the one you want. It holds the complete
settings and action reference, how the matcher decides what to assign, what the
known-callsign allowlist does and why callsign-shaped English words are
rejected, how the optional EPG Freshness Watchdog behaves, where every file is
written, and a troubleshooting section arranged by symptom.

Two entries in that troubleshooting section are worth reading before your first
bulk run rather than after: the warning about channels being moved from East
feeds to Pacific feeds, which shifts a guide by two to three hours, and the one
about an empty **EPG Sources to Match** filter letting a foreign guide land on a
local channel.

**[Changelog](CHANGELOG.md)** lists what changed in each version, described in
terms of what you will notice rather than which functions moved.

## If you are working on EPG Janitor itself

**[Contributing guide](../CONTRIBUTING.md)** covers the development setup, the
test suite, and how changes are expected to arrive.

The plugin runs inside Dispatcharr's Django backend and cannot be run
standalone. There is no build step.

## If you are reading the matcher

The name-normalization and similarity primitives live in a shared component,
`matching_core.py`, which is vendored into each of the sibling plugins
byte-identically. It is not edited in this repository: a change is made once in
the shared source and re-vendored, and a test fails if this copy ever diverges
from its recorded hash.

EPG Janitor keeps its own name normalization for over-the-air names, its own
four-priority callsign ladder and its own single-digit token-overlap guard. Those
three legitimately differ from the sibling plugins and are not candidates for
sharing.

---

The **[project front page](../README.md)** describes what the plugin is and what
it does.
