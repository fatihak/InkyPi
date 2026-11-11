import os
import sys
from unittest import mock

import pytest
from flask import Flask

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from model import Playlist, PlaylistManager, PluginInstance  # noqa: E402
from blueprints.playlist import playlist_bp  # noqa: E402


def _playlist(names, index=None, disabled=()):
    plugins = [{"plugin_id": "clock", "name": n, "plugin_settings": {}, "refresh": {"interval": 60},
                "enabled": n not in disabled} for n in names]
    return Playlist("P", "00:00", "24:00", plugins, current_plugin_index=index)


def test_next_plugin_skips_disabled_instances():
    playlist = _playlist(["a", "b", "c"], disabled=("b",))
    assert [playlist.get_next_plugin().name for _ in range(4)] == ["a", "c", "a", "c"]


def test_next_plugin_none_when_all_disabled():
    playlist = _playlist(["a", "b"], index=1, disabled=("a", "b"))
    assert playlist.get_next_plugin() is None
    assert playlist.current_plugin_index == 1
    assert Playlist("E", "00:00", "24:00").get_next_plugin() is None


def test_move_plugin_keeps_rotation_on_same_instance():
    playlist = _playlist(["a", "b", "c"], index=1)  # 'b' currently shown
    assert playlist.move_plugin("clock", "b", -1)
    assert [p.name for p in playlist.plugins] == ["b", "a", "c"]
    assert playlist.plugins[playlist.current_plugin_index].name == "b"
    assert playlist.get_next_plugin().name == "a"
    playlist.move_plugin("clock", "c", 5)  # clamped at the end
    assert [p.name for p in playlist.plugins] == ["b", "a", "c"]
    assert not playlist.move_plugin("clock", "missing", 1)


def test_enabled_round_trips_and_defaults_to_true():
    old = PluginInstance.from_dict({"plugin_id": "x", "name": "n", "plugin_settings": {}, "refresh": {}})
    assert old.enabled is True
    paused = PluginInstance.from_dict({**old.to_dict(), "enabled": False})
    assert paused.enabled is False and paused.to_dict()["enabled"] is False


@pytest.fixture
def client():
    app = Flask(__name__)
    app.register_blueprint(playlist_bp)
    manager = PlaylistManager([_playlist(["a", "b"])])
    config = mock.Mock()
    config.get_playlist_manager.return_value = manager
    app.config["DEVICE_CONFIG"] = config
    return app.test_client(), manager, config


def test_move_and_enable_endpoints(client):
    http, manager, config = client
    body = {"playlist_name": "P", "plugin_id": "clock", "plugin_instance": "b"}
    assert http.post("/move_plugin_instance", json={**body, "direction": "up"}).status_code == 200
    assert [p.name for p in manager.get_playlist("P").plugins] == ["b", "a"]
    assert http.post("/set_plugin_instance_enabled", json={**body, "enabled": False}).status_code == 200
    assert manager.get_playlist("P").find_plugin("clock", "b").enabled is False
    assert config.write_config.call_count == 2


@pytest.mark.parametrize("payload", [
    {"playlist_name": "P", "plugin_id": "clock", "plugin_instance": "a", "direction": "left"},
    {"playlist_name": "nope", "plugin_id": "clock", "plugin_instance": "a", "direction": "up"},
    {"playlist_name": "P", "plugin_id": "clock", "plugin_instance": "zz", "direction": "up"},
])
def test_move_endpoint_rejects_bad_requests(client, payload):
    assert client[0].post("/move_plugin_instance", json=payload).status_code == 400


def test_enable_endpoint_requires_boolean(client):
    body = {"playlist_name": "P", "plugin_id": "clock", "plugin_instance": "a", "enabled": "false"}
    assert client[0].post("/set_plugin_instance_enabled", json=body).status_code == 400
