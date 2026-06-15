# Development Workflow

This is the dev/contributor guide for **EPG-Janitor**, a Dispatcharr plugin.
It documents how to set up, test, lint, and ship changes. For *what the plugin
does* and its architecture, see [`README.md`](README.md) and
[`EPG-Janitor/CLAUDE.md`](EPG-Janitor/CLAUDE.md).

---

## TL;DR loop

```bash
python -m pip install -r requirements-dev.txt   # one time
python -m pytest tests                           # run the suite (fast, ~3s)
python -m ruff check EPG-Janitor tools tests     # lint
python bump_version.py                           # stamp a new version
# deploy: docker cp into the container, then docker restart (see below)
```

CI runs the same `ruff check` + `pytest --cov` on every push and PR
(`.github/workflows/ci.yml`), on Python 3.12 and 3.13.

---

## Setup

The plugin has **no _required_ runtime pip dependencies** — it runs inside
Dispatcharr, which supplies Django and the standard library. `fuzzy_matcher`
will use `rapidfuzz` for faster similarity **if it's importable**, falling back
to an identical pure-Python scorer otherwise. You only need dev dependencies to
run the tests and linter locally:

```bash
python -m pip install -r requirements-dev.txt
```

(`pytest`, `pytest-cov`, `hypothesis`, `ruff`, `rapidfuzz` — the latter so CI
exercises the accelerated path.)

---

## Testing

```bash
python -m pytest tests                       # all tests
python -m pytest tests --cov --cov-report=term-missing   # with coverage
python -m pytest tests/test_regressions.py   # one file
```

### What's testable offline, and what isn't

| Module | Django? | Tested |
|---|---|---|
| `fuzzy_matcher.py` | No | Yes — the matching engine, importable standalone |
| `progress_status.py` | No | Yes — pure progress/results helpers |
| `notification_text.py` | No | Yes — notification text helpers (char cap, filter phrasing) |
| `aliases.py`, `wildcard_match.py` | No | Yes |
| `plugin.py` | **Yes** (`apps.channels.models`, etc.) | **No** — needs a live Dispatcharr/Django runtime |

`tests/__init__.py` prepends `EPG-Janitor/` to `sys.path`, so tests import the
plugin modules directly (`import fuzzy_matcher`) without packaging.

**`plugin.py` cannot be unit-tested offline** because it imports Django models
at module load. The strategy for covering its logic is to **extract pure,
decision-only code into Django-free modules** and test those. `progress_status.py`
and `notification_text.py` are the existing examples of this pattern — when you
add logic to `plugin.py` that is pure (filtering, text building, scope
resolution, threshold decisions), prefer putting it in (or extracting it to) a
sibling module so it can have tests. Changes to `plugin.py` itself still require
manual verification in Dispatcharr (see Deploy).

### Regression tests are mandatory for fixed bugs

When you fix a matcher/logic bug, add a named test to
[`tests/test_regressions.py`](tests/test_regressions.py) that fails before the
fix and passes after. The bugs already encoded there (MeTV→WE tv alias false
positive, loose-word callsign mis-anchoring, wrong-market callsign rejection)
came from real production reports — see `.wolf/buglog.json`. The matcher's
thresholds are easy to regress while tuning; these tests are the safety net.

### Property-based tests

`tests/test_properties.py` uses Hypothesis to check invariants that must hold
for *all* inputs (similarity identity/symmetry/range, normalization
idempotence, "extracted callsign is never denylisted"). They skip automatically
if Hypothesis isn't installed.

---

## Linting

```bash
python -m ruff check EPG-Janitor tools tests          # check
python -m ruff check EPG-Janitor tools tests --fix     # auto-fix
```

Config lives in `pyproject.toml`. `E501` (line length) is ignored for now
because `plugin.py` has many long lines and isn't worth churning while it has
no test coverage — revisit once that changes.

---

## Versioning & releasing

Version scheme: `1.YY.{DDD}{HHMM}` (day-of-year + 24h local time), e.g.
`1.26.1411305` = day 141, 13:05. The string is carried **in lockstep** by
`plugin.json`, `plugin.py`, and `fuzzy_matcher.py`.

```bash
python bump_version.py    # stamps all three files with a fresh version
```

**Always run the test suite before bumping.** Release steps:

1. `python -m pytest tests` — green.
2. `python -m ruff check EPG-Janitor tools tests` — clean.
3. `python bump_version.py`.
4. Commit (`chore: bump version to <new>`).
5. Deploy (below) and smoke-test in Dispatcharr.

A `/release` helper skill that runs this sequence lives in
`.claude/skills/release/` (local tooling, not committed).

---

## Deploy / manual verification

There is no build step. To run a change against a live Dispatcharr:

```bash
docker cp EPG-Janitor/. <container>:/data/plugins/epg-janitor/
docker restart <container>
```

**Always hard-restart** — Dispatcharr's `.reload_token` mechanism leaves stale
bound methods in memory, so a reload alone won't pick up code changes reliably.

Every destructive action has a **preview / dry-run** counterpart — use those to
verify behavior before applying changes. First-run against a brand-new EPG
source: set **Allow EPG Without Program Data: True**, auto-match, refresh the
source, then optionally flip it back (Dispatcharr only imports program data for
already-mapped channels — see `EPG-Janitor/CLAUDE.md`).

---

## Offline matcher tuning (`tools/match_sim.py`)

`tools/match_sim.py` is an offline stream→channel match-simulation harness. It
reuses the live `fuzzy_matcher`/`aliases` modules (no Dispatcharr needed) so you
can iterate on matching against real exported data. See `tools/README.md`.

---

## Branching & PRs

- Branch off `main`; don't commit directly to `main`.
- Keep `.planning/` and `docs/` artifacts out of PRs — `docs/` is gitignored on
  purpose (internal dev notes), and so are `.claude/`, `.serena/`, and all
  `CLAUDE.md`/`GEMINI.md` files.
- CI (ruff + pytest on 3.12/3.13) must pass before merge.

---

## Repo conventions

- `snake_case` methods/variables, `PascalCase` classes, `_private` helpers,
  `UPPER_SNAKE_CASE` constants.
- Action methods are `*_action()`; every destructive action has a preview twin.
- Line endings are LF (enforced by `.gitattributes`).
- This repo uses OpenWolf for cross-session memory (`.wolf/`): check
  `.wolf/cerebrum.md` and `.wolf/buglog.json` before changing matcher logic —
  they record hard-won gotchas and past false positives.
