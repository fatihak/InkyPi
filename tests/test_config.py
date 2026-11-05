import json
import os
import sys
from unittest.mock import Mock, patch

import pytest

# config.py imports its siblings as top-level modules (`from model import ...`).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from src.config import Config  # noqa: E402


def _config_at(path, data):
    """Build a Config that reads/writes `path`, skipping the real __init__."""
    path.write_text(json.dumps(data))
    config = Config.__new__(Config)
    config.config_file = str(path)
    config.config = dict(data)
    config.playlist_manager = Mock(to_dict=Mock(return_value={"playlists": []}))
    config.refresh_info = Mock(to_dict=Mock(return_value={}))
    return config


def test_write_config_keeps_old_file_if_write_fails(tmp_path):
    """A failure mid-write (crash, power glitch) must leave the previous
    device.json intact instead of an empty or half-written file."""
    path = tmp_path / "device.json"
    config = _config_at(path, {"name": "InkyPi", "display_type": "epd7in3e"})

    with patch("src.config.json.dump", side_effect=OSError("simulated crash")):
        with pytest.raises(OSError):
            config.write_config()

    assert json.loads(path.read_text())["display_type"] == "epd7in3e"
    assert [p.name for p in tmp_path.iterdir()] == ["device.json"]  # no temp file left behind


def test_write_config_writes_new_content(tmp_path):
    path = tmp_path / "device.json"
    config = _config_at(path, {"name": "InkyPi"})
    config.config["name"] = "Renamed"

    config.write_config()

    saved = json.loads(path.read_text())
    assert saved["name"] == "Renamed"
    assert saved["playlist_config"] == {"playlists": []}
    assert [p.name for p in tmp_path.iterdir()] == ["device.json"]
