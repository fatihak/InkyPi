import pytest
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from blueprints.system_info import (
    _format_bytes,
    _get_cpu_info,
    _get_cpu_freq,
    _get_cpu_cur_freq,
    _get_cpu_max_freq,
    _get_arm_cpu_model,
    _get_installed_ram,
    _read_sysfs_freq,
    _get_memory_info,
    _get_storage_info,
    _get_os_info,
    _get_device_model,
    _get_uptime,
    _get_last_boot,
    _get_local_ip,
    _get_hostname,
    _get_display_info,
    _get_kernel_info,
    _get_device_name,
    _get_architecture,
    _get_temperature,
    _is_wsl,
    _get_host_physical_memory,
    _ram_secondary,
    _parse_epd_code,
    _resolve_display_name,
    _collect_system_info,
    _format_time_ago,
    _collect_overview,
    _collect_plugin_info,
)


class TestFormatBytes:
    def test_bytes(self):
        assert _format_bytes(500) == "500.0 B"

    def test_kilobytes(self):
        assert _format_bytes(1024) == "1.0 KB"

    def test_megabytes(self):
        assert _format_bytes(1024 * 1024) == "1.0 MB"

    def test_gigabytes(self):
        assert _format_bytes(1024 ** 3) == "1.0 GB"

    def test_terabytes(self):
        assert _format_bytes(1024 ** 4) == "1.0 TB"


class TestGetCpuFreq:
    @patch("blueprints.system_info.psutil")
    def test_psutil_current(self, mock_psutil):
        mock_psutil.cpu_freq.return_value = MagicMock(current=2500.0, max=3000.0)
        assert _get_cpu_freq() == "2.5 GHz"

    @patch("blueprints.system_info.psutil")
    def test_psutil_max_fallback(self, mock_psutil):
        mock_psutil.cpu_freq.return_value = MagicMock(current=0.0, max=1800.0)
        assert _get_cpu_freq() == "1.8 GHz"

    @patch("blueprints.system_info.psutil")
    def test_psutil_none_falls_through(self, mock_psutil):
        mock_psutil.cpu_freq.return_value = None
        with patch("builtins.open", side_effect=FileNotFoundError):
            assert _get_cpu_freq() is None

    @patch("blueprints.system_info.psutil", new=None)
    def test_no_psutil_reads_proc_cpuinfo(self):
        cpuinfo = "cpu MHz\t: 1000.000\n"
        with patch("builtins.open", MagicMock(
            return_value=MagicMock(
                __enter__=MagicMock(return_value=iter(cpuinfo.splitlines(True))),
                __exit__=MagicMock(return_value=False),
            )
        )):
            assert _get_cpu_freq() == "1.0 GHz"


class TestGetCpuInfo:
    def setup_method(self):
        if hasattr(_get_cpu_info, "_cache"):
            del _get_cpu_info._cache

    @patch("blueprints.system_info._get_cpu_max_freq", return_value=None)
    @patch("blueprints.system_info._get_cpu_cur_freq", return_value=None)
    @patch("blueprints.system_info._get_cpu_freq", return_value=None)
    @patch("blueprints.system_info._get_arm_cpu_model", return_value=None)
    @patch("builtins.open", side_effect=FileNotFoundError)
    @patch("platform.processor", return_value="x86_64")
    def test_fallback_to_platform(self, mock_proc, mock_open, mock_arm, mock_freq, mock_cur, mock_max):
        result = _get_cpu_info()
        assert result["model"] == "x86_64"
        assert result["freq"] is None
        assert result["cur_freq"] is None
        assert result["max_freq"] is None
        assert result["cores"] is None

    @patch("blueprints.system_info._get_cpu_max_freq", return_value="3.0 GHz")
    @patch("blueprints.system_info._get_cpu_cur_freq", return_value="2.5 GHz")
    @patch("blueprints.system_info._get_cpu_freq", return_value="2.5 GHz")
    @patch("blueprints.system_info._get_arm_cpu_model", return_value=None)
    @patch("builtins.open")
    def test_reads_proc_cpuinfo(self, mock_open, mock_arm, mock_freq, mock_cur, mock_max):
        cpuinfo_content = "processor\t: 0\nmodel name\t: Intel(R) Core(TM) i5-12400\nprocessor\t: 1\nmodel name\t: Intel(R) Core(TM) i5-12400\n"
        mock_open.return_value = MagicMock(
            __enter__=MagicMock(return_value=iter(cpuinfo_content.splitlines(True))),
            __exit__=MagicMock(return_value=False),
        )
        result = _get_cpu_info()
        assert "i5-12400" in result["model"]
        assert result["cores"] == 2
        assert result["freq"] == "2.5 GHz"
        assert result["cur_freq"] == "2.5 GHz"
        assert result["max_freq"] == "3.0 GHz"


