"""Test package for EPG-Janitor.

Prepends the plugin directory to sys.path so tests can import
`fuzzy_matcher`, `aliases`, etc. as top-level modules.
"""
import os
import sys

_PLUGIN_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "EPG-Janitor")
)
if _PLUGIN_DIR not in sys.path:
    sys.path.insert(0, _PLUGIN_DIR)
