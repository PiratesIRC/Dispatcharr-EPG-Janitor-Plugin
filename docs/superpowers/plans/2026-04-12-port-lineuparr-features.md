# Port Lineuparr Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port Lineuparr's fuzzy matcher (aliases, ranked matches, caching, regional differentiation), its EPG-matching pipeline improvements, and its Dispatcharr v0.20.0+ GUI customizations into EPG-Janitor while preserving EPG-Janitor's per-category normalization toggles and richer pattern sets.

**Architecture:** Hybrid port. Lineuparr's `fuzzy_matcher.py` becomes the base; EPG-Janitor's richer bracketed/parenthesized pattern regexes are merged in. `aliases.py` is new, copied wholesale. Two plugin.py code paths are refactored (`_auto_match_channels` / `_find_best_epg_match` and the heal flow) to use the new `match_all_streams()` ranked API. A legacy `fuzzy_match()` wrapper keeps the 12 other actions untouched. `plugin.json` gains `min_dispatcharr_version`, a `custom_aliases` field, button styling/confirms/emoji. New `tests/test_fuzzy_matcher.py` covers the matcher with stdlib `unittest`.

**Tech Stack:** Python 3.13 stdlib only. `unittest` for tests. No external deps, no build, no lint.

---

## Environment note

**This directory is NOT currently a git repository** (verified in project memory). The commit steps below use `git` commands for convention and in case the user initializes a repo. If the workspace remains non-git, skip the commit steps. None of the test or implementation steps depend on git.

**Spec reference:** `docs/superpowers/specs/2026-04-12-port-lineuparr-features-design.md`

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `EPG-Janitor/aliases.py` | **create** | Built-in channel alias table (`CHANNEL_ALIASES` dict) |
| `EPG-Janitor/fuzzy_matcher.py` | **rewrite** | 4-stage matching pipeline, caching, regional differentiation, legacy `fuzzy_match()` wrapper |
| `EPG-Janitor/plugin.py` | **modify** | Refactor `_auto_match_channels` + `_find_best_epg_match` (auto-match) and `_scan_and_heal_*` (heal). 12 other action methods untouched. |
| `EPG-Janitor/plugin.json` | **modify** | Bump version to `0.8.0`, add `min_dispatcharr_version`, add `custom_aliases` field, enrich 14 actions with `button_variant`/`button_color`/`confirm`/emoji labels |
| `EPG-Janitor/CLAUDE.md` | **modify** | Add "Upgrade notes" section for 0.8.0 behavior changes |
| `tests/__init__.py` | **create** | Empty-but-present package marker that adds `EPG-Janitor/` to `sys.path` for test imports |
| `tests/test_fuzzy_matcher.py` | **create** | ~30–50 unit tests (unittest) for matcher behavior |

Working directory for all paths: `/home/user/docker/EPG-Janitor/`.

---

## Task 1: Test scaffold

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_fuzzy_matcher.py` (smoke test only for now)

- [ ] **Step 1: Create tests/__init__.py**

Create `/home/user/docker/EPG-Janitor/tests/__init__.py`:

```python
"""Test package for EPG-Janitor.

Prepends the plugin directory to sys.path so tests can import
`fuzzy_matcher`, `aliases`, etc. as top-level modules.
"""
import os
import sys

_PLUGIN_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "EPG-Janitor")
)
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)
```

- [ ] **Step 2: Create smoke test**

Create `/home/user/docker/EPG-Janitor/tests/test_fuzzy_matcher.py`:

```python
"""Unit tests for EPG-Janitor's fuzzy_matcher module."""
import unittest


class TestImport(unittest.TestCase):
    def test_module_imports(self):
        import fuzzy_matcher  # noqa: F401


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run the smoke test to verify it passes**

Run: `cd /home/user/docker/EPG-Janitor && python -m unittest discover tests -v`
Expected: `test_module_imports ... ok` (the existing `fuzzy_matcher.py` still loads).

- [ ] **Step 4: Commit**

```bash
cd /home/user/docker/EPG-Janitor
git add tests/__init__.py tests/test_fuzzy_matcher.py
git commit -m "test: add unittest scaffold for fuzzy_matcher"
```

---

## Task 2: Create aliases.py

**Files:**
- Create: `EPG-Janitor/aliases.py`
- Modify: `tests/test_fuzzy_matcher.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_fuzzy_matcher.py`:

```python
class TestAliases(unittest.TestCase):
    def test_aliases_module_exports_channel_aliases_dict(self):
        import aliases
        self.assertIsInstance(aliases.CHANNEL_ALIASES, dict)
        self.assertGreater(len(aliases.CHANNEL_ALIASES), 100)

    def test_alias_values_are_lists_of_strings(self):
        import aliases
        for key, value in aliases.CHANNEL_ALIASES.items():
            self.assertIsInstance(key, str)
            self.assertIsInstance(value, list)
            for item in value:
                self.assertIsInstance(item, str)

    def test_known_alias_present(self):
        import aliases
        self.assertIn("FOX News Channel", aliases.CHANNEL_ALIASES)
        self.assertIn("FNC", aliases.CHANNEL_ALIASES["FOX News Channel"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/user/docker/EPG-Janitor && python -m unittest tests.test_fuzzy_matcher.TestAliases -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'aliases'`.

- [ ] **Step 3: Copy aliases.py from Lineuparr**

Copy the file wholesale:

```bash
cp /home/user/docker/Lineuparr/Lineuparr/aliases.py /home/user/docker/EPG-Janitor/EPG-Janitor/aliases.py
```

