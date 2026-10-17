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
import contextlib
import importlib.util
import json
import os
import pathlib
import sys
from unittest.mock import MagicMock

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


# ---------------------------------------------------------------------------
# Importing plugin.py outside Dispatcharr
#
# plugin.py does `from apps.channels.models import ...`, `from django.db import
# ...`, `import celery` and `from core.utils import ...` at module scope, so it
# cannot be imported without a running backend. Registering stand-ins for those
# modules lets the import succeed, which is what every sibling plugin in this
# workspace does; the approach is copied from Channel-Maparr/tests/conftest.py.
#
# The stubs answer attribute access and nothing more. They do NOT emulate the
# ORM, so a test may assert on the module's static surface and on pure helpers,
# but never on query behaviour. A test that appears to exercise a queryset is
# asserting on a MagicMock and is worthless -- assert on real behaviour or move
# the test into the container.
#
# The hyphenated directory name cannot be imported directly, and plugin.py uses
# relative imports ("from .fuzzy_matcher import FuzzyMatcher"), so the directory
# is loaded as a package under the synthetic name below.
# ---------------------------------------------------------------------------

_STUBBED_MODULES = [
    "apps", "apps.channels", "apps.channels.models",
    "apps.epg", "apps.epg.models",
    "celery",
    "core", "core.utils",
    "django", "django.db", "django.db.models", "django.utils",
]

_PACKAGE_NAME = "epg_janitor_under_test"


def _load_plugin_package():
    if _PACKAGE_NAME in sys.modules:
        return sys.modules[_PACKAGE_NAME]
    for name in _STUBBED_MODULES:
        sys.modules.setdefault(name, MagicMock())
    spec = importlib.util.spec_from_file_location(
        _PACKAGE_NAME,
        PLUGIN_DIR / "__init__.py",
        submodule_search_locations=[str(PLUGIN_DIR)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[_PACKAGE_NAME] = package
    spec.loader.exec_module(package)
    return package


@pytest.fixture(scope="session")
def plugin_module():
    """The shipped plugin package, imported with Dispatcharr stubbed."""
    return _load_plugin_package()


@pytest.fixture(autouse=True)
def usage_counter_sandbox(monkeypatch, tmp_path):
    """Every test: the usage counter writes only under tmp_path and never sends.

    The client returns before doing anything when fcntl is missing (Windows), so
    the lock is forced open here. The code then reaches the start hook on every
    platform, and the start hook records the call instead of starting a thread.
    Any recorded call fails the test at teardown, because report() swallows its
    own exceptions and an assertion made inside it could never surface.
    """
    package = _load_plugin_package()
    # USAGE lives in plugin.py; the package __init__ re-exports only Plugin.
    usage = getattr(sys.modules[package.Plugin.__module__], "USAGE", None)
    if usage is None:
        yield
        return
    started = []
    monkeypatch.setattr(usage, "data_dir", str(tmp_path / "plugin_stats"))
    monkeypatch.setattr(usage, "directory", str(tmp_path / "plugin_stats" / usage.plugin))
    monkeypatch.setattr(usage, "_lock", lambda fd: True)
    monkeypatch.setattr(usage, "_start", lambda fn: started.append(fn))
    yield
    assert not started, f"a test started a real usage send ({len(started)} call(s))"


@pytest.fixture(scope="session")
def manifest():
    """plugin.json, parsed. Read as utf-8 explicitly: it carries emoji, and the
    Windows cp1252 default raises UnicodeDecodeError."""
    return json.loads((PLUGIN_DIR / "plugin.json").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Shared helpers for the interface tests
#
# Two of them were copy-pasted into separate test files and had already
# drifted: one copy of the export-writer detector matched async functions and
# the other did not. One definition each, here.
# ---------------------------------------------------------------------------

from export_sites import export_writer_functions, parse_plugin  # noqa: E402


@pytest.fixture(scope="session")
def plugin_source_tree():
    """plugin.py parsed once for the whole session."""
    return parse_plugin()


@pytest.fixture(scope="session")
def export_writers(plugin_source_tree):
    return export_writer_functions(plugin_source_tree)


def declared_settings(plugin_module):
    """Every declared field that stores a value, section headings excluded.

    Two test files filtered _base_fields this way independently.
    """
    return [f for f in plugin_module.Plugin._base_fields
            if not f["id"].startswith("_section_")]


def build_bare_plugin(plugin_module):
    """A Plugin instance built without running __init__.

    __init__ writes progress state to a container path, which the guard at the
    top of this file would fail the session for. One definition: the same two
    lines were copy-pasted into two test files.
    """
    P = plugin_module.Plugin
    inst = P.__new__(P)
    inst.version = "test"
    return inst


@pytest.fixture
def bare_plugin(plugin_module):
    return build_bare_plugin(plugin_module)

# ---- gevent hub-hold guard (same as Sentinelarr's and Stream-Mapparr's) ------
# uWSGI runs this plugin under `gevent = 400` with early monkey-patching, so a
# thread here is a greenlet and code that runs without yielding holds the whole
# worker. hub_hold(max_ms) fails a test when the body runs longer than max_ms
# between two switches into the hub, measured by gevent.util.assert_switches
# (gevent pinned in requirements-dev.txt to the container's version). Without
# gevent the guard skips locally but FAILS under CI (GitHub Actions sets
# CI=true), so a CI run cannot pass it vacuously.

def _import_gevent_util():
    try:
        import gevent.util
        return gevent.util
    except ImportError:
        if os.environ.get("CI"):
            pytest.fail("gevent is not installed; requirements-dev.txt pins it for this guard")
        pytest.skip("gevent is not installed (pip install -r requirements-dev.txt)")


@pytest.fixture
def hub_hold():
    util = _import_gevent_util()
    import gevent

    @contextlib.contextmanager
    def guard(max_ms):
        with util.assert_switches(max_blocking_time=max_ms / 1000.0, hub_only=True):
            # The tracer measures from the greenlet's LAST switch, not from
            # entering the block, so test setup that ran without yielding is
            # charged to the body (measured 2026-10-17 in Sentinelarr: a 5 ms
            # body failed a 50 ms limit). One switch to the hub starts it here.
            gevent.sleep(0)
            yield

    return guard