class TestIsWsl:
    @patch("builtins.open")
    def test_detects_wsl(self, mock_open):
        mock_open.return_value = MagicMock(
            __enter__=MagicMock(return_value=MagicMock(read=MagicMock(
                return_value="Linux version 5.15.0 (Microsoft)"
            ))),
            __exit__=MagicMock(return_value=False),
        )
        assert _is_wsl() is True

    @patch("builtins.open")
    def test_non_wsl(self, mock_open):
        mock_open.return_value = MagicMock(
            __enter__=MagicMock(return_value=MagicMock(read=MagicMock(
                return_value="Linux version 6.1.0-rpi7"
            ))),
            __exit__=MagicMock(return_value=False),
        )
        assert _is_wsl() is False

    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_fallback_on_missing(self, mock_open):
        assert _is_wsl() is False


class TestGetHostPhysicalMemory:
    @patch("subprocess.run")
    def test_returns_bytes(self, mock_run):
        import subprocess
        mock_run.return_value = MagicMock(returncode=0, stdout="34359738368\n")
        result = _get_host_physical_memory()
        assert result == 34359738368

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_returns_none_on_failure(self, mock_run):
        assert _get_host_physical_memory() is None


class TestRamSecondary:
    def test_normal(self):
        mem = {"total": "4.0 GB", "used": "2.0 GB", "note": None}
        assert _ram_secondary(mem) == "2.0 GB of 4.0 GB used"

    def test_wsl_with_host_ram(self):
        mem = {"total": "32.0 GB", "used": "8.0 GB", "note": "WSL allocated: 15.5 GB"}
        assert _ram_secondary(mem) == "8.0 GB of 32.0 GB used (WSL allocated: 15.5 GB)"

    def test_wsl_no_host_ram(self):
        mem = {"total": "15.5 GB", "used": "8.0 GB", "note": "WSL allocated"}
        assert _ram_secondary(mem) == "8.0 GB of 15.5 GB used (WSL allocated)"


class TestGetMemoryInfo:
    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_fallback_on_missing_proc(self, mock_open):
        result = _get_memory_info()
        assert result["total"] == "N/A"
        assert result["used"] == "N/A"
        assert result["note"] is None


class TestGetStorageInfo:
    @patch("os.statvfs")
    def test_returns_storage(self, mock_statvfs):
        mock_statvfs.return_value = MagicMock(
            f_frsize=4096, f_blocks=2621440, f_bfree=1310720
        )
        result = _get_storage_info()
        assert "GB" in result["total"] or "MB" in result["total"]

    @patch("os.statvfs", side_effect=OSError)
    def test_fallback_on_error(self, mock_statvfs):
        result = _get_storage_info()
        assert result["total"] == "N/A"


class TestGetOsInfo:
    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_fallback_to_platform(self, mock_open):
        result = _get_os_info()
        assert result["name"] != "Unknown"
        assert result["pretty_name"] is not None
        assert result["distro"] is None


