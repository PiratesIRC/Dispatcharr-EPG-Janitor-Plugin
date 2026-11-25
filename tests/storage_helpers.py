"""Helpers shared by the storage tests. Nothing here reads a real /data path."""
import ast
import os
import pathlib
from types import SimpleNamespace

PLUGIN_SOURCE = pathlib.Path(__file__).resolve().parent.parent / "EPG-Janitor" / "plugin.py"
STATE_NAMES = ("RESULTS_FILE", "PROGRESS_FILE", "MATCH_LEDGER_FILE", "USAGE_DATA_DIR")


class Log:
    def __init__(self):
        self.infos, self.warnings, self.errors = [], [], []

    def info(self, *a):
        self.infos.append(a)

    def debug(self, *a):
        pass

    def warning(self, *a):
        self.warnings.append(a)

    def error(self, *a):
        self.errors.append(a)


def source_literals():
    """The PluginConfig class body's string constants, read from source (the legacy paths)."""
    tree = ast.parse(PLUGIN_SOURCE.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "PluginConfig")
    out = {}
    for node in cls.body:
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            out[node.targets[0].id] = node.value.value
    return out


def make_cfg(values):
    return SimpleNamespace(PLUGIN_DB_KEY="epg_janitor", PLUGIN_VERSION="9.9.9", **values)


def make_layout(storage, root):
    plugins = os.path.join(root, "plugins")
    data = os.path.join(plugins, "_data", "epg_janitor")
    return storage.Layout(False, data, plugins, "epg_janitor", "test")


def tmp_legacy(tmp_path):
    """The legacy literals, each moved under tmp_path so a carry-over reads only test files."""
    base = tmp_path / "old"
    literals = source_literals()
    return {name: str(base / literals[name][len("/data/"):]) for name in STATE_NAMES}
