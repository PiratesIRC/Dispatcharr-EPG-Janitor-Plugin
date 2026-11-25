"""EPG Janitor's storage: where its private state lives and what moves over from /data.

The logic (resolving the data directory, carrying the old /data state over, the tally tail and
binding the state constants) is in plugin_storage.py, a vendored copy of _shared/plugin_storage.py.
This module holds only what belongs to this plugin: the Spec, the table of state paths, the name
kept beside the data directories and the rollout switch. Each public function passes SPEC to the
vendored module, so callers see the same names they always did.
"""
from __future__ import annotations

try:
    from . import plugin_storage as _ps
except ImportError:  # loaded as a bare module, as plugin.py allows
    import plugin_storage as _ps

# Rollout switch for this release only: remove in the release after next, with the dual-path
# branches it guards. While it is on, a worker on this code also honours the old progress file
# that workers on the previous release still write (the single-flight scan guard).
ROLLOUT_DUAL_PATHS = True

# (constant name, kind, rel under the data dir). The progress file lives beside the data dirs,
# named in _BESIDE, because it is the scan's cross-worker single-flight claim.
_BIND_TABLE = (
    ("RESULTS_FILE", "file", "epg_janitor_results.json"),
    ("PROGRESS_FILE", "beside", None),
    ("MATCH_LEDGER_FILE", "tally", "epg_janitor_match_counts.jsonl"),
    ("USAGE_DATA_DIR", "usage_dir", "usage"),
)

_BESIDE = {
    "PROGRESS_FILE": ".progress.json",
}

SPEC = _ps.Spec(
    label="EPG Janitor",
    state_name="_epg_janitor_storage_state",
    table=_BIND_TABLE,
    beside=_BESIDE,
    reports_subdir=None,
    usage_subdir="epg-janitor",
    tally_offsets="epg_janitor_match_counts.offsets.json",
    tally_lock="epg_janitor_match_counts.lock",
    reports_constant="REPORTS_DIR_UNUSED",
)

Layout = _ps.Layout
Item = _ps.Item
MigrateResult = _ps.MigrateResult
atomic_write_bytes = _ps.atomic_write_bytes
atomic_write_json = _ps.atomic_write_json


def resolve(plugin_dir, key, logger):
    """Resolve the data directory for the plugin folder plugin_dir. See plugin_storage.resolve."""
    return _ps.resolve(SPEC, plugin_dir, key, logger)


def migrate(layout, items, logger, version=None):
    """Copy the old state into the data dir once. See plugin_storage.migrate."""
    return _ps.migrate(SPEC, layout, items, logger, version=version)


def sync_tally_tail(layout, tally_path, logger):
    """Append the tally's new old-source bytes to it. See plugin_storage.sync_tally_tail."""
    return _ps.sync_tally_tail(SPEC, layout, tally_path, logger)


def items_for(cfg, layout):
    """The moves bind hands to migrate. See plugin_storage.items_for."""
    return _ps.items_for(SPEC, cfg, layout)


def bind(cfg, plugin_file, logger):
    """Resolve, rebind the state constants and carry the old state over. See plugin_storage.bind."""
    return _ps.bind(SPEC, cfg, plugin_file, logger)


def check_context(layout, context, logger):
    """Warn once when Dispatcharr's data_dir differs from the resolved one. See plugin_storage."""
    return _ps.check_context(SPEC, layout, context, logger)