class TestGetDeviceModel:
    @patch("builtins.open", side_effect=FileNotFoundError)
    @patch("platform.machine", return_value="x86_64")
    def test_fallback_to_platform(self, mock_machine, mock_open):
        result = _get_device_model()
        assert result == "x86_64"


class TestGetTemperature:
    @patch("blueprints.system_info.psutil")
    def test_psutil_cpu_thermal(self, mock_psutil):
        mock_psutil.sensors_temperatures.return_value = {
            "cpu_thermal": [MagicMock(current=55.0)],
        }
        assert _get_temperature() == "55 °C"

    @patch("blueprints.system_info.psutil")
    def test_psutil_coretemp(self, mock_psutil):
        mock_psutil.sensors_temperatures.return_value = {
            "coretemp": [MagicMock(current=62.0)],
        }
        assert _get_temperature() == "62 °C"

    @patch("blueprints.system_info.psutil", new=None)
    @patch("subprocess.run", side_effect=FileNotFoundError)
    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_returns_none_when_unavailable(self, mock_open, mock_run):
        assert _get_temperature() is None

    @patch("blueprints.system_info.psutil")
    def test_psutil_empty_falls_to_sysfs(self, mock_psutil):
        mock_psutil.sensors_temperatures.return_value = {}
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with patch("builtins.open") as mock_open:
                mock_open.return_value = MagicMock(
                    __enter__=MagicMock(return_value=MagicMock(
                        read=MagicMock(return_value="45000")
                    )),
                    __exit__=MagicMock(return_value=False),
                )
                assert _get_temperature() == "45 °C"


class TestGetUptime:
    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_fallback_on_missing(self, mock_open):
        assert _get_uptime() == "N/A"

    @patch("builtins.open")
    def test_parses_uptime(self, mock_open):
        mock_open.return_value.__enter__ = MagicMock(
            return_value=MagicMock(read=MagicMock(return_value="90061.23 180000.00"))
        )
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        result = _get_uptime()
        assert "1d" in result
        assert "h" in result


class TestGetLastBoot:
    @patch("builtins.open", side_effect=FileNotFoundError)
    def test_fallback_on_missing(self, mock_open):
        assert _get_last_boot() == "N/A"


class TestGetLocalIp:
    @patch("socket.socket")
    def test_returns_ip(self, mock_socket_cls):
        mock_sock = MagicMock()
        mock_socket_cls.return_value = mock_sock
        mock_sock.getsockname.return_value = ("192.168.1.100", 0)
        assert _get_local_ip() == "192.168.1.100"

    @patch("socket.socket", side_effect=OSError)
    def test_fallback_on_error(self, mock_socket_cls):
        assert _get_local_ip() == "N/A"


class TestGetHostname:
    @patch("socket.gethostname", return_value="inkypi")
    def test_returns_hostname(self, mock_hostname):
        assert _get_hostname() == "inkypi"


class TestParseEpdCode:
    def test_simple_model(self):
        assert _parse_epd_code("epd7in3e") == "Waveshare 7.3inch e-Paper"

    def test_decimal_model(self):
        assert _parse_epd_code("epd5in83") == "Waveshare 5.83inch e-Paper"

    def test_version_suffix(self):
        assert _parse_epd_code("epd5in83_v2") == "Waveshare 5.83inch e-Paper V2"

    def test_hd_suffix(self):
        assert _parse_epd_code("epd7in5b_hd") == "Waveshare 7.5inch e-Paper HD"

    def test_large_model(self):
        assert _parse_epd_code("epd13in3k") == "Waveshare 13.3inch e-Paper"

    def test_invalid_code(self):
        assert _parse_epd_code("not_an_epd") is None


