"""Every file the plugin needs at run time must actually be shipped.

The plugin is installed by copying its package directory somewhere else: into
the Dispatcharr container, into a release archive, or into the Plugin Hub's own
repository as a listing. Each of those copies is made from a file list, and a
file list can be incomplete. When it is, the failure depends on which file was
left out:

- a module reached by a relative import fails at IMPORT, so the plugin does not
  load at all and every setting and action disappears;
- a data file read at run time usually degrades instead, which is quieter and
  therefore easier to ship.

Measured 2026-08-12: the Plugin Hub listing carried 24 files while the plugin
shipped 26. The two missing were epg_watchdog.py, which plugin.py imports
unconditionally, and us_station_callsigns.json. That listing was internally
consistent because it pinned an older version that predated both files, but the
same omission at the moment of a version bump would have published a plugin that
could not import.

These tests read the requirements out of the source rather than from a
hand-maintained list, so a module added later is covered without anyone
remembering to update anything. scripts/check_hub_listing.py performs the
matching check against the Plugin Hub, which needs the network and so cannot
live here.
"""
import ast
import pathlib
import re
import subprocess

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
PLUGIN_DIR = REPO_ROOT / "EPG-Janitor"


@pytest.fixture(scope="module")
def tracked_package_files():
    """The file set git would ship, which is what every copy is made from.

    Deliberately not a directory listing: an untracked file is present on this
    machine and absent everywhere else, which is the failure being guarded
    against.
    """
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-tree", "--name-only", "HEAD:EPG-Janitor"],
        capture_output=True, text=True, check=True).stdout
    names = {line.strip() for line in out.splitlines() if line.strip()}
    assert names, "git listed no files for the plugin package"
    return names


def _relative_imports():
    """Module names reached by a relative import from any shipped module."""
    found = set()
    for source_file in sorted(PLUGIN_DIR.glob("*.py")):
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level == 0:
                continue
            if node.module:
                # from .aliases import X  ->  aliases
                found.add(node.module.split(".")[0])
            else:
                # from . import a, b  ->  a, b
                found.update(alias.name for alias in node.names)
    return found


def test_every_relatively_imported_module_is_shipped(tracked_package_files):
    """A missing module here does not degrade the plugin, it stops it loading."""
    imported = _relative_imports()
    assert imported, "no relative imports found, so this test proves nothing"
    missing = sorted(name for name in imported
                     if f"{name}.py" not in tracked_package_files)
    assert not missing, (
        f"modules imported by the plugin but not shipped: {missing}. "
        f"The plugin will fail at import wherever it is installed from this file set."
    )


def test_named_data_files_are_shipped(tracked_package_files):
    """Data files named by a module-level constant, e.g. the callsign allowlist.

    These degrade rather than crash, which is exactly why they need a gate: a
    plugin shipped without one behaves like a plugin whose file failed to load.
    """
    referenced = set()
    for source_file in sorted(PLUGIN_DIR.glob("*.py")):
        text = source_file.read_text(encoding="utf-8")
        # A constant assigned a bare .json filename, e.g. _X_FILE = "y.json"
        referenced.update(re.findall(r'^\s*_[A-Z_]+\s*=\s*"([^"/\\]+\.json)"',
                                     text, re.MULTILINE))
    assert referenced, "no named data files found, so this test proves nothing"
    missing = sorted(name for name in referenced if name not in tracked_package_files)
    assert not missing, f"data files named in the source but not shipped: {missing}"


def test_at_least_one_channel_database_is_shipped(tracked_package_files):
    """The matcher globs *_channels.json out of its own directory and only warns
    when it finds none, so an empty glob is silent."""
    databases = sorted(n for n in tracked_package_files if n.endswith("_channels.json"))
    assert databases, "no *_channels.json shipped; the matcher would load nothing and only warn"
    assert "US_channels.json" in databases, (
        "the US database is the canonical superset for the other countries and must ship")


def test_the_loader_entry_point_is_shipped(tracked_package_files):
    """Dispatcharr's loader imports the package and expects Plugin exported."""
    assert "__init__.py" in tracked_package_files
    assert "plugin.json" in tracked_package_files, "the manifest is how the loader finds the plugin"
    init_text = (PLUGIN_DIR / "__init__.py").read_text(encoding="utf-8")
    assert "Plugin" in init_text, "__init__.py must export Plugin (loader contract)"