No edits needed — the Lineuparr file already exports `CHANNEL_ALIASES`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/user/docker/EPG-Janitor && python -m unittest tests.test_fuzzy_matcher.TestAliases -v`
Expected: three `ok`.

- [ ] **Step 5: Commit**

```bash
cd /home/user/docker/EPG-Janitor
git add EPG-Janitor/aliases.py tests/test_fuzzy_matcher.py
git commit -m "feat: add built-in channel aliases table (port from Lineuparr)"
```

---

## Task 3: Rewrite fuzzy_matcher.py — baseline (Lineuparr port + merged EPG-Janitor patterns)

**Files:**
- Modify (replace contents): `EPG-Janitor/fuzzy_matcher.py`
- Modify: `tests/test_fuzzy_matcher.py`

This task replaces the existing 750-line matcher with Lineuparr's 635-line baseline, but merges in EPG-Janitor's richer `QUALITY_PATTERNS`, `REGIONAL_PATTERNS`, `GEOGRAPHIC_PATTERNS`, `MISC_PATTERNS` regex variants so current EPG-Janitor behavior on bracketed and parenthesized tags is preserved.

- [ ] **Step 1: Write failing tests for pattern coverage**

Append to `tests/test_fuzzy_matcher.py`:

```python
class TestNormalizationPatterns(unittest.TestCase):
    """Verify merged pattern set strips what EPG-Janitor 0.7.0a stripped
    AND what Lineuparr strips."""

    def setUp(self):
        import fuzzy_matcher
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=80)

    # EPG-Janitor legacy coverage
    def test_strips_bracketed_4k(self):
        self.assertEqual(self.m.normalize_name("CNN [4K]").strip().lower(), "cnn")

    def test_strips_bracketed_unknown_lowercase(self):
        self.assertEqual(self.m.normalize_name("CNN [unknown]").strip().lower(), "cnn")

    def test_strips_parenthesized_backup(self):
        self.assertEqual(self.m.normalize_name("CNN (Backup)").strip().lower(), "cnn")

    def test_strips_single_letter_tag(self):
        self.assertEqual(self.m.normalize_name("CNN (A)").strip().lower(), "cnn")

    def test_strips_cx_tag(self):
        self.assertEqual(self.m.normalize_name("Cinemax (CX)").strip().lower(), "cinemax")

    def test_strips_us_prefix(self):
        self.assertEqual(self.m.normalize_name("US: CNN").strip().lower(), "cnn")

    # Lineuparr new coverage
    def test_strips_8k(self):
        self.assertEqual(self.m.normalize_name("CNN 8K").strip().lower(), "cnn")

    def test_strips_pacific(self):
        self.assertEqual(
            self.m.normalize_name("HBO Pacific", ignore_regional=True).strip().lower(),
            "hbo",
        )

    def test_strips_provider_prefix_us_pipe(self):
        self.assertEqual(self.m.normalize_name("US | CNN").strip().lower(), "cnn")

    # Regional toggle behavior (from spec)
    def test_preserves_east_when_ignore_regional_true(self):
        # EPG-Janitor 0.7.0a stripped " East" even with ignore_regional=True;
        # Lineuparr/new behavior preserves East/West as feed distinguishers.
        # Spec §Regional: ignore_regional_tags=True → strip ALL regional variants.
        # This test locks in the SPEC behavior (strip East when True).
        result = self.m.normalize_name("HBO East", ignore_regional=True).strip().lower()
        self.assertEqual(result, "hbo")

    def test_preserves_east_when_ignore_regional_false(self):
        result = self.m.normalize_name("HBO East", ignore_regional=False).strip().lower()
        self.assertIn("east", result)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/user/docker/EPG-Janitor && python -m unittest tests.test_fuzzy_matcher.TestNormalizationPatterns -v`
Expected: Multiple failures — the current 0.7.0a matcher doesn't strip `(Backup)`, `8K`, `Pacific`, or `US |` prefixes.

- [ ] **Step 3: Replace fuzzy_matcher.py with the merged baseline**

Do this in three sub-steps:

  - **3a.** Start from Lineuparr's file:
    ```bash
    cp /home/user/docker/Lineuparr/Lineuparr/fuzzy_matcher.py /home/user/docker/EPG-Janitor/EPG-Janitor/fuzzy_matcher.py
    ```

  - **3b.** Merge pattern sets using the Edit tool. Open `EPG-Janitor/fuzzy_matcher.py` and replace the five pattern constants (`QUALITY_PATTERNS`, `REGIONAL_PATTERNS`, `GEOGRAPHIC_PATTERNS`, `PROVIDER_PREFIX_PATTERNS`, `MISC_PATTERNS`) with the merged versions below. These combine Lineuparr's patterns with EPG-Janitor's bracketed/parenthesized variants that Lineuparr's consolidated patterns miss.

    ```python
    # Merged pattern set — Lineuparr base + EPG-Janitor bracketed variants.
    # All patterns applied with re.IGNORECASE in normalize_name().

    QUALITY_PATTERNS = [
        # Bracketed: [4K], [UHD], [FHD], [HD], [SD], [FD], [8K], [Unknown], [Unk], [Slow], [Dead], [Backup]
        r'\s*\[(4K|8K|UHD|FHD|HD|SD|FD|Unknown|Unk|Slow|Dead|Backup)\]\s*',
        # Parenthesized
        r'\s*\((4K|8K|UHD|FHD|HD|SD|FD|Unknown|Unk|Slow|Dead|Backup)\)\s*',
        # Start of string
        r'^\s*(4K|8K|UHD|FHD|HD|SD|FD|Unknown|Unk|Slow|Dead)\b\s*',
        # End of string
        r'\s*\b(4K|8K|UHD|FHD|HD|SD|FD|Unknown|Unk|Slow|Dead)$',
        # Middle (with word boundary padding)
        r'\s+\b(4K|8K|UHD|FHD|HD|SD|FD|Unknown|Unk|Slow|Dead)\b\s+',
        # Trailing colon form: "HD:", "4K:"
        r'\b(?:4K|8K|UHD|FHD|HD|SD|FD|Unknown|Unk|Slow|Dead):\s',
    ]

    REGIONAL_PATTERNS = [
        # East/West are conditionally stripped by the ignore_regional flag in normalize_name().
        # The patterns here target Pacific/Central/Mountain/Atlantic, which are always
        # stripped when ignore_regional=True but never distinguish separate feeds.
        r'\s[Pp][Aa][Cc][Ii][Ff][Ii][Cc]',
        r'\s[Cc][Ee][Nn][Tt][Rr][Aa][Ll]',
        r'\s[Mm][Oo][Uu][Nn][Tt][Aa][Ii][Nn]',
        r'\s[Aa][Tt][Ll][Aa][Nn][Tt][Ii][Cc]',
        r'\s*\([Pp][Aa][Cc][Ii][Ff][Ii][Cc]\)\s*',
        r'\s*\([Cc][Ee][Nn][Tt][Rr][Aa][Ll]\)\s*',
        r'\s*\([Mm][Oo][Uu][Nn][Tt][Aa][Ii][Nn]\)\s*',
        r'\s*\([Aa][Tt][Ll][Aa][Nn][Tt][Ii][Cc]\)\s*',
    ]

    REGIONAL_EAST_WEST_PATTERNS = [
        # Stripped only when ignore_regional=True (EPG-Janitor default).
        # When ignore_regional=False, East/West are preserved so the regional
        # differentiation filter in match_all_streams() can act on them.
        r'\s[Ee][Aa][Ss][Tt]\b',
        r'\s[Ww][Ee][Ss][Tt]\b',
        r'\s*\([Ee][Aa][Ss][Tt]\)\s*',
        r'\s*\([Ww][Ee][Ss][Tt]\)\s*',
    ]

    GEOGRAPHIC_PATTERNS = [
        # Bracket/delimiter country-code prefixes
        r'\b[A-Z]{2,3}:\s*',
        r'\b[A-Z]{2,3}\s*-\s*',
        r'\|[A-Z]{2,3}\|\s*',
        r'\[[A-Z]{2,3}\]\s*',
        # EPG-Janitor legacy: bare "US " / "USA " at word boundary
        r'\bUSA?:\s',
        r'\bUSA?\s',
    ]

    PROVIDER_PREFIX_PATTERNS = [
        r'^(?:US|USA|UK|CA|AU|FR|DE|ES|IT|NL|BR|MX|IN)\s*[:\-\|]\s*',
        r'^\s*\((?:US|USA|UK|CA|AU|FR|DE|ES|IT|NL|BR|MX|IN)\)\s*',
        r'\s*\|\s*(?:US|USA|UK|CA|AU|FR|DE|ES|IT|NL|BR|MX|IN)\s*$',
    ]

    MISC_PATTERNS = [
        # Single-letter parenthesized tags: (A), (B), (C)
        r'\s*\([A-Z]\)\s*',
        # Cinemax/specialty
        r'\s*\(CX\)\s*',
        # Any remaining parenthesized group (broad Lineuparr-style fallback)
        r'\s*\([^)]*\)\s*',
    ]
    ```

  - **3c.** In the `normalize_name()` method, find the block that applies `REGIONAL_PATTERNS` when `ignore_regional` is truthy and extend it to ALSO apply `REGIONAL_EAST_WEST_PATTERNS` only when `ignore_regional` is truthy. Use the Edit tool to locate the existing `REGIONAL_PATTERNS` loop inside `normalize_name()` and add the East/West loop immediately after:

    ```python
    if ignore_regional:
        for pattern in REGIONAL_PATTERNS:
            name = re.sub(pattern, ' ', name, flags=re.IGNORECASE)
        for pattern in REGIONAL_EAST_WEST_PATTERNS:
            name = re.sub(pattern, ' ', name, flags=re.IGNORECASE)
    ```

- [ ] **Step 4: Run all pattern tests to verify they pass**

Run: `cd /home/user/docker/EPG-Janitor && python -m unittest tests.test_fuzzy_matcher.TestNormalizationPatterns -v`
Expected: all tests pass.

- [ ] **Step 5: Run full suite to catch regressions**

Run: `cd /home/user/docker/EPG-Janitor && python -m unittest discover tests -v`
Expected: all previous tests still pass; `fuzzy_matcher` module still imports; `CHANNEL_ALIASES` still loads.

- [ ] **Step 6: Commit**

```bash
cd /home/user/docker/EPG-Janitor
git add EPG-Janitor/fuzzy_matcher.py tests/test_fuzzy_matcher.py
git commit -m "refactor(fuzzy_matcher): port Lineuparr base + merge EPG-Janitor patterns"
```

---

## Task 4: Normalization caching + `precompute_normalizations()`

**Files:**
- Modify: `tests/test_fuzzy_matcher.py`
- Confirm present: `EPG-Janitor/fuzzy_matcher.py` (already inherited from Lineuparr port in Task 3)

The Lineuparr port already includes `_norm_cache`, `_norm_nospace_cache`, `_processed_cache`, `precompute_normalizations()`, `_get_cached_norm()`, `_get_cached_processed()`. This task locks in behavior with tests.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_fuzzy_matcher.py`:

```python
class TestCaching(unittest.TestCase):
    def setUp(self):
        import fuzzy_matcher
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=80)

    def test_precompute_populates_norm_cache(self):
        names = ["CNN [HD]", "Fox News", "ESPN 2"]
        self.m.precompute_normalizations(names)
        self.assertEqual(len(self.m._norm_cache), 3)
        for name in names:
            self.assertIn(name, self.m._norm_cache)

    def test_precompute_clears_prior_state(self):
        self.m.precompute_normalizations(["CNN [HD]"])
        self.m.precompute_normalizations(["BBC News"])
        self.assertEqual(len(self.m._norm_cache), 1)
        self.assertNotIn("CNN [HD]", self.m._norm_cache)
        self.assertIn("BBC News", self.m._norm_cache)

    def test_cached_norm_matches_ondemand_norm(self):
        name = "CNN [HD]"
        self.m.precompute_normalizations([name])
        cached, _ = self.m._get_cached_norm(name)
        live = self.m.normalize_name(name).lower()
        self.assertEqual(cached, live)

    def test_cached_nospace_is_stripped(self):
        self.m.precompute_normalizations(["Fox News"])
        _, nospace = self.m._get_cached_norm("Fox News")
        self.assertNotIn(" ", nospace)

    def test_short_names_excluded_from_cache(self):
        # Names that normalize to <2 chars are skipped per _get_cached_norm logic.
        self.m.precompute_normalizations(["X"])
        self.assertNotIn("X", self.m._norm_cache)
```

- [ ] **Step 2: Run tests to verify they pass (already implemented via port)**

Run: `cd /home/user/docker/EPG-Janitor && python -m unittest tests.test_fuzzy_matcher.TestCaching -v`
Expected: all tests pass.

If any test fails, the cache implementation from Lineuparr didn't port cleanly — inspect `EPG-Janitor/fuzzy_matcher.py` and fix. Do not move on until all pass.

- [ ] **Step 3: Commit**

```bash
cd /home/user/docker/EPG-Janitor
git add tests/test_fuzzy_matcher.py
git commit -m "test(fuzzy_matcher): lock in precompute_normalizations cache behavior"
```

---

## Task 5: Alias stage (stage 0)

**Files:**
- Modify: `tests/test_fuzzy_matcher.py`
- Confirm present: `EPG-Janitor/fuzzy_matcher.py` (`alias_match()` method inherited from Lineuparr port)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_fuzzy_matcher.py`:

```python
class TestAliasStage(unittest.TestCase):
    def setUp(self):
        import fuzzy_matcher
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=80)
        self.alias_map = {
            "FOX News Channel": ["Fox News", "FNC", "FOX NEWS"],
            "HISTORY Channel, The": ["HISTORY", "History Channel HD"],
        }

    def test_alias_hits_exact_variant(self):
        result = self.m.alias_match(
            "FOX News Channel",
            ["Fox News"],
            self.alias_map,
        )
        self.assertIsNotNone(result)
        matched, score, match_type = result
        self.assertEqual(matched, "Fox News")
        self.assertEqual(match_type, "alias")
        self.assertGreaterEqual(score, 95)

    def test_alias_miss_when_variant_not_in_candidates(self):
        result = self.m.alias_match(
            "FOX News Channel",
            ["CNN", "ESPN"],
            self.alias_map,
        )
        self.assertIsNone(result)

    def test_alias_empty_map_returns_none(self):
        result = self.m.alias_match("FOX News Channel", ["Fox News"], {})
        self.assertIsNone(result)

    def test_alias_unknown_query_returns_none(self):
        result = self.m.alias_match("Unknown Channel", ["Fox News"], self.alias_map)
        self.assertIsNone(result)
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd /home/user/docker/EPG-Janitor && python -m unittest tests.test_fuzzy_matcher.TestAliasStage -v`
Expected: all pass.

If `alias_match` raises or returns an unexpected shape, consult `/home/user/docker/Lineuparr/Lineuparr/fuzzy_matcher.py` lines ~300-377 and align the method signature.

- [ ] **Step 3: Commit**

```bash
cd /home/user/docker/EPG-Janitor
git add tests/test_fuzzy_matcher.py
git commit -m "test(fuzzy_matcher): lock in alias_match stage 0 behavior"
```

---

## Task 6: Length-scaled threshold + token-overlap guard

**Files:**
- Modify: `tests/test_fuzzy_matcher.py`
- Confirm present: `EPG-Janitor/fuzzy_matcher.py` (helpers inherited from Lineuparr port)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_fuzzy_matcher.py`:

