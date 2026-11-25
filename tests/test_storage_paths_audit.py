"""Every /data path literal in the shipped modules is one the storage design accounts for.

plugin.py holds its /data literals only in the PluginConfig class body: the legacy paths that
storage.bind moves, and the two user-facing paths that stay (the shared exports folder and the
automatch preview CSV). The vendored usage client keeps its own default, which the plugin
overrides by passing data_dir. A literal anywhere else is a path the data-dir move does not cover.
"""
import ast
import pathlib

PLUGIN_DIR = pathlib.Path(__file__).resolve().parent.parent / "EPG-Janitor"

# The vendored client is not edited; the plugin passes data_dir and never uses this default.
VENDORED_ALLOWED = {"usage_client.py": {"/data/plugin_stats"}}
# storage.py names the legacy paths in its docstrings; plugin_storage.py guards real data.
SKIPPED = {"storage.py", "plugin_storage.py"}

CONFIG_LITERALS = {
    "/data/exports", "/data/epg_automatch_preview.csv", "/data/epg_janitor_results.json",
    "/data/epg_janitor_progress.json", "/data/epg_janitor_match_counts.jsonl", "/data/plugin_stats",
}


def _data_literals(tree):
    """(value, node) for each string constant starting with /data and holding no whitespace."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if value.startswith("/data") and not any(ch.isspace() for ch in value):
                yield value, node


def _plugin_config_span(tree):
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "PluginConfig")
    return cls.lineno, cls.end_lineno


def test_plugin_py_keeps_data_literals_only_in_the_config_class():
    path = PLUGIN_DIR / "plugin.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    first, last = _plugin_config_span(tree)
    found = list(_data_literals(tree))
    outside = sorted({v for v, n in found if not (first <= n.lineno <= last)})
    assert not outside, "a /data literal outside PluginConfig: %s" % outside
    inside = {v for v, n in found if first <= n.lineno <= last}
    assert inside == CONFIG_LITERALS


def test_no_other_module_holds_a_data_literal_outside_the_allowed_set():
    for path in sorted(PLUGIN_DIR.glob("*.py")):
        if path.name in SKIPPED or path.name == "plugin.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found = {v for v, _n in _data_literals(tree)}
        strays = found - VENDORED_ALLOWED.get(path.name, set())
        assert not strays, "%s holds unaccounted /data literals: %s" % (path.name, sorted(strays))