class TestResolveDisplayName:
    def test_mock(self):
        assert _resolve_display_name("mock") == "Mock Display"

    def test_inky(self):
        assert _resolve_display_name("inky") == "Inky e-Paper"

    def test_waveshare_parsed(self):
        result = _resolve_display_name("epd7in3e")
        assert "Waveshare 7.3inch e-Paper" in result
        assert "epd7in3e" in result

    def test_waveshare_unparseable(self):
        result = _resolve_display_name("epd_custom_in_format")
        assert "Waveshare e-Paper" in result

    def test_unknown_type(self):
        assert _resolve_display_name("something_else") == "something_else"

    def test_empty(self):
        assert _resolve_display_name("") == "Unknown"

    def test_none(self):
        assert _resolve_display_name(None) == "Unknown"


class TestGetDisplayInfo:
    def test_mock_display(self):
        mock_dm = MagicMock()
        mock_dm.device_config.get_config.return_value = "mock"
        mock_dm.device_config.get_resolution.return_value = (800, 480)
        result = _get_display_info(mock_dm)
        assert result["name"] == "Mock Display"
        assert result["type"] == "mock"
        assert result["resolution"] == "800 × 480"

    def test_inky_display(self):
        mock_dm = MagicMock()
        mock_dm.device_config.get_config.return_value = "inky"
        mock_dm.device_config.get_resolution.return_value = (400, 300)
        result = _get_display_info(mock_dm)
        assert result["name"] == "Inky e-Paper"
        assert result["type"] == "inky"
        assert result["resolution"] == "400 × 300"

    def test_waveshare_display(self):
        mock_dm = MagicMock()
        mock_dm.device_config.get_config.return_value = "epd7in3e"
        mock_dm.device_config.get_resolution.return_value = (800, 480)
        result = _get_display_info(mock_dm)
        assert "Waveshare 7.3inch e-Paper" in result["name"]
        assert result["type"] == "epd7in3e"
        assert result["resolution"] == "800 × 480"

    def test_resolution_unavailable(self):
        mock_dm = MagicMock()
        mock_dm.device_config.get_config.return_value = "mock"
        mock_dm.device_config.get_resolution.side_effect = KeyError
        result = _get_display_info(mock_dm)
        assert result["resolution"] is None


class TestGetKernelInfo:
    @patch("platform.release", return_value="6.1.0-rpi7-rpi-v8")
    def test_returns_kernel(self, mock_release):
        assert _get_kernel_info() == "6.1.0-rpi7-rpi-v8"


class TestGetArchitecture:
    @patch("platform.machine", return_value="aarch64")
    def test_returns_arch(self, mock_machine):
        assert _get_architecture() == "aarch64"

    @patch("platform.machine", return_value="")
    def test_fallback_on_empty(self, mock_machine):
        assert _get_architecture() == "Unknown"


class TestGetDeviceName:
    def test_returns_config_name(self):
        mock_config = MagicMock()
        mock_config.get_config.return_value = "My InkyPi"
        assert _get_device_name(mock_config) == "My InkyPi"

    def test_returns_default(self):
        mock_config = MagicMock()
        mock_config.get_config.return_value = "InkyPi"
        assert _get_device_name(mock_config) == "InkyPi"