```python
class TestLengthScaledThreshold(unittest.TestCase):
    def setUp(self):
        import fuzzy_matcher
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=80)

    def test_short_name_gets_strict_threshold(self):
        t = self.m._length_scaled_threshold(80, 4)
        self.assertGreaterEqual(t, 95)

    def test_medium_name_gets_moderate_threshold(self):
        t = self.m._length_scaled_threshold(80, 8)
        self.assertGreaterEqual(t, 90)
        self.assertLess(t, 95)

    def test_long_name_uses_base_threshold(self):
        t = self.m._length_scaled_threshold(80, 20)
        self.assertEqual(t, 80)


class TestTokenOverlap(unittest.TestCase):
    def setUp(self):
        import fuzzy_matcher
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=80)

    def test_basic_overlap_requires_one_shared_long_token(self):
        self.assertTrue(self.m._has_token_overlap("america racing", "america bbc"))

    def test_basic_no_overlap_when_only_stopwords_shared(self):
        self.assertFalse(self.m._has_token_overlap("the one show", "the big bang"))

    def test_majority_mode_requires_majority_overlap(self):
        self.assertTrue(
            self.m._has_token_overlap("america racing sports", "america racing news", mode="majority")
        )
        self.assertFalse(
            self.m._has_token_overlap("america racing", "america bbc", mode="majority")
        )
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd /home/user/docker/EPG-Janitor && python -m unittest tests.test_fuzzy_matcher.TestLengthScaledThreshold tests.test_fuzzy_matcher.TestTokenOverlap -v`
Expected: all pass.

If any fail, inspect the Lineuparr helpers at lines 230-266 and confirm they were copied intact during Task 3.

- [ ] **Step 3: Commit**

```bash
cd /home/user/docker/EPG-Janitor
git add tests/test_fuzzy_matcher.py
git commit -m "test(fuzzy_matcher): lock in length-scaled threshold and token-overlap guard"
```

---

## Task 7: Channel number boost

**Files:**
- Modify: `tests/test_fuzzy_matcher.py`
- Confirm present: `EPG-Janitor/fuzzy_matcher.py` (`_channel_number_boost()` inherited from Lineuparr port)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_fuzzy_matcher.py`:

```python
class TestChannelNumberBoost(unittest.TestCase):
    def setUp(self):
        import fuzzy_matcher
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=80)

    def test_boost_applied_when_number_in_candidate(self):
        boost = self.m._channel_number_boost("CNN", "CNN 202", channel_number=202)
        self.assertGreaterEqual(boost, 5)

    def test_no_boost_when_number_missing(self):
        boost = self.m._channel_number_boost("CNN", "CNN HD", channel_number=202)
        self.assertEqual(boost, 0)

    def test_no_boost_when_channel_number_none(self):
        boost = self.m._channel_number_boost("CNN", "CNN 202", channel_number=None)
        self.assertEqual(boost, 0)
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd /home/user/docker/EPG-Janitor && python -m unittest tests.test_fuzzy_matcher.TestChannelNumberBoost -v`
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
cd /home/user/docker/EPG-Janitor
git add tests/test_fuzzy_matcher.py
git commit -m "test(fuzzy_matcher): lock in channel number boost behavior"
```

---

## Task 8: `match_all_streams()` orchestration + regional differentiation

**Files:**
- Modify: `EPG-Janitor/fuzzy_matcher.py` (add `min_score` parameter to `match_all_streams()`)
- Modify: `tests/test_fuzzy_matcher.py`

Spec change from Lineuparr: the matcher owns the score floor via a `min_score` argument, so callers don't double-filter. Lineuparr's version returns all above an internal threshold; ours returns all with `score >= min_score`.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_fuzzy_matcher.py`:

```python
class TestMatchAllStreams(unittest.TestCase):
    def setUp(self):
        import fuzzy_matcher
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=80)

    def test_results_sorted_descending_by_score(self):
        results = self.m.match_all_streams(
            "CNN",
            ["CNN", "CNN HD", "Unrelated"],
            alias_map={},
            min_score=0,
        )
        scores = [score for _, score, _ in results]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_min_score_filters_low_results(self):
        results = self.m.match_all_streams(
            "CNN",
            ["CNN", "Unrelated"],
            alias_map={},
            min_score=50,
        )
        for _, score, _ in results:
            self.assertGreaterEqual(score, 50)

    def test_alias_stage_short_circuits(self):
        results = self.m.match_all_streams(
            "FOX News Channel",
            ["Fox News"],
            alias_map={"FOX News Channel": ["Fox News"]},
            min_score=0,
        )
        self.assertTrue(any(mt == "alias" for _, _, mt in results))

    def test_empty_when_no_matches(self):
        results = self.m.match_all_streams(
            "zzzqqq",
            ["CNN", "ESPN"],
            alias_map={},
            min_score=70,
        )
        self.assertEqual(results, [])


