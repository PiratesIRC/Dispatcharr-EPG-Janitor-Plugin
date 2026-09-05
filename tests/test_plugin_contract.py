"""Static contract tests for the plugin's settings and action surface.

The loader contract: the settings fields and the action list are declared TWICE,
once in plugin.json and once in the Plugin class inside plugin.py. At runtime
Dispatcharr serves the CLASS, so an entry added to plugin.json alone does
nothing, and an entry added to the class alone works but leaves the published
manifest wrong. Nothing checked that the two agreed, so both directions of drift
were silent. These tests close that.

Why this file parses instead of importing: plugin.py imports apps.channels.models,
apps.epg.models, celery and django at module scope, so it cannot be imported
outside a running Dispatcharr. The Plugin class declares `_base_fields` and
`actions` as plain list literals, so ast.literal_eval reads them exactly without
executing anything. The `fields` PROPERTY is not read here at all: it queries the
database to build the EPG source pickers, which is also why the count Dispatcharr
serves (measured at 42 on 2026-08-12) is larger than the 30 static entries.

Deliberately NOT ported from the sibling plugin Channel-Maparr: its two tests
banning astral-plane characters (any character above U+FFFF, such as an emoji).
Its notes record those characters silently dropping an action. That is not true
of this plugin on this Dispatcharr: measured 2026-08-12 against the real loader,
EPG Janitor declares 15 actions and Dispatcharr serves all 15, including
watchdog_run_check_now, whose button label contains the astral dog emoji
U+1F415. Porting the ban would have created a test asserting the opposite of what
the running system does.
"""
import ast
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PLUGIN_DIR = REPO_ROOT / "EPG-Janitor"
PLUGIN_JSON = PLUGIN_DIR / "plugin.json"
PLUGIN_PY = PLUGIN_DIR / "plugin.py"

# plugin.json carries emoji, so the Windows cp1252 default raises
# UnicodeDecodeError. Every read here is explicit about utf-8.
_ENCODING = "utf-8"


@pytest.fixture(scope="module")
def manifest():
    return json.loads(PLUGIN_JSON.read_text(encoding=_ENCODING))


@pytest.fixture(scope="module")
def plugin_source():
    return PLUGIN_PY.read_text(encoding=_ENCODING)


@pytest.fixture(scope="module")
def class_literals(plugin_source):
    """Every literal class attribute of Plugin, read without importing it."""
    tree = ast.parse(plugin_source)
    classes = [n for n in ast.walk(tree)
               if isinstance(n, ast.ClassDef) and n.name == "Plugin"]
    assert len(classes) == 1, "expected exactly one class named Plugin in plugin.py"
    out = {}
    for statement in classes[0].body:
        if not isinstance(statement, ast.Assign):
            continue
        for target in statement.targets:
            if not isinstance(target, ast.Name):
                continue
            try:
                out[target.id] = ast.literal_eval(statement.value)
            except (ValueError, SyntaxError):
                # A computed attribute. Not a declaration surface, so skip it.
                pass
    return out


@pytest.fixture(scope="module")
def class_fields(class_literals):
    fields = class_literals.get("_base_fields")
    assert isinstance(fields, list) and fields, (
        "Plugin._base_fields is no longer a plain list literal. If it became "
        "computed, this whole file stops checking anything and must be rewritten."
    )
    return fields


@pytest.fixture(scope="module")
def class_actions(class_literals):
    actions = class_literals.get("actions")
    assert isinstance(actions, list) and actions, (
        "Plugin.actions is no longer a plain list literal. If it became computed, "
        "this whole file stops checking anything and must be rewritten."
    )
    return actions


def test_manifest_is_valid_json(manifest):
    assert manifest["name"]
    assert manifest["version"]
    assert isinstance(manifest["fields"], list) and manifest["fields"]
    assert isinstance(manifest["actions"], list) and manifest["actions"]


def test_action_ids_match_between_manifest_and_class(manifest, class_actions):
    """Every action in plugin.json exists in Plugin.actions and the reverse."""
    manifest_ids = {a["id"] for a in manifest["actions"]}
    class_ids = {a["id"] for a in class_actions}
    assert manifest_ids == class_ids, (
        f"action drift: only in plugin.json={sorted(manifest_ids - class_ids)}, "
        f"only in Plugin.actions={sorted(class_ids - manifest_ids)}"
    )


