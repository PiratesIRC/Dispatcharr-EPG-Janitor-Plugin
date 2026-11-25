"""plugin_storage._lock creates its lock file readable and writable by its owner only.

The Dispatcharr Plugin Hub runs CodeQL on the released archive and refuses a pull request on a
high finding. Mode 0o644 on the lock file's os.open raised py/overly-permissive-file on
Dispatcharr/Plugins#628, and so did 0o660 (group writable). Every Dispatcharr worker runs as one
user, so the mode is 0o600.
"""
import os
import pathlib
import re
import stat
import sys

import pytest

PLUGIN_STORAGE = pathlib.Path(__file__).resolve().parent.parent / "EPG-Janitor" / "plugin_storage.py"


def test_no_world_bits_in_any_os_open_mode():
    source = PLUGIN_STORAGE.read_text(encoding="utf-8")
    modes = re.findall(r"os\.open\([^)]*?(0o[0-7]{3})\)", source)
    assert modes, "no os.open mode found; the check would pass vacuously"
    for mode in modes:
        assert int(mode, 8) & 0o077 == 0, f"os.open mode {mode} grants access beyond the owner"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
def test_created_lock_file_has_no_world_bits(plugin_impl, tmp_path):
    lock_path = str(tmp_path / "x.lock")
    old_umask = os.umask(0)
    try:
        with plugin_impl.storage._ps._lock(lock_path):
            pass
    finally:
        os.umask(old_umask)
    assert stat.S_IMODE(os.stat(lock_path).st_mode) & 0o077 == 0