class TestCollectSystemInfo:
    @patch("blueprints.system_info._get_temperature", return_value=None)
    @patch("blueprints.system_info._get_local_ip", return_value="192.168.1.1")
    @patch("blueprints.system_info._get_last_boot", return_value="2025-01-01 10:00")
    @patch("blueprints.system_info._get_uptime", return_value="5d 3h 20m")
    @patch("blueprints.system_info._get_device_model", return_value="Raspberry Pi 4")
    @patch("blueprints.system_info._get_os_info", return_value={"name": "Debian GNU/Linux", "version": "11", "distro": "debian", "pretty_name": "Debian GNU/Linux 11 (bullseye)"})
    @patch("blueprints.system_info._get_storage_info", return_value={"total": "32.0 GB", "used": "10.0 GB"})
    @patch("blueprints.system_info._get_memory_info", return_value={"total": "4.0 GB", "used": "2.0 GB", "installed": None, "note": None})
    @patch("blueprints.system_info._get_cpu_info", return_value={"model": "ARM Cortex-A72", "freq": "1.5 GHz", "cur_freq": "1.2 GHz", "max_freq": "1.5 GHz", "cores": 4})
    @patch("blueprints.system_info._get_kernel_info", return_value="6.1.0-rpi7")
    @patch("blueprints.system_info._get_hostname", return_value="inkypi")
    @patch("blueprints.system_info._get_device_name", return_value="My InkyPi")
    @patch("blueprints.system_info._get_architecture", return_value="aarch64")
    def test_returns_cards_and_specs(self, *mocks):
        mock_dm = MagicMock()
        mock_dm.device_config.get_config.return_value = "mock"
        mock_dm.device_config.get_resolution.return_value = (800, 480)

        cards, device_specs, system_specs = _collect_system_info(mock_dm)

        # Verify cards – Display-centric order, temperature always present
        card_labels = [c["label"] for c in cards]
        assert card_labels[0] == "Display"
        assert "Installed RAM" in card_labels
        assert "CPU" in card_labels
        assert "Temperature" in card_labels
        assert "Uptime" in card_labels
        assert "Local IP" in card_labels
        assert "Storage" not in card_labels
        assert "OS" not in card_labels
        assert len(cards) == 6

        # When temperature is None, card shows "N/A"
        temp_card = next(c for c in cards if c["label"] == "Temperature")
        assert temp_card["value"] == "N/A"

        # Verify device specs
        dev_labels = [s["label"] for s in device_specs]
        assert "Device name" in dev_labels
        assert "Network name" in dev_labels
        assert "Model" not in dev_labels
        assert "Architecture" in dev_labels
        assert "CPU" in dev_labels
        assert "CPU cores" in dev_labels
        assert "Current frequency" in dev_labels
        assert "Max frequency" in dev_labels
        assert "Installed RAM" in dev_labels
        assert "Usable RAM" in dev_labels
        assert "Storage" in dev_labels
        assert "Storage used" in dev_labels
        # device_specs count varies based on installed RAM availability

        # Verify system specs
        sys_labels = [s["label"] for s in system_specs]
        assert "OS name" in sys_labels
        assert "OS version" in sys_labels
        assert "Distribution" in sys_labels
        assert "Kernel" in sys_labels
        assert len(system_specs) == 4

    @patch("blueprints.system_info._get_temperature", return_value="55 °C")
    @patch("blueprints.system_info._get_local_ip", return_value="192.168.1.1")
    @patch("blueprints.system_info._get_last_boot", return_value="2025-01-01 10:00")
    @patch("blueprints.system_info._get_uptime", return_value="5d 3h 20m")
    @patch("blueprints.system_info._get_device_model", return_value="Raspberry Pi 4")
    @patch("blueprints.system_info._get_os_info", return_value={"name": "Debian GNU/Linux", "version": "11", "distro": "debian", "pretty_name": "Debian GNU/Linux 11 (bullseye)"})
    @patch("blueprints.system_info._get_storage_info", return_value={"total": "32.0 GB", "used": "10.0 GB"})
    @patch("blueprints.system_info._get_memory_info", return_value={"total": "4.0 GB", "used": "2.0 GB", "installed": None, "allocated": None, "note": None})
    @patch("blueprints.system_info._get_cpu_info", return_value={"model": "ARM Cortex-A72", "freq": "1.5 GHz", "cur_freq": "1.2 GHz", "max_freq": "1.5 GHz", "cores": 4})
    @patch("blueprints.system_info._get_kernel_info", return_value="6.1.0-rpi7")
    @patch("blueprints.system_info._get_hostname", return_value="inkypi")
    @patch("blueprints.system_info._get_device_name", return_value="My InkyPi")
    @patch("blueprints.system_info._get_architecture", return_value="aarch64")
    def test_temperature_card_shows_value_when_available(self, *mocks):
        mock_dm = MagicMock()
        mock_dm.device_config.get_config.return_value = "mock"
        mock_dm.device_config.get_resolution.return_value = (800, 480)

        cards, _, _ = _collect_system_info(mock_dm)
        temp_card = next(c for c in cards if c["label"] == "Temperature")
        assert temp_card["value"] == "55 °C"
        assert len(cards) == 6


