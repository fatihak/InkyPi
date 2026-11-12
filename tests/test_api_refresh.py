import pytest
from flask import Flask

from blueprints.main import main_bp
from model import PlaylistManager, RefreshInfo
from refresh_task import PlaylistRefresh


class FakeDeviceConfig:
    def __init__(self, refresh_info, playlist_manager):
        self._refresh_info = refresh_info
        self._playlist_manager = playlist_manager

    def get_refresh_info(self):
        return self._refresh_info

    def get_playlist_manager(self):
        return self._playlist_manager


class FakeRefreshTask:
    def __init__(self, running=True, error=None):
        self.running = running
        self.error = error
        self.actions = []

    def manual_update(self, refresh_action):
        if self.error:
            raise self.error
        self.actions.append(refresh_action)


def make_playlist_manager():
    return PlaylistManager.from_dict({
        "active_playlist": "Default",
        "playlists": [{
            "name": "Default",
            "start_time": "00:00",
            "end_time": "24:00",
            "plugins": [{
                "plugin_id": "image_url",
                "name": "Dashboard",
                "plugin_settings": {"url": "http://example.invalid/dash.png"},
                "refresh": {"interval": 3600},
            }],
        }],
    })


def make_refresh_info(**overrides):
    values = {
        "refresh_type": "Playlist",
        "plugin_id": "image_url",
        "refresh_time": "2026-01-01T10:00:00+00:00",
        "image_hash": "abc",
        "playlist": "Default",
        "plugin_instance": "Dashboard",
    }
    values.update(overrides)
    return RefreshInfo(**values)


def make_client(refresh_info=None, refresh_task=None, playlist_manager=None):
    refresh_task = refresh_task or FakeRefreshTask()
    app = Flask(__name__)
    app.config["DEVICE_CONFIG"] = FakeDeviceConfig(
        refresh_info or make_refresh_info(), playlist_manager or make_playlist_manager()
    )
    app.config["REFRESH_TASK"] = refresh_task
    app.register_blueprint(main_bp)
    return app.test_client(), refresh_task


class TestApiRefresh:

    def test_refreshes_what_is_currently_displayed(self):
        client, task = make_client()

        response = client.post("/api/refresh")

        assert response.status_code == 200
        assert response.get_json() == {
            "success": True,
            "message": "Display refreshed",
            "playlist": "Default",
            "plugin_id": "image_url",
            "plugin_instance": "Dashboard",
        }
        assert len(task.actions) == 1
        action = task.actions[0]
        assert isinstance(action, PlaylistRefresh)
        assert action.force is True
        assert action.playlist.name == "Default"
        assert action.plugin_instance.name == "Dashboard"

    def test_does_not_need_a_request_body(self):
        client, task = make_client()

        response = client.post("/api/refresh", data="not json", content_type="text/plain")

        assert response.status_code == 200
        assert len(task.actions) == 1

    def test_get_is_not_allowed(self):
        client, task = make_client()

        response = client.get("/api/refresh")

        assert response.status_code == 405
        assert task.actions == []

    def test_refresh_task_not_running(self):
        client, task = make_client(refresh_task=FakeRefreshTask(running=False))

        response = client.post("/api/refresh")

        assert response.status_code == 503
        assert response.get_json()["success"] is False
        assert task.actions == []

    def test_nothing_displayed_yet(self):
        client, task = make_client(refresh_info=make_refresh_info(
            refresh_type=None, plugin_id=None, playlist=None, plugin_instance=None))

        response = client.post("/api/refresh")

        assert response.status_code == 409
        assert "Nothing has been displayed" in response.get_json()["error"]
        assert task.actions == []

    def test_current_image_from_manual_update_cannot_be_refreshed(self):
        client, task = make_client(refresh_info=make_refresh_info(
            refresh_type="Manual Update", playlist=None, plugin_instance=None))

        response = client.post("/api/refresh")

        assert response.status_code == 409
        assert "manual update" in response.get_json()["error"]
        assert task.actions == []

    @pytest.mark.parametrize("overrides", [
        {"plugin_instance": "Deleted instance"},
        {"playlist": "Deleted playlist"},
        {"plugin_id": "weather"},
    ])
    def test_displayed_item_no_longer_in_a_playlist(self, overrides):
        client, task = make_client(refresh_info=make_refresh_info(**overrides))

        response = client.post("/api/refresh")

        assert response.status_code == 409
        assert "no longer exists" in response.get_json()["error"]
        assert task.actions == []

    def test_refresh_error_is_reported(self):
        client, task = make_client(refresh_task=FakeRefreshTask(error=RuntimeError("fetch failed")))

        response = client.post("/api/refresh")

        assert response.status_code == 500
        assert response.get_json() == {"success": False, "error": "An error occurred: fetch failed"}
