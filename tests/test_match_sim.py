import os
import sys
import tempfile  # noqa: E402
import unittest

_TOOLS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import aliases as _aliases_mod  # noqa: E402
import match_sim  # noqa: E402


class TestParseChannelsCsv(unittest.TestCase):
    def test_skips_comment_header_and_autodetects_column(self):
        text = (
            "# EPG Janitor v1.26 - Export Report\n"
            "# Generated: 2026-05-16\n"
            "#\n"
            "Channel Name,EPG ID,Status\n"
            "CNN,cnn.us,ok\n"
            "ESPN,espn.us,missing\n"
        )
        names = match_sim.parse_channels_csv(text)
        self.assertEqual(names, ["CNN", "ESPN"])

    def test_explicit_column_and_dedupe_and_blank_drop(self):
        text = "name,other\nFoo,x\nFoo,y\n,z\nBar,w\n"
        names = match_sim.parse_channels_csv(text, channel_col="name")
        self.assertEqual(names, ["Foo", "Bar"])

    def test_unresolvable_column_raises(self):
        text = "colA,colB\n1,2\n"
        with self.assertRaises(ValueError):
            match_sim.parse_channels_csv(text)


class TestParseM3u(unittest.TestCase):
    def test_basic_entry(self):
        text = (
            '#EXTM3U\n'
            '#EXTINF:-1 tvg-id="cnn.us" tvg-name="CNN HD" group-title="News",CNN HD\n'
            'http://example/cnn\n'
        )
        entries = match_sim.parse_m3u(text)
        self.assertEqual(len(entries), 1)
        e = entries[0]
        self.assertEqual(e.display_name, "CNN HD")
        self.assertEqual(e.tvg_name, "CNN HD")
        self.assertEqual(e.group_title, "News")
        self.assertEqual(e.tvg_id, "cnn.us")

    def test_display_name_fallback_to_tvg_name(self):
        text = '#EXTINF:-1 tvg-name="ESPN",\nhttp://x\n'
        entries = match_sim.parse_m3u(text)
        self.assertEqual(entries[0].query_name, "ESPN")

    def test_malformed_line_skipped(self):
        text = '#EXTINF:garbage-no-comma\nhttp://x\n#EXTINF:-1,Good\nhttp://y\n'
        entries = match_sim.parse_m3u(text)
        self.assertEqual([e.display_name for e in entries], ["Good"])

    def test_bom_tolerated(self):
        text = '﻿#EXTM3U\n#EXTINF:-1,Foo\nhttp://x\n'
        entries = match_sim.parse_m3u(text)
        self.assertEqual(entries[0].display_name, "Foo")


class TestBuildAliasMap(unittest.TestCase):
    def test_empty_returns_builtins_copy(self):
        m = match_sim.build_alias_map("")
        self.assertEqual(m, dict(_aliases_mod.CHANNEL_ALIASES))
        self.assertIsNot(m, _aliases_mod.CHANNEL_ALIASES)

    def test_valid_custom_overlays(self):
        m = match_sim.build_alias_map('{"My Chan": ["MC HD", "MC"]}')
        self.assertEqual(m["My Chan"], ["MC HD", "MC"])

    def test_malformed_json_ignored(self):
        m = match_sim.build_alias_map("{not json")
        self.assertEqual(m, dict(_aliases_mod.CHANNEL_ALIASES))

    def test_non_object_ignored(self):
        m = match_sim.build_alias_map("[1, 2, 3]")
        self.assertEqual(m, dict(_aliases_mod.CHANNEL_ALIASES))

    def test_bad_entry_skipped_others_kept(self):
        m = match_sim.build_alias_map('{"Good": ["g"], "Bad": "nope"}')
        self.assertEqual(m["Good"], ["g"])
        self.assertNotIn("Bad", m)


class _FakeMatcher:
    """Returns canned per-channel rankings keyed by the query (channel) name."""
    def __init__(self, table):
        self._table = table  # {channel_name: [(stream_name, score, mtype), ...]}
        self.precomputed = None

    def precompute_normalizations(self, names):
        self.precomputed = list(names)

    def match_all_streams(self, lineup_name, candidate_names, alias_map,
                          channel_number=None, user_ignored_tags=None, min_score=0):
        return list(self._table.get(lineup_name, []))


