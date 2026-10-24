"""Assigning EPG through _batch_set_epg must queue the programme parse.

Dispatcharr queues the parse for a newly assigned EPG entry from a Channel
post_save signal. bulk_update sends no signal, so before this fix every
channel Apply Auto-Match or Scan & Heal assigned stayed without programmes
until the source's next scheduled refresh, which can be days away.

The stand-ins below are plain objects that record what the plugin did with
them. They do not emulate a queryset; they let the test assert on which EPG
ids the plugin hands to Dispatcharr's own dispatch function.
"""
import contextlib
import logging
import sys
import types

import pytest


class _Channel:
    def __init__(self, cid, epg_data_id):
        self.id = cid
        self.epg_data_id = epg_data_id


class _Manager:
    def __init__(self, channels):
        self._channels = {c.id: c for c in channels}
        self.bulk_updated = []

    def filter(self, id__in):
        return [self._channels[i] for i in id__in if i in self._channels]

    def bulk_update(self, objs, fields):
        self.bulk_updated.append(([o.id for o in objs], list(fields)))


@pytest.fixture
def plugin_py(plugin_module):
    return sys.modules[plugin_module.Plugin.__module__]


@pytest.fixture
def channels(plugin_py, monkeypatch):
    manager = _Manager([_Channel(1, 10), _Channel(2, 30), _Channel(3, None)])
    monkeypatch.setattr(plugin_py, "Channel", types.SimpleNamespace(objects=manager))
    monkeypatch.setattr(plugin_py, "transaction",
                        types.SimpleNamespace(atomic=contextlib.nullcontext))
    return manager


def _install_dispatch(monkeypatch, fn):
    tasks = types.SimpleNamespace(dispatch_program_refresh_for_epg_ids=fn)
    monkeypatch.setitem(sys.modules, "apps.epg.tasks", tasks)


def test_changed_assignments_queue_programme_parse(plugin_module, channels, monkeypatch):
    queued = []
    _install_dispatch(monkeypatch, lambda ids: queued.append(sorted(ids)) or len(ids))
    inst = plugin_module.Plugin.__new__(plugin_module.Plugin)

    result = inst._batch_set_epg(
        [{"channel_id": 1, "epg_data_id": 20},   # changed 10 -> 20
         {"channel_id": 2, "epg_data_id": 30},   # unchanged
         {"channel_id": 3, "epg_data_id": 40}],  # newly assigned
        logging.getLogger("test"))

    assert result["channels_updated"] == 3
    assert channels.bulk_updated == [([1, 2, 3], ["epg_data_id"])]
    assert queued == [[20, 40]]
    assert result["programs_queued"] == 2


def test_parse_dispatch_failure_does_not_undo_the_assignment(plugin_module, channels,
                                                              monkeypatch, caplog):
    def boom(ids):
        raise RuntimeError("broker down")
    _install_dispatch(monkeypatch, boom)
    inst = plugin_module.Plugin.__new__(plugin_module.Plugin)

    with caplog.at_level(logging.WARNING):
        result = inst._batch_set_epg([{"channel_id": 1, "epg_data_id": 20}],
                                     logging.getLogger("test"))

    assert result["channels_updated"] == 1
    assert result["programs_queued"] == 0
    assert channels.bulk_updated == [([1], ["epg_data_id"])]
    assert "broker down" in caplog.text
