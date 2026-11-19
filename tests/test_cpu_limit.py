import os
import sys
import subprocess
from unittest import mock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from utils import cpu_limit  # noqa: E402


@pytest.mark.parametrize("model,cpus,expected", [
    ("Raspberry Pi Zero W Rev 1.1", 1, 40),
    ("Raspberry Pi Zero 2 W Rev 1.0", 4, 100),
    ("Raspberry Pi 3 Model B Plus Rev 1.3", 4, 200),
    ("Raspberry Pi 4 Model B Rev 1.5", 4, 300),
    ("Raspberry Pi 5 Model B Rev 1.0", 4, 300),
    ("", 2, 150),
])
def test_recommended_percent(model, cpus, expected):
    assert cpu_limit.recommended_percent(model, cpus) == expected


def test_target_and_parse():
    assert cpu_limit.target_percent("default") is None
    assert cpu_limit.target_percent("auto", model="Raspberry Pi 4 Model B", cpus=4) == 300
    assert cpu_limit.target_percent("manual", "150%", cpus=4) == 150
    for bad in ("10", "500", "abc", ""):
        with pytest.raises(ValueError):
            cpu_limit.parse_percent(bad, cpus=4)


def _result(stdout="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="boom" if returncode else "")


@pytest.mark.parametrize("value,expected", [("400ms", 40), ("2s", 200), ("1.5s", 150), ("infinity", None), ("", None)])
def test_current_percent(value, expected):
    with mock.patch.object(cpu_limit, "_systemctl", return_value=_result(value + "\n")):
        assert cpu_limit.current_percent() == expected


def test_apply_sets_or_reverts_the_property(tmp_path, monkeypatch):
    dropin = tmp_path / "50-CPUQuota.conf"
    dropin.write_text("[Service]\nCPUQuota=300%\n")
    monkeypatch.setattr(cpu_limit, "_CONTROL_DROPINS", (str(dropin), str(tmp_path / "missing.conf")))
    with mock.patch.object(cpu_limit, "_systemctl", return_value=_result()) as systemctl:
        cpu_limit.apply(300)
        systemctl.assert_called_with("set-property", "inkypi.service", "CPUQuota=300%")
        cpu_limit.apply(None)
        systemctl.assert_called_with("daemon-reload")
    assert not dropin.exists()
    with mock.patch.object(cpu_limit, "_systemctl", return_value=_result(returncode=1)):
        with pytest.raises(RuntimeError, match="boom"):
            cpu_limit.apply(200)
