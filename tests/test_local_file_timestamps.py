"""Report and CSV file names carry Dispatcharr's local time, not UTC.

The Celery worker clock is UTC, so names built from datetime.now(UTC) showed
five hours early against the operator's clock. The names now come from the
same timezone source as the result views (progress_status.format_local_now).
"""

import pathlib
import re
import sys
import zoneinfo

REPO = pathlib.Path(__file__).resolve().parents[1]
PLUGIN_SOURCE = (REPO / "EPG-Janitor" / "plugin.py").read_text(encoding="utf-8")

LOCAL_STAMP = re.compile(r"""format_local_now\(fmt=["']%Y%m%d_%H%M%S["']\)""")


def test_no_file_name_is_built_from_the_utc_clock():
    assert not re.search(r"datetime\.now\(tz=dt_timezone\.utc\)\.strftime", PLUGIN_SOURCE)


def test_the_four_file_names_use_the_local_stamp():
    # automatch export, heal export, removal export, results export
    assert len(LOCAL_STAMP.findall(PLUGIN_SOURCE)) == 4


def test_the_local_stamp_is_dispatcharr_local_time(plugin_module, monkeypatch):
    progress_status = sys.modules[plugin_module.__name__ + ".progress_status"]
    chicago = zoneinfo.ZoneInfo("America/Chicago")
    monkeypatch.setattr(progress_status, "_display_tz", lambda: chicago)
    # Unix epoch 0 is 1969-12-31 18:00 in Central time.
    assert progress_status.format_local_timestamp(0, fmt="%Y%m%d_%H%M%S") == "19691231_180000"