class TestRegionalDifferentiation(unittest.TestCase):
    def setUp(self):
        import fuzzy_matcher
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=70)

    def test_ignore_regional_true_matches_any_region(self):
        # With the toggle on, East/West are stripped at normalize time
        # so all variants are eligible.
        results = self.m.match_all_streams(
            "HBO East",
            ["HBO West", "HBO"],
            alias_map={},
            min_score=0,
            user_ignored_tags={"regional"},
        )
        names = {name for name, _, _ in results}
        self.assertIn("HBO", names)

    def test_ignore_regional_false_east_does_not_match_west_only(self):
        results = self.m.match_all_streams(
            "HBO East",
            ["HBO West"],
            alias_map={},
            min_score=0,
            user_ignored_tags=set(),
        )
        # Lineuparr rule: East cannot match West-only feeds when regional
        # filtering is active.
        self.assertEqual(results, [])

    def test_ignore_regional_false_pacific_matches_only_pacific(self):
        results = self.m.match_all_streams(
            "HBO Pacific",
            ["HBO East", "HBO Pacific"],
            alias_map={},
            min_score=0,
            user_ignored_tags=set(),
        )
        names = {name for name, _, _ in results}
        self.assertIn("HBO Pacific", names)
        self.assertNotIn("HBO East", names)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/user/docker/EPG-Janitor && python -m unittest tests.test_fuzzy_matcher.TestMatchAllStreams tests.test_fuzzy_matcher.TestRegionalDifferentiation -v`
Expected: Some failures — at minimum, Lineuparr's `match_all_streams()` signature does not accept `min_score`. Also, the regional differentiation logic in Lineuparr assumes the toggle-agnostic pattern set; our merged patterns need the toggle-aware East/West handling wired in.

- [ ] **Step 3: Add `min_score` parameter to `match_all_streams()`**

Edit `EPG-Janitor/fuzzy_matcher.py`:

  - **3a.** Change the `match_all_streams()` signature to accept `min_score=0` as a keyword arg.

    ```python
    def match_all_streams(self, lineup_name, candidate_names, alias_map,
                          channel_number=None, user_ignored_tags=None,
                          min_score=0):
    ```

  - **3b.** At the end of the method, before returning, filter and sort:

    ```python
    results = [r for r in results if r[1] >= min_score]
    results.sort(key=lambda r: r[1], reverse=True)
    return results
    ```

  - **3c.** Remove any prior internal threshold filter that used `self.match_threshold` as the floor (we want the instance threshold to apply only to the fuzzy stage's acceptance, not to the final return list). Grep for `self.match_threshold` inside `match_all_streams` and confirm it's still used inside the fuzzy stage gate but not as a post-hoc filter.

- [ ] **Step 4: Wire toggle-aware regional filter**

In `match_all_streams()`, find the regional filtering block (around Lineuparr lines 570-630). Guard the East/West differentiation with the toggle:

```python
skip_regional_filter = (
    user_ignored_tags is not None
    and "regional" in user_ignored_tags
)
if not skip_regional_filter:
    # existing East/West/Pacific differentiation logic
    ...
```

When `skip_regional_filter` is True, the method skips regional filtering entirely and returns matches based on score alone.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /home/user/docker/EPG-Janitor && python -m unittest tests.test_fuzzy_matcher.TestMatchAllStreams tests.test_fuzzy_matcher.TestRegionalDifferentiation -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
cd /home/user/docker/EPG-Janitor
git add EPG-Janitor/fuzzy_matcher.py tests/test_fuzzy_matcher.py
git commit -m "feat(fuzzy_matcher): add min_score param and toggle-aware regional filter to match_all_streams"
```

---

## Task 9: Legacy `fuzzy_match()` backward-compat wrapper

**Files:**
- Modify: `EPG-Janitor/fuzzy_matcher.py` (add wrapper)
- Modify: `tests/test_fuzzy_matcher.py`

The 12 untouched action methods still call `fuzzy_match()` with the old signature. Keep them working via a wrapper.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_fuzzy_matcher.py`:

```python
class TestLegacyFuzzyMatchWrapper(unittest.TestCase):
    def setUp(self):
        import fuzzy_matcher
        self.m = fuzzy_matcher.FuzzyMatcher(match_threshold=70)

    def test_returns_best_single_match_tuple(self):
        result = self.m.fuzzy_match("CNN", ["CNN HD", "ESPN"])
        matched, score, match_type = result
        self.assertEqual(matched, "CNN HD")
        self.assertGreaterEqual(score, 70)
        self.assertIn(match_type, {"exact", "substring", "fuzzy"})

    def test_returns_no_match_sentinel_when_empty(self):
        result = self.m.fuzzy_match("zzzqqq", ["abc", "def"])
        self.assertEqual(result, ("", 0, "none"))

    def test_does_not_use_aliases(self):
        # Legacy callers get no alias lookup — the wrapper always passes {}.
        # This test verifies we don't accidentally hit the built-in alias table.
        result = self.m.fuzzy_match("FOX News Channel", ["Totally Unrelated"])
        matched, _, _ = result
        self.assertEqual(matched, "")

    def test_passes_through_user_ignored_tags(self):
        # When ignore_regional is in the ignored set, "HBO East" should match "HBO".
        result = self.m.fuzzy_match(
            "HBO East", ["HBO"], user_ignored_tags={"regional"}
        )
        matched, _, _ = result
        self.assertEqual(matched, "HBO")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/user/docker/EPG-Janitor && python -m unittest tests.test_fuzzy_matcher.TestLegacyFuzzyMatchWrapper -v`
Expected: if Lineuparr's `fuzzy_match()` is present it may partially work, but the sentinel shape `("", 0, "none")` and the "no alias" contract almost certainly won't match.

- [ ] **Step 3: Replace `fuzzy_match()` with the wrapper**

In `EPG-Janitor/fuzzy_matcher.py`, locate the existing `fuzzy_match()` method (ported from Lineuparr, lines ~379 in their file) and replace its body with:

```python
def fuzzy_match(self, query_name, candidate_names, user_ignored_tags=None,
                remove_cinemax=False):
    """Legacy single-best-match API used by callers that have not migrated
    to match_all_streams(). Returns (name, score, match_type) or
    ("", 0, "none") when no candidate crosses the instance threshold.

    Does NOT use aliases — callers that need aliases must use
    match_all_streams() directly.
    """
    # remove_cinemax is honored by adding "misc" to the ignored tag set
    # (Cinemax CX tags live in MISC_PATTERNS).
    ignored = set(user_ignored_tags or ())
    if remove_cinemax:
        ignored.add("misc")

    matches = self.match_all_streams(
        query_name,
        candidate_names,
        alias_map={},
        channel_number=None,
        user_ignored_tags=ignored,
        min_score=self.match_threshold,
    )
    if not matches:
        return ("", 0, "none")
    return matches[0]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/user/docker/EPG-Janitor && python -m unittest tests.test_fuzzy_matcher.TestLegacyFuzzyMatchWrapper -v`
Expected: all pass.

- [ ] **Step 5: Run full test suite for regression check**

Run: `cd /home/user/docker/EPG-Janitor && python -m unittest discover tests -v`
Expected: every test class from Tasks 1-9 passes.

- [ ] **Step 6: Commit**

```bash
cd /home/user/docker/EPG-Janitor
git add EPG-Janitor/fuzzy_matcher.py tests/test_fuzzy_matcher.py
git commit -m "feat(fuzzy_matcher): add fuzzy_match() backward-compat wrapper"
```

---

## Task 10: Refactor `_auto_match_channels` / `_find_best_epg_match` in plugin.py

**Files:**
- Modify: `EPG-Janitor/plugin.py` (lines ~719–970 per spec exploration)

No tests for plugin.py (it depends on Dispatcharr ORM and isn't importable outside the container). Verify by reading + static inspection.

- [ ] **Step 1: Read the current auto-match code path**

Read `/home/user/docker/EPG-Janitor/EPG-Janitor/plugin.py` lines 700-970. Identify:
- Where `epg_data_list` is built.
- Where the channel loop begins.
- Where `_find_best_epg_match` is called and what it currently does internally.
- Where `automatch_confidence_threshold` is consulted.

- [ ] **Step 2: Add alias map construction helper**

Near the top of `plugin.py` (after existing imports), add:

```python
import json as _json  # alias to avoid shadowing later local variables
from aliases import CHANNEL_ALIASES