def test_field_ids_match_between_manifest_and_class(manifest, class_fields):
    """Both directions. An entry present only in the class renders in the UI but
    is missing from the published manifest, and that direction is the one that
    went unnoticed: the freshness watchdog added six fields to the class in July
    2026 and none of them to plugin.json."""
    manifest_ids = {f["id"] for f in manifest["fields"]}
    class_ids = {f["id"] for f in class_fields}
    assert manifest_ids == class_ids, (
        f"field drift: only in plugin.json={sorted(manifest_ids - class_ids)}, "
        f"only in Plugin._base_fields={sorted(class_ids - manifest_ids)}"
    )


def test_field_definitions_match_between_manifest_and_class(manifest, class_fields):
    """Ids matching is not enough. Dispatcharr serves the CLASS (loader.py
    prefers the instance's `fields` property and falls back to the manifest only
    when the instance supplies none), so a help text or default edited in
    plugin.json alone changes nothing a user sees, and nothing failed.

    Measured 2026-08-16: five fields had diverged this way, and the divergence
    ran in the harmful direction for `epg_sources_to_match` -- the manifest
    carried the warning that leaving it empty matches foreign-country guides,
    which is a documented recurring trap, while the text users actually see did
    not mention it."""
    manifest_by_id = {f["id"]: f for f in manifest["fields"]}
    differing = {}
    for field in class_fields:
        published = manifest_by_id.get(field["id"], {})
        keys = set(field) | set(published)
        delta = {k: (field.get(k), published.get(k))
                 for k in keys if field.get(k) != published.get(k)}
        if delta:
            differing[field["id"]] = sorted(delta)
    assert differing == {}, (
        f"these fields differ beyond their id between Plugin._base_fields and "
        f"plugin.json: {differing}. The class is what Dispatcharr serves."
    )


def test_manifest_version_matches_class(manifest, class_literals):
    assert manifest["version"] == class_literals.get("version"), (
        f"version skew: plugin.json={manifest['version']!r} "
        f"Plugin.version={class_literals.get('version')!r}. "
        f"bump_version.py stamps plugin.json, plugin.py and fuzzy_matcher.py together."
    )


def test_every_class_action_has_a_button_label(class_actions):
    """Without button_label Dispatcharr renders a generic Run button."""
    missing = [a["id"] for a in class_actions if not a.get("button_label")]
    assert not missing, f"actions missing button_label: {missing}"


def test_every_class_action_has_a_button_color(class_actions):
    missing = [a["id"] for a in class_actions if not a.get("button_color")]
    assert not missing, f"actions missing button_color: {missing}"


def test_button_labels_match_between_manifest_and_class(manifest, class_actions):
    """The label text itself must agree, not merely the set of ids.

    This catches the lossy re-encoding signature, where an icon character is
    written into one of the two files as a literal question mark while the other
    keeps the real symbol.
    """
    class_labels = {a["id"]: a.get("button_label", "") for a in class_actions}
    mismatches = {
        a["id"]: {"plugin.json": a.get("button_label"),
                  "Plugin.actions": class_labels.get(a["id"])}
        for a in manifest["actions"]
        if a["id"] in class_labels and a.get("button_label") != class_labels[a["id"]]
    }
    assert not mismatches, (
        f"button_label drift between plugin.json and Plugin.actions: {mismatches}")


def test_no_placeholder_question_mark_in_button_labels(manifest, class_actions):
    """A literal question mark inside a button label is the fingerprint of an
    icon character that did not survive an encoding round trip."""
    bad_json = [a["id"] for a in manifest["actions"]
                if "?" in (a.get("button_label") or "")]
    bad_class = [a["id"] for a in class_actions
                 if "?" in (a.get("button_label") or "")]
    assert not bad_json, f"plugin.json button_labels contain a placeholder '?': {bad_json}"
    assert not bad_class, f"Plugin.actions button_labels contain a placeholder '?': {bad_class}"


def test_destructive_actions_declare_a_confirmation(class_actions):
    """Every action that permanently removes EPG assignments must put a
    confirmation dialog in front of it. These are one click away from wiping
    guide data across whole channel groups."""
    must_confirm = {
        "remove_epg_assignments",
        "remove_epg_from_hidden",
        "remove_epg_by_regex",
        "remove_all_epg_from_groups",
        "clear_csv_exports",
    }
    declared = {a["id"] for a in class_actions}
    unknown = must_confirm - declared
    assert not unknown, (
        f"this test names actions that no longer exist: {sorted(unknown)}. "
        f"Update the list rather than deleting the test.")
    missing = sorted(a["id"] for a in class_actions
                     if a["id"] in must_confirm and not a.get("confirm", {}).get("message"))
    assert not missing, f"destructive actions with no confirm message: {missing}"