class TestFormatTimeAgo:
    def test_just_now(self):
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        assert _format_time_ago(now) == "just now"

    def test_minutes_ago(self):
        from datetime import datetime, timezone, timedelta
        dt = datetime.now(timezone.utc) - timedelta(minutes=5)
        assert _format_time_ago(dt) == "5 min ago"

    def test_hours_ago(self):
        from datetime import datetime, timezone, timedelta
        dt = datetime.now(timezone.utc) - timedelta(hours=3)
        assert _format_time_ago(dt) == "3h ago"

    def test_days_ago(self):
        from datetime import datetime, timezone, timedelta
        dt = datetime.now(timezone.utc) - timedelta(days=2)
        assert _format_time_ago(dt) == "2d ago"

    def test_naive_datetime(self):
        from datetime import datetime, timezone, timedelta
        dt = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=10)
        assert _format_time_ago(dt) == "10 min ago"


class TestCollectOverview:
    def test_returns_all_items(self):
        from flask import Flask
        app = Flask(__name__)

        mock_refresh_info = MagicMock()
        mock_refresh_info.plugin_id = "clock"
        mock_refresh_info.refresh_time = "2026-03-27T10:00:00+00:00"
        from datetime import datetime, timezone
        mock_refresh_info.get_refresh_datetime.return_value = datetime(
            2026, 3, 27, 10, 0, tzinfo=timezone.utc
        )

        mock_config = MagicMock()
        mock_config.get_refresh_info.return_value = mock_refresh_info
        mock_config.get_plugin.return_value = {"display_name": "Clock", "id": "clock"}
        mock_config.get_plugins.return_value = [{"id": "clock"}, {"id": "weather"}]

        mock_playlist = MagicMock()
        mock_playlist.name = "Default"
        mock_playlist.start_time = "00:00"
        mock_playlist.end_time = "24:00"
        mock_config.get_playlist_manager.return_value.determine_active_playlist.return_value = mock_playlist

        app.config["DEVICE_CONFIG"] = mock_config

        with app.app_context():
            line1, line2 = _collect_overview()

        # Line 1: Active playlist
        l1_labels = [i["label"] for i in line1]
        assert "Active playlist" in l1_labels
        playlist = next(i for i in line1 if i["label"] == "Active playlist")
        assert playlist["value"] == "Default (00:00\u201324:00)"

        # Line 2: Active plugin, Last refresh, Installed plugins
        l2_labels = [i["label"] for i in line2]
        assert "Active plugin" in l2_labels
        assert "Last refresh" in l2_labels
        assert "Installed plugins" in l2_labels

        plugin = next(i for i in line2 if i["label"] == "Active plugin")
        assert plugin["value"] == "Clock"

        plugins_count = next(i for i in line2 if i["label"] == "Installed plugins")
        assert plugins_count["value"] == "2"

    def test_empty_when_no_config(self):
        from flask import Flask
        app = Flask(__name__)

        with app.app_context():
            line1, line2 = _collect_overview()

        assert line1 == []
        assert line2 == []

    def test_skips_missing_fields(self):
        from flask import Flask
        app = Flask(__name__)

        mock_refresh_info = MagicMock()
        mock_refresh_info.plugin_id = None
        mock_refresh_info.refresh_time = None

        mock_config = MagicMock()
        mock_config.get_refresh_info.return_value = mock_refresh_info
        mock_config.get_plugins.return_value = []
        mock_config.get_playlist_manager.return_value.determine_active_playlist.return_value = None

        app.config["DEVICE_CONFIG"] = mock_config

        with app.app_context():
            line1, line2 = _collect_overview()

        # Playlist always present with fallback
        playlist = next(i for i in line1 if i["label"] == "Active playlist")
        assert playlist["value"] == "None (no active schedule now)"

        # Active plugin and Last refresh always present with "None"
        l2_labels = [i["label"] for i in line2]
        assert "Active plugin" in l2_labels
        assert "Last refresh" in l2_labels
        assert "Installed plugins" not in l2_labels

        plugin = next(i for i in line2 if i["label"] == "Active plugin")
        assert plugin["value"] == "None"

        refresh = next(i for i in line2 if i["label"] == "Last refresh")
        assert refresh["value"] == "None"


