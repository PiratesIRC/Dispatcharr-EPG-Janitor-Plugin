"""Tests that import plugin.py for real, with Dispatcharr and Django stubbed.

Until now no test in this repository imported plugin.py at all, because it does
`from apps.channels.models import ...`, `from django.db import ...`, `import
celery` and `from core.utils import ...` at module scope. That left 1,385
statements, a little over half the shipped code, with no test coverage of any
kind, while every one of the six sibling plugins in this workspace imports its
own plugin.py in tests.

The `plugin_module` fixture in conftest.py registers stand-ins for those modules
and loads the hyphenated plugin directory as a package, which is the approach
already proven in the sibling plugin Channel-Maparr.

What this does NOT give: anything that executes a query. The stubs answer
attribute access, not semantics. These tests therefore assert on the module's
static surface and on pure helpers, not on database behaviour.
"""


def test_the_plugin_module_imports_with_dispatcharr_stubbed(plugin_module):
    assert plugin_module.Plugin is not None


def test_the_plugin_class_declares_the_actions_the_manifest_publishes(plugin_module, manifest):
    declared = [a["id"] for a in plugin_module.Plugin.actions]
    published = [a["id"] for a in manifest["actions"]]
    assert declared == published


def test_every_action_id_has_a_matching_handler_method(plugin_module):
    """Dispatcharr routes an action by id. An id with no handler is a button
    that fails only when somebody presses it."""
    plugin = plugin_module.Plugin
    missing = [a["id"] for a in plugin.actions
               if not hasattr(plugin, a["id"] + "_action")]
    assert missing == []