@pytest.fixture(scope="module")
def action_map(plugin_source):
    """The `action_map` dict literal inside Plugin.run, as {action id: method name}.

    Read by parsing rather than by searching for the id as a substring. An
    earlier version of this test did search for the substring and was vacuous:
    the id it was looking for is declared in the same file it was searching, so
    the check could never fail.
    """
    tree = ast.parse(plugin_source)
    found = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "action_map" for t in node.targets):
            continue
        assert isinstance(node.value, ast.Dict), "action_map is no longer a dict literal"
        for key, value in zip(node.value.keys, node.value.values, strict=True):
            assert isinstance(key, ast.Constant) and isinstance(key.value, str), (
                "an action_map key is not a plain string")
            assert isinstance(value, ast.Attribute), (
                f"action_map[{key.value!r}] is not a self.<method> reference")
            found[key.value] = value.attr
    assert found, "no action_map dict literal found in plugin.py"
    return found


def test_action_map_covers_exactly_the_declared_actions(class_actions, action_map):
    """run() dispatches through action_map. An action declared but absent from
    that dict reaches the user as a button that returns 'Unknown action', and an
    entry in the dict with no declared action is unreachable code."""
    declared = {a["id"] for a in class_actions}
    routed = set(action_map)
    assert declared == routed, (
        f"declared but not routed in action_map={sorted(declared - routed)}, "
        f"routed but not declared={sorted(routed - declared)}"
    )


def test_every_routed_handler_method_exists(action_map, plugin_source):
    """Each self.<name> in action_map must be a method actually defined here."""
    missing = sorted(name for name in action_map.values()
                     if f"def {name}(" not in plugin_source)
    assert not missing, f"action_map names methods that do not exist: {missing}"


# ---------------------------------------------------------------------------
# Failure returns must be visible in Dispatcharr's plugin card.
#
# The card renders exactly three keys: `message` (green, transient, closes
# itself after four seconds), `error` (red, persistent) and `file`. The `status`
# value renders NOWHERE. So a return of {"status": "error", "message": ...} is
# indistinguishable from success to the person looking at the screen.
#
# Measured across this workspace on 2026-08-16: Channel-Maparr sets `error` on
# all 47 of its status-error returns and Dustarr on 7 of 8, while this plugin
# set it on 0 of 40.
#
# This is a static check on purpose. It covers every return site at once and
# cannot go stale as new actions are added, which a hand-written list of cases
# could not do.
# ---------------------------------------------------------------------------


def _status_error_returns(tree):
    """Every `return {...}` whose "status" is the literal "error"."""
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Return) or not isinstance(node.value, ast.Dict):
            continue
        pairs = {}
        # A Dict node always reports keys and values in step (a `**spread`
        # entry contributes a None key), so strict= is safe and catches any
        # future ast change that breaks that assumption.
        for key, value in zip(node.value.keys, node.value.values, strict=True):
            if isinstance(key, ast.Constant):
                pairs[key.value] = value
        status = pairs.get("status")
        if isinstance(status, ast.Constant) and status.value == "error":
            found.append((node.lineno, pairs))
    return found


def test_the_plugin_still_reports_failures_at_all():
    """Guard against this contract being satisfied by deleting every failure
    path rather than by surfacing them."""
    tree = ast.parse(PLUGIN_PY.read_text(encoding=_ENCODING))
    assert len(_status_error_returns(tree)) >= 20


def test_every_failure_return_sets_the_error_key():
    tree = ast.parse(PLUGIN_PY.read_text(encoding=_ENCODING))
    offenders = [line for line, pairs in _status_error_returns(tree)
                 if "error" not in pairs]
    assert offenders == [], (
        f"{len(offenders)} returns set status=error but no 'error' key, so they "
        f"render as a transient green toast and look like success. Lines: "
        f"{offenders}"
    )


def test_the_matcher_module_version_matches_the_manifest(manifest):
    """bump_version.py stamps three files. Only two of them were compared.

    fuzzy_matcher.py carries its own __version__ and nothing checked it, so a
    partial bump could ship a matcher module reporting a version that does not
    exist.
    """
    source = (PLUGIN_DIR / "fuzzy_matcher.py").read_text(encoding=_ENCODING)
    tree = ast.parse(source)
    declared = None
    for node in tree.body:
        if (isinstance(node, ast.Assign)
                and any(getattr(t, "id", None) == "__version__" for t in node.targets)):
            declared = ast.literal_eval(node.value)
    assert declared is not None, "fuzzy_matcher.py no longer declares __version__"
    assert declared == manifest["version"], (
        f"version skew: fuzzy_matcher.__version__={declared!r} "
        f"plugin.json={manifest['version']!r}")
