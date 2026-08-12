"""Session-wide guard against tests writing to the container's own paths.

The plugin writes to absolute container paths (/data/exports and three files
directly under /data). On a Linux CI runner those are real, writable-looking
locations; on Windows they resolve to the same names on the current drive root.
A test that reaches production code writing one of them creates a file outside
the repository, on the machine running the suite. The sibling plugin
Channel-Maparr had its workflow red for a week from exactly this, and it is
invisible on Windows.

It has not happened here yet, and the reason is worth writing down: no test
imports plugin.py at all, because that module imports apps.channels.models,
apps.epg.models, celery and django at module scope. The moment anyone finds a
way to exercise an export path, the class opens up.

So this is a detector, not a redirect. Channel-Maparr redirects the paths to a
temporary directory, which is the stronger fix, but a redirect here would be a
fixture that never fires and could not be told apart from a working one. This
fails the session instead, and names the file that appeared.

Measured on the development machine 2026-08-12: the /data and /config roots
already existed there, created by the test suites of three sibling plugins. They
held no EPG Janitor artifacts. That is why the guard checks for the specific
paths this plugin writes rather than for the directories themselves, and why it
compares against a snapshot taken at session start rather than assuming the
roots are absent.
"""
import ast
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PLUGIN_DIR = REPO_ROOT / "EPG-Janitor"


def _declared_container_paths():
    """Every absolute /data or /config path written as a literal in a shipped
    module, read from the source so the list cannot go stale."""
    found = set()
    for source_file in sorted(PLUGIN_DIR.glob("*.py")):
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = node.value
                if text.startswith("/data") or text.startswith("/config"):
                    found.add(text.rstrip("/"))
    return sorted(found)


@pytest.fixture(scope="session", autouse=True)
def no_container_paths_created():
    """Autouse on purpose: a new test cannot forget it."""
    declared = _declared_container_paths()
    assert declared, (
        "no /data or /config literals found in the shipped modules. Either the "
        "plugin stopped writing to container paths, in which case delete this "
        "guard, or the paths are now computed and this guard has gone blind."
    )
    before = {p for p in declared if pathlib.Path(p).exists()}

    yield

    appeared = sorted(p for p in declared
                      if p not in before and pathlib.Path(p).exists())
    assert not appeared, (
        f"the test run created container paths on this machine: {appeared}. "
        f"A test reached production code that writes an absolute container "
        f"path. Point that code at tmp_path rather than deleting this guard."
    )