class TestCollectPluginInfo:
    def test_reads_real_plugins_dir(self):
        result = _collect_plugin_info()
        assert result["total"] > 0
        assert result["total"] == result["builtin_count"] + result["third_party_count"]
        assert isinstance(result["builtin"], list)
        assert isinstance(result["third_party"], list)
        for p in result["builtin"] + result["third_party"]:
            assert "id" in p
            assert "name" in p

    def test_empty_when_dir_missing(self, tmp_path):
        # Point the plugins directory to a non-existent path and call the real
        # implementation to verify the fallback behavior.
        fake_dir = tmp_path / "nonexistent"
        with patch("blueprints.system_info._PLUGINS_DIR", fake_dir):
            result = _collect_plugin_info()

        assert result["total"] == 0
        assert result["builtin_count"] == 0
        assert result["third_party_count"] == 0
        assert result["builtin"] == []
        assert result["third_party"] == []

    def test_third_party_detection(self, tmp_path):
        import json
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        # Builtin plugin (no repository)
        builtin = plugins_dir / "my_builtin"
        builtin.mkdir()
        (builtin / "plugin-info.json").write_text(
            json.dumps({"display_name": "My Builtin", "id": "my_builtin"})
        )

        # Third-party plugin (has repository)
        thirdparty = plugins_dir / "my_thirdparty"
        thirdparty.mkdir()
        (thirdparty / "plugin-info.json").write_text(
            json.dumps({
                "display_name": "My Third Party",
                "id": "my_thirdparty",
                "repository": "https://github.com/example/plugin",
            })
        )

        with patch(
            "blueprints.system_info._PLUGINS_DIR",
            plugins_dir,
        ):
            result = _collect_plugin_info()

        assert result["total"] == 2
        assert result["builtin_count"] == 1
        assert result["third_party_count"] == 1
        assert result["third_party"][0]["name"] == "My Third Party"
        assert result["third_party"][0]["repository"] == "https://github.com/example/plugin"
        assert result["builtin"][0]["name"] == "My Builtin"

    def test_skips_dir_without_info_file(self, tmp_path):
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        no_info = plugins_dir / "some_plugin"
        no_info.mkdir()

        with patch(
            "blueprints.system_info._PLUGINS_DIR",
            plugins_dir,
        ):
            result = _collect_plugin_info()

        assert result["total"] == 0
        assert result["builtin"] == []
        assert result["third_party"] == []

    def test_skips_base_plugin_and_pycache(self, tmp_path):
        import json
        plugins_dir = tmp_path / "plugins"
        plugins_dir.mkdir()

        (plugins_dir / "base_plugin").mkdir()
        (plugins_dir / "__pycache__").mkdir()
        real = plugins_dir / "real_plugin"
        real.mkdir()
        (real / "plugin-info.json").write_text(
            json.dumps({"display_name": "Real Plugin", "id": "real_plugin"})
        )

        with patch(
            "blueprints.system_info._PLUGINS_DIR",
            plugins_dir,
        ):
            result = _collect_plugin_info()

        assert result["total"] == 1
        assert result["builtin"][0]["id"] == "real_plugin"
        assert result["builtin"][0]["name"] == "Real Plugin"