def _build_alias_map(settings):
    """Merge built-in aliases with user-supplied custom_aliases JSON.
    Malformed JSON is logged and ignored (built-ins only)."""
    effective = dict(CHANNEL_ALIASES)
    raw = (settings or {}).get("custom_aliases") or ""
    raw = raw.strip()
    if not raw:
        return effective
    try:
        custom = _json.loads(raw)
        if isinstance(custom, dict):
            for key, value in custom.items():
                if isinstance(value, list):
                    effective[key] = list(value)
    except (_json.JSONDecodeError, TypeError, ValueError) as exc:
        LOGGER.warning("custom_aliases JSON invalid, ignoring: %s", exc)
    return effective
```

Place this helper adjacent to other `_build_*` or `_get_*` helpers at module scope. If module-scope placement conflicts with `Plugin` class helpers in this codebase, put it as a `@staticmethod` on `Plugin`.

- [ ] **Step 3: Refactor `_auto_match_channels()`**

Inside `_auto_match_channels()`, immediately after `epg_data_list` is built and the user's ignored-tag set is computed:

```python
# Build effective alias map once.
alias_map = _build_alias_map(self.settings)

# Pre-filter EPG to candidates that actually have program data
# within check_hours. (Existing pre-filter logic stays.)

# Collect candidate EPG display names once.
epg_names = [row["name"] for row in epg_data_list]

# Warm the matcher's normalization caches before the channel loop.
matcher.precompute_normalizations(epg_names)
```

Replace the per-channel match call:

```python
# OLD:
# best = self._find_best_epg_match(channel.name, epg_data_list, ...)

# NEW:
matches = matcher.match_all_streams(
    channel.name,
    epg_names,
    alias_map=alias_map,
    channel_number=None,
    user_ignored_tags=ignored_set,
    min_score=self.settings.get("automatch_confidence_threshold", 95),
)
best = matches[0] if matches else None
if best is None:
    continue  # no match; existing "no match" handling
matched_name, score, match_type = best
# Look up the EPG row for matched_name in epg_data_list and proceed
# with existing assignment logic.
```

Remove the body of `_find_best_epg_match()` — its job is now performed inline. If the method is called from elsewhere, convert it to a thin wrapper:

```python
def _find_best_epg_match(self, channel_name, epg_data_list, *args, **kwargs):
    """Deprecated: retained for any stray callers. Delegates to
    match_all_streams() with the same semantics as the refactored
    auto-match loop."""
    matcher = self._get_fuzzy_matcher()
    alias_map = _build_alias_map(self.settings)
    names = [row["name"] for row in epg_data_list]
    matches = matcher.match_all_streams(
        channel_name, names, alias_map=alias_map,
        user_ignored_tags=self._get_ignored_tags(),
        min_score=self.settings.get("automatch_confidence_threshold", 95),
    )
    return matches[0] if matches else None
```

- [ ] **Step 4: Static verification**

Run: `cd /home/user/docker/EPG-Janitor && python -c "import ast; ast.parse(open('EPG-Janitor/plugin.py').read()); print('OK')"`
Expected: `OK` (no syntax errors).

Run: `cd /home/user/docker/EPG-Janitor && python -m unittest discover tests -v`
Expected: all existing tests still pass (plugin.py isn't imported by tests, so this just confirms we didn't break tooling).

- [ ] **Step 5: Commit**

```bash
cd /home/user/docker/EPG-Janitor
git add EPG-Janitor/plugin.py
git commit -m "refactor(plugin): migrate _auto_match_channels to match_all_streams with aliases and precompute cache"
```

---

## Task 11: Refactor heal flow

**Files:**
- Modify: `EPG-Janitor/plugin.py` (scan-and-heal code path)

- [ ] **Step 1: Locate the heal code**

Open `EPG-Janitor/plugin.py` and grep for `scan_and_heal` to find `_do_scan_and_heal` (or the equivalently named internal routine). Identify the per-channel loop and the call that picks a replacement EPG.

- [ ] **Step 2: Replace single-match heal with ranked fallback**

Inside the heal loop, replace the single-match call with:

```python
heal_threshold = self.settings.get("heal_confidence_threshold", 95)
matches = matcher.match_all_streams(
    channel.name,
    epg_names,
    alias_map=alias_map,
    channel_number=None,
    user_ignored_tags=ignored_set,
    min_score=heal_threshold,
)

# Walk ranked candidates and pick the first one that:
#   (a) has program data in the check_hours window, and
#   (b) belongs to an eligible EPG source.
eligible_sources = self._resolve_heal_fallback_sources(channel)
chosen = None
for matched_name, score, match_type in matches:
    row = epg_by_name.get(matched_name)
    if row is None:
        continue
    if row["epg_id"] not in epg_ids_with_programs:
        continue
    if eligible_sources and row["source"] not in eligible_sources:
        continue
    chosen = (matched_name, score, match_type, row)
    break

if chosen is None:
    # Existing "no heal possible" recording — unchanged.
    continue

# Apply `chosen` via the existing assignment path.
```

`epg_by_name` is a dict built once before the loop: `epg_by_name = {row["name"]: row for row in epg_data_list}`.

Before writing `_resolve_heal_fallback_sources`, grep the plugin for an existing helper:

```bash
cd /home/user/docker/EPG-Janitor/EPG-Janitor
grep -n "heal_fallback" plugin.py
```

If a helper already parses `heal_fallback_sources`, reuse it. If not, add this method on `Plugin`:

```python
def _resolve_heal_fallback_sources(self, channel):
    """Return the set of EPG source names eligible for healing this channel.

    Consults settings['heal_fallback_sources'] (comma-separated). When
    empty, falls back to a set containing only the channel's current EPG
    source name so the heal never crosses sources unintentionally.
    """
    raw = (self.settings.get("heal_fallback_sources") or "").strip()
    if raw:
        return {item.strip() for item in raw.split(",") if item.strip()}
    current = getattr(channel, "epg_source_name", None)
    return {current} if current else set()
