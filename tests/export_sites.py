"""Which functions in plugin.py write a CSV export.

Shared by tests/test_csv_retention.py, which checks each one prunes older
exports, and tests/test_csv_header.py, which checks each one writes a preamble.
It lived in both files as a copy and the two had already drifted: one matched
async functions and the other did not.
"""
import ast
import pathlib

PLUGIN_DIR = pathlib.Path(__file__).resolve().parent.parent / "EPG-Janitor"
PLUGIN_PY = PLUGIN_DIR / "plugin.py"


def parse_plugin():
    return ast.parse(PLUGIN_PY.read_text(encoding="utf-8"))


def export_writer_functions(tree=None):
    """Every function that builds an epg_janitor_*.csv filename.

    The filenames are built as f-strings, so a function that constructs one is a
    function that writes an export. Read from the source rather than listed by
    hand, so a fifth export site cannot be added without the tests noticing.
    """
    if tree is None:
        tree = parse_plugin()
    writers = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.JoinedStr):
                continue
            parts = [v.value for v in inner.values if isinstance(v, ast.Constant)]
            if not parts:
                continue
            if parts[0].startswith("epg_janitor_") and parts[-1].endswith(".csv"):
                writers[node.name] = node
    return writers


def actions_that_clear_a_guide_assignment(tree=None):
    """Action handlers whose own body writes a cleared EPG assignment.

    Ground truth for the button colour rule, read from the source rather than
    from a hand-maintained list, because a hand-maintained list can agree with a
    wrong colour. Measured 2026-09-05: exactly five handlers do this, and one of
    them was coloured orange while the colour legend promised orange removes no
    guide assignment.

    LIMITATION, stated because a test that silently stops finding anything is
    worse than no test: this reads each handler's OWN body and does not follow
    calls into helpers. The caller must assert the returned set matches the five
    known handlers, so moving a write into a helper fails the suite loudly
    instead of quietly reporting that nothing clears an assignment.
    """
    if tree is None:
        tree = parse_plugin()
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.endswith("_action"):
            continue
        for inner in ast.walk(node):
            text = ""
            if isinstance(inner, ast.Dict):
                text = ast.unparse(inner)
            elif isinstance(inner, (ast.Assign, ast.Call)):
                text = ast.unparse(inner)
            if not text:
                continue
            if ("'epg_data_id': None" in text
                    or "epg_data_id'] = None" in text
                    or "epg_data=None" in text):
                found.add(node.name[:-len("_action")])
                break
    return found