class TestSimulate(unittest.TestCase):
    def test_inverts_to_best_channel_per_stream(self):
        matcher = _FakeMatcher({
            "CNN":  [("CNN HD", 95, "alias"), ("CNN US", 80, "fuzzy")],
            "ESPN": [("CNN US", 60, "fuzzy")],  # weaker claim on CNN US
        })
        per_stream = match_sim.simulate(
            channel_names=["CNN", "ESPN"],
            stream_names=["CNN HD", "CNN US", "Orphan TV"],
            matcher=matcher,
            alias_map={},
            user_ignored_tags=[],
        )
        # CNN US claimed by both channels -> CNN wins (80 > 60), ESPN retained, sorted desc
        self.assertEqual(
            per_stream["CNN US"], [("CNN", 80, "fuzzy"), ("ESPN", 60, "fuzzy")]
        )
        self.assertEqual(per_stream["CNN HD"], [("CNN", 95, "alias")])
        # Orphan stream present with empty ranking
        self.assertEqual(per_stream["Orphan TV"], [])

    def test_precompute_called_with_all_names(self):
        matcher = _FakeMatcher({})
        match_sim.simulate(["A"], ["s1", "s2"], matcher, {}, [])
        self.assertEqual(sorted(matcher.precomputed), ["A", "s1", "s2"])


class TestWriteReports(unittest.TestCase):
    def test_writes_all_five_files_with_expected_classification(self):
        per_stream = {
            "Hit":  [("CNN", 95, "alias"), ("CNNI", 70, "fuzzy")],
            "Low":  [("ESPN", 72, "fuzzy")],
            "Miss": [],
        }
        with tempfile.TemporaryDirectory() as d:
            out = match_sim.write_reports(
                per_stream, d, threshold=80, margin=15, top_n=2,
                run_config={"threshold": 80},
            )
            files = {p.name for p in out.iterdir()}
            self.assertEqual(files, {
                "per_stream_matches.csv", "unmatched.csv",
                "low_confidence.csv", "top_n.csv", "summary.txt",
            })
            per = (out / "per_stream_matches.csv").read_text()
            self.assertIn("Hit,", per)
            self.assertIn("True", per)   # Hit passed
            # header + one row per stream (no skipped/duplicated rows)
            self.assertEqual(len(per.strip().split("\n")), 4)
            unmatched = (out / "unmatched.csv").read_text()
            self.assertIn("Miss", unmatched)
            self.assertNotIn("Hit", unmatched)
            low = (out / "low_confidence.csv").read_text()
            self.assertIn("Low", low)        # 72 in [65,80)
            self.assertNotIn("Hit", low)
            topn = (out / "top_n.csv").read_text()
            self.assertIn("CNNI", topn)      # rank-2 candidate present
            summary = (out / "summary.txt").read_text()
            self.assertIn("Total streams: 3", summary)
            self.assertIn("threshold", summary)


class TestCliEndToEnd(unittest.TestCase):
    def test_real_matcher_smoke(self):
        with tempfile.TemporaryDirectory() as d:
            ch = os.path.join(d, "channels.csv")
            m3 = os.path.join(d, "streams.m3u")
            out = os.path.join(d, "out")
            with open(ch, "w") as f:
                f.write("# header comment\nChannel Name\nCNN\nESPN\n")
            with open(m3, "w") as f:
                f.write(
                    '#EXTM3U\n'
                    '#EXTINF:-1 tvg-name="CNN",CNN\n'
                    'http://x\n'
                    '#EXTINF:-1,ESPN HD\n'
                    'http://y\n'
                )
            rc = match_sim.main([
                "--channels", ch, "--streams", m3,
                "--out", out, "--countries", "",
            ])
            self.assertEqual(rc, 0)
            run_dirs = list(os.scandir(out))
            self.assertEqual(len(run_dirs), 1)
            produced = {e.name for e in os.scandir(run_dirs[0].path)}
            self.assertIn("per_stream_matches.csv", produced)
            self.assertIn("summary.txt", produced)

    def test_missing_file_returns_nonzero(self):
        rc = match_sim.main([
            "--channels", "/no/such.csv", "--streams", "/no/such.m3u",
        ])
        self.assertNotEqual(rc, 0)

    def test_invalid_group_filter_regex_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as d:
            ch = os.path.join(d, "channels.csv")
            m3 = os.path.join(d, "streams.m3u")
            with open(ch, "w") as f:
                f.write("Channel Name\nCNN\n")
            with open(m3, "w") as f:
                f.write('#EXTM3U\n#EXTINF:-1,CNN\nhttp://x\n')
            rc = match_sim.main([
                "--channels", ch, "--streams", m3,
                "--out", os.path.join(d, "out"),
                "--countries", "", "--group-filter", "[invalid(",
            ])
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