```

Callers in the heal loop treat an empty set as "no eligibility restriction" — adjust the `if eligible_sources and row["source"] not in eligible_sources` guard accordingly.

- [ ] **Step 3: Static verification**

Run: `cd /home/user/docker/EPG-Janitor && python -c "import ast; ast.parse(open('EPG-Janitor/plugin.py').read()); print('OK')"`
Expected: `OK`.

Run: `cd /home/user/docker/EPG-Janitor && python -m unittest discover tests -v`
Expected: all existing tests pass.

- [ ] **Step 4: Commit**

```bash
cd /home/user/docker/EPG-Janitor
git add EPG-Janitor/plugin.py
git commit -m "refactor(plugin): ranked-fallback heal using match_all_streams"
```

---

## Task 12: Update plugin.json — version, min_version, custom_aliases field, action styling

**Files:**
- Modify: `EPG-Janitor/plugin.json`

- [ ] **Step 1: Write the full new plugin.json**

Overwrite `EPG-Janitor/plugin.json` with this exact content:

```json
{
  "name": "EPG Janitor",
  "version": "0.8.0",
  "description": "Scans for channels with EPG assignments but no program data. Auto-matches EPG to channels using intelligent fuzzy matching with aliases, removes EPG from hidden channels, and manages EPG assignments.",
  "author": "community",
  "help_url": "https://github.com/PiratesIRC/Dispatcharr-EPG-Janitor-Plugin",
  "min_dispatcharr_version": "v0.20.0",
  "fields": [
    {"id": "channel_profile_name", "label": "Channel Profile Names", "type": "string", "default": ""},
    {"id": "selected_groups", "label": "Channel Groups", "type": "string", "default": ""},
    {"id": "ignore_groups", "label": "Ignore Groups", "type": "string", "default": ""},
    {"id": "epg_sources_to_match", "label": "EPG Sources to Match", "type": "string", "default": ""},
    {"id": "check_hours", "label": "Hours to Check Ahead", "type": "number", "default": 12},
    {"id": "epg_regex_to_remove", "label": "EPG Name REGEX to Remove", "type": "string", "default": ""},
    {"id": "bad_epg_suffix", "label": "Bad EPG Suffix", "type": "string", "default": " [BadEPG]"},
    {"id": "remove_epg_with_suffix", "label": "Also Remove EPG When Adding Suffix", "type": "boolean", "default": false},
    {"id": "automatch_confidence_threshold", "label": "Auto-Match Confidence Threshold", "type": "number", "default": 95},
    {"id": "heal_fallback_sources", "label": "Heal Fallback EPG Sources", "type": "string", "default": ""},
    {"id": "heal_confidence_threshold", "label": "Heal Confidence Threshold", "type": "number", "default": 95},
    {"id": "allow_epg_without_programs", "label": "Allow EPG Without Program Data", "type": "boolean", "default": false},
    {"id": "ignore_quality_tags", "label": "Ignore Quality Tags", "type": "boolean", "default": true},
    {"id": "ignore_regional_tags", "label": "Ignore Regional Tags", "type": "boolean", "default": true},
    {"id": "ignore_geographic_tags", "label": "Ignore Geographic Prefixes", "type": "boolean", "default": true},
    {"id": "ignore_misc_tags", "label": "Ignore Miscellaneous Tags", "type": "boolean", "default": true},
    {"id": "custom_aliases", "label": "Custom Channel Aliases (JSON)", "type": "string", "default": ""}
  ],
  "actions": [
    {"id": "validate_settings", "label": "\u2705 Validate Settings", "description": "Validate all plugin settings and database connectivity", "button_variant": "outline", "button_color": "blue"},
    {"id": "get_summary", "label": "\ud83d\udcca View Last Results", "description": "Display summary of the last EPG scan results", "button_variant": "outline", "button_color": "blue"},
    {"id": "scan_missing_epg", "label": "\ud83d\udd0d Scan for Missing Program Data", "description": "Find channels with EPG assignments but no program data", "button_variant": "outline", "button_color": "blue"},
    {"id": "preview_auto_match", "label": "\ud83d\udc41\ufe0f Preview Auto-Match (Dry Run)", "description": "Preview intelligent EPG auto-matching with program data validation", "button_variant": "outline", "button_color": "cyan"},
    {"id": "scan_and_heal_dry_run", "label": "\ud83e\ude79 Scan & Heal (Dry Run)", "description": "Find broken EPG assignments and search for working replacements (preview only)", "button_variant": "outline", "button_color": "cyan"},
    {"id": "export_results", "label": "\ud83d\udcc4 Export Results to CSV", "description": "Export the last scan results to a CSV file", "button_variant": "outline", "button_color": "cyan"},
    {"id": "apply_auto_match", "label": "\ud83c\udfaf Apply Auto-Match EPG Assignments", "description": "Automatically match and assign EPG to channels using intelligent weighted scoring", "button_variant": "filled", "button_color": "green", "confirm": {"message": "This will assign EPG data to matched channels. Continue?"}},
    {"id": "scan_and_heal_apply", "label": "\ud83e\ude79 Scan & Heal (Apply Changes)", "description": "Automatically find and fix broken EPG assignments", "button_variant": "filled", "button_color": "green", "confirm": {"message": "This will replace broken EPG assignments with working ones. Continue?"}},
    {"id": "add_bad_epg_suffix", "label": "\ud83c\udff7\ufe0f Add Bad EPG Suffix to Channels", "description": "Add suffix to channels with missing EPG program data", "button_variant": "filled", "button_color": "orange", "confirm": {"message": "This will rename channels that have missing EPG program data. Continue?"}},
    {"id": "remove_epg_from_hidden", "label": "\ud83d\udc41\ufe0f\u200d\ud83d\udde8\ufe0f Remove EPG from Hidden Channels", "description": "Remove all EPG data from channels hidden in the selected profile", "button_variant": "filled", "button_color": "orange", "confirm": {"message": "This will remove EPG assignments from every channel hidden in the selected profile. Continue?"}},
    {"id": "remove_epg_assignments", "label": "\u274c Remove EPG Assignments", "description": "Remove EPG assignments from channels with missing program data", "button_variant": "filled", "button_color": "red", "confirm": {"message": "This will permanently remove EPG assignments from channels with missing program data. Are you sure?"}},
    {"id": "remove_epg_by_regex", "label": "\u274c Remove EPG Assignments matching REGEX", "description": "Remove EPG from channels matching REGEX pattern within groups", "button_variant": "filled", "button_color": "red", "confirm": {"message": "This will permanently remove EPG assignments from channels matching the REGEX pattern. Are you sure?"}},
    {"id": "remove_all_epg_from_groups", "label": "\u274c Remove ALL EPG Assignments from Groups", "description": "Remove EPG from all channels in specified groups", "button_variant": "filled", "button_color": "red", "confirm": {"message": "This will permanently remove EPG from EVERY channel in the specified groups. This cannot be undone. Are you sure?"}},
    {"id": "clear_csv_exports", "label": "\ud83d\uddd1\ufe0f Clear CSV Exports", "description": "Delete all CSV export files created by this plugin", "button_variant": "outline", "button_color": "red", "confirm": {"message": "Delete all EPG Janitor CSV exports?"}}
  ]
}
```

- [ ] **Step 2: Validate JSON**

Run: `cd /home/user/docker/EPG-Janitor && python -c "import json; data=json.load(open('EPG-Janitor/plugin.json')); print(data['version'], data['min_dispatcharr_version'], len(data['fields']), 'fields,', len(data['actions']), 'actions')"`
Expected: `0.8.0 v0.20.0 17 fields, 14 actions`.

- [ ] **Step 3: Commit**

```bash
cd /home/user/docker/EPG-Janitor
git add EPG-Janitor/plugin.json
git commit -m "feat(plugin.json): add min_dispatcharr_version, custom_aliases, action styling, emoji labels"
```

---

## Task 13: Update CLAUDE.md with upgrade notes

**Files:**
- Modify: `EPG-Janitor/CLAUDE.md`

- [ ] **Step 1: Append upgrade notes section**

Append to the end of `EPG-Janitor/CLAUDE.md`:

```markdown

## Upgrade Notes: 0.7.0a → 0.8.0

Behavior changes users may notice:

- **Regional filtering when `ignore_regional_tags=False`**: in 0.7.0a this setting only affected normalization. In 0.8.0 it also enables active filtering — "HBO East" will no longer match "HBO West", and "X Pacific" will only match Pacific variants. Users who want the old "preserve region in name but match across regions" behavior should set `ignore_regional_tags=True` (the default).
- **Alias-backed auto-match**: auto-match now consults a ~200-entry built-in alias table (`aliases.py`) plus any user-provided `custom_aliases` JSON. Matches that previously failed because the display name differed from the EPG display name (e.g. "Fox News" vs. "FOX News Channel") will now succeed. Run **Preview Auto-Match** after upgrade to review.
- **Ranked heal**: Scan & Heal now walks ranked candidates and picks the first one with program data in an eligible source. Users who set `heal_fallback_sources` will see more successful heals.
- **Performance**: auto-match on large EPG databases is noticeably faster thanks to normalization caching (`precompute_normalizations()`).

No database migration, no setting rename. All 0.7.0a settings keep their names and semantics.

## Architecture additions in 0.8.0

- `aliases.py` — built-in `CHANNEL_ALIASES` dict (copied wholesale from the Lineuparr plugin).
- `fuzzy_matcher.FuzzyMatcher.match_all_streams(query, candidates, alias_map, channel_number, user_ignored_tags, min_score)` — new ranked-matches API. Pipeline: alias → exact → substring → fuzzy token-sort, with length-scaled thresholds and token-overlap guards. Returns `[(name, score, match_type), ...]` sorted descending.
- `fuzzy_matcher.FuzzyMatcher.precompute_normalizations(names)` — one-shot cache warmer, called once per auto-match run.
- `fuzzy_matcher.FuzzyMatcher.fuzzy_match(...)` — retained as a thin backward-compat wrapper that does NOT use aliases. All new code should call `match_all_streams()` directly.
```

- [ ] **Step 2: Commit**

```bash
cd /home/user/docker/EPG-Janitor
git add EPG-Janitor/CLAUDE.md
git commit -m "docs(CLAUDE.md): document 0.8.0 upgrade notes and matcher additions"
```

---

## Task 14: Final verification

**Files:** none modified.

- [ ] **Step 1: Full test suite**

Run: `cd /home/user/docker/EPG-Janitor && python -m unittest discover tests -v`
Expected: every test passes (target: 30–50 tests across 9 test classes).

- [ ] **Step 2: JSON validation**

Run: `cd /home/user/docker/EPG-Janitor && python -c "import json; json.load(open('EPG-Janitor/plugin.json'))"`
Expected: no output, exit 0.

- [ ] **Step 3: Syntax validation for plugin.py**

Run: `cd /home/user/docker/EPG-Janitor && python -c "import ast; ast.parse(open('EPG-Janitor/plugin.py').read())"`
Expected: no output, exit 0.

- [ ] **Step 4: Import check for the plugin modules**

Run: `cd /home/user/docker/EPG-Janitor && python -c "import sys; sys.path.insert(0, 'EPG-Janitor'); import fuzzy_matcher, aliases; print('fuzzy_matcher OK, aliases OK, built-in aliases:', len(aliases.CHANNEL_ALIASES))"`
Expected: `fuzzy_matcher OK, aliases OK, built-in aliases: NNN` (some number >100).

- [ ] **Step 5: Count lines (sanity check)**

Run: `cd /home/user/docker/EPG-Janitor && wc -l EPG-Janitor/fuzzy_matcher.py EPG-Janitor/aliases.py EPG-Janitor/plugin.py tests/test_fuzzy_matcher.py`
Expected rough shape: `fuzzy_matcher.py` ~600-750 lines, `aliases.py` ~200 lines, `plugin.py` still ~3200 lines ±100, `test_fuzzy_matcher.py` ~250-400 lines.

- [ ] **Step 6: Manual Dispatcharr deploy checklist (user-side, not automated)**

These steps happen on the user's Windows host, not in this dev checkout:

1. Zip the plugin: the user should use `zip.cmd` or equivalent to package `EPG-Janitor/` into `EPG-Janitor.zip`.
2. In Dispatcharr (running on the Windows host): **Plugins → Import Plugin**, upload the zip, confirm it appears at version 0.8.0.
3. Verify all 14 actions render with the new colors, emoji, and confirmation dialogs.
4. Run **Validate Settings** — should succeed.
5. Run **Preview Auto-Match** — review CSV output for new matches created by the alias table.
6. Run **Apply Auto-Match** only after reviewing the preview.

If any Dispatcharr UI regression appears (e.g. a button fails to render, a confirm dialog never fires), the most likely cause is a plugin.json shape mismatch — re-check against Lineuparr's `plugin.json` for the exact property names Dispatcharr v0.20.0+ expects.

- [ ] **Step 7: Tag the completion commit**

```bash
cd /home/user/docker/EPG-Janitor
git commit --allow-empty -m "chore: EPG-Janitor 0.8.0 feature complete"
```

---

## Post-implementation: deferred items tracking

These are explicitly out of scope for 0.8.0 per the spec. If pursued later, they deserve a separate plan:

- Dynamic select fields (EPG sources, profiles, groups) — requires Dispatcharr support for multi-select and a runtime options-population mechanism.
- Match sensitivity preset slider — would collapse the four independent toggles into a single axis; needs user-research on whether that's desired.
- Integration tests — requires a Dispatcharr test fixture or an ORM mocking layer; neither exists today.
- Bump `min_dispatcharr_version` beyond v0.20.0 if newer UI primitives (e.g., multi-select, grouped sections) become available.
