import fnmatch
import json
import logging
import os
import platform
import re
import socket
from urllib.parse import urlparse
from datetime import datetime, timezone
from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template

try:
    import psutil
except ImportError:
    psutil = None

logger = logging.getLogger(__name__)

system_info_bp = Blueprint("system_info", __name__)

_PLUGINS_DIR = Path(__file__).resolve().parent.parent / "plugins"


def _get_cpu_freq():
    """Return CPU frequency as a formatted string (e.g. '2.5 GHz').

    Priority: psutil current -> psutil max -> /proc/cpuinfo cpu MHz ->
    sysfs scaling_cur_freq -> sysfs cpuinfo_max_freq -> None.
    """
    # 1. psutil (preferred - works on ARM and x86)
    if psutil is not None:
        try:
            freq = psutil.cpu_freq()
            if freq is not None:
                mhz = freq.current if freq.current and freq.current > 0 else freq.max
                if mhz and mhz > 0:
                    return f"{round(mhz / 1000, 1)} GHz"
        except Exception:
            pass

    # 2. /proc/cpuinfo "cpu MHz" line
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.lower().startswith("cpu mhz"):
                    mhz = float(line.split(":")[1].strip())
                    if mhz > 0:
                        return f"{round(mhz / 1000, 1)} GHz"
    except (FileNotFoundError, PermissionError, ValueError):
        pass

    # 3. sysfs frequency files (kHz)
    freq_paths = [
        "/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq",
        "/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq",
    ]
    for path in freq_paths:
        try:
            with open(path) as f:
                freq_khz = int(f.read().strip())
                if freq_khz > 0:
                    return f"{round(freq_khz / 1_000_000, 1)} GHz"
        except (FileNotFoundError, PermissionError, ValueError):
            continue

    return None


def _read_sysfs_freq(path):
    """Read a sysfs frequency file (kHz) and return formatted GHz string or None."""
    try:
        with open(path) as f:
            freq_khz = int(f.read().strip())
            if freq_khz > 0:
                return f"{round(freq_khz / 1_000_000, 1)} GHz"
    except (FileNotFoundError, PermissionError, ValueError):
        pass
    return None


def _get_cpu_cur_freq():
    """Return current CPU frequency as a formatted string or None.

    Priority: sysfs scaling_cur_freq -> psutil current -> /proc/cpuinfo cpu MHz.
    """
    # 1. sysfs (Linux / Raspberry Pi)
    val = _read_sysfs_freq("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq")
    if val:
        return val

    # 2. psutil current frequency
    if psutil is not None:
        try:
            freq = psutil.cpu_freq()
            if freq is not None and freq.current and freq.current > 0:
                return f"{round(freq.current / 1000, 1)} GHz"
        except Exception:
            pass

    # 3. /proc/cpuinfo "cpu MHz"
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.lower().startswith("cpu mhz"):
                    mhz = float(line.split(":")[1].strip())
                    if mhz > 0:
                        return f"{round(mhz / 1000, 1)} GHz"
    except (FileNotFoundError, PermissionError, ValueError):
        pass

    return None


def _get_cpu_max_freq():
    """Return max CPU frequency as a formatted string or None.

    Priority: sysfs scaling_max_freq -> psutil max -> lscpu CPU max MHz.
    """
    # 1. sysfs (Linux / Raspberry Pi)
    val = _read_sysfs_freq("/sys/devices/system/cpu/cpu0/cpufreq/scaling_max_freq")
    if val:
        return val

    # 2. psutil max frequency
    if psutil is not None:
        try:
            freq = psutil.cpu_freq()
            if freq is not None and freq.max and freq.max > 0:
                return f"{round(freq.max / 1000, 1)} GHz"
        except Exception:
            pass

    # 3. lscpu (available on most Linux distros and WSL)
    import subprocess
    try:
        result = subprocess.run(
            ["lscpu"], capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            max_mhz = None
            cur_mhz = None
            for line in result.stdout.splitlines():
                lower = line.lower()
                if "cpu max mhz" in lower:
                    try:
                        max_mhz = float(line.split(":")[1].strip().replace(",", "."))
                    except ValueError:
                        pass
                elif "cpu mhz" in lower and "max" not in lower and "min" not in lower:
                    try:
                        cur_mhz = float(line.split(":")[1].strip().replace(",", "."))
                    except ValueError:
                        pass
            mhz = max_mhz or cur_mhz
            if mhz and mhz > 0:
                return f"{round(mhz / 1000, 1)} GHz"
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, OSError):
        pass

    return None


# -- ARM CPU part ID to model name mapping --
_ARM_CPU_PART_MAP = {
    "0xb76": "ARM1176JZF-S",
    "0xc07": "ARM Cortex-A7",
    "0xc08": "ARM Cortex-A8",
    "0xc09": "ARM Cortex-A9",
    "0xc0f": "ARM Cortex-A15",
    "0xd01": "ARM Cortex-A32",
    "0xd03": "ARM Cortex-A53",
    "0xd04": "ARM Cortex-A35",
    "0xd05": "ARM Cortex-A55",
    "0xd07": "ARM Cortex-A57",
    "0xd08": "ARM Cortex-A72",
    "0xd09": "ARM Cortex-A73",
    "0xd0a": "ARM Cortex-A75",
    "0xd0b": "ARM Cortex-A76",
    "0xd0c": "ARM Neoverse N1",
    "0xd0d": "ARM Cortex-A77",
    "0xd41": "ARM Cortex-A78",
    "0xd44": "ARM Cortex-X1",
    "0xd46": "ARM Cortex-A510",
    "0xd47": "ARM Cortex-A710",
    "0xd48": "ARM Cortex-X2",
}


def _get_arm_cpu_model():
    """Detect ARM CPU model from /proc/cpuinfo CPU part field.

    Returns a friendly name like 'ARM Cortex-A53' or None.
    """
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("CPU part"):
                    part = line.split(":")[1].strip().lower()
                    return _ARM_CPU_PART_MAP.get(part)
    except (FileNotFoundError, PermissionError):
        pass
    return None


def _get_cpu_info():
    """Return CPU model name, frequency strings, and core count.

    Detection order for model name:
    1. ARM CPU part mapping (Raspberry Pi / ARM SoCs)
    2. /proc/cpuinfo ``model name`` field (x86, modern ARM)
    3. /proc/cpuinfo ``Hardware`` field (older Raspberry Pi kernels)
    4. /proc/device-tree/model (Raspberry Pi device-tree)
    5. platform.processor()
    6. ``CPU not detected`` (never shows "Unknown")

    Results are cached after the first call.
    """
    if hasattr(_get_cpu_info, "_cache"):
        return _get_cpu_info._cache

    model = None
    hardware = None
    cores = None

    # Try ARM CPU part mapping first (most accurate for Raspberry Pi)
    arm_model = _get_arm_cpu_model()
    if arm_model:
        model = arm_model

    try:
        with open("/proc/cpuinfo") as f:
            core_count = 0
            for line in f:
                if line.startswith("model name") and not model:
                    model = line.split(":")[1].strip()
                if line.startswith("Hardware") and not hardware:
                    hardware = line.split(":")[1].strip()
                if line.startswith("processor"):
                    core_count += 1
            if core_count > 0:
                cores = core_count
    except (FileNotFoundError, PermissionError):
        pass

    if not model or model.lower() == "unknown":
        model = hardware

    if not model or model.lower() == "unknown":
        try:
            with open("/proc/device-tree/model") as f:
                model = f.read().strip().rstrip("\x00")
        except (FileNotFoundError, PermissionError):
            pass

    if not model or model.lower() == "unknown":
        proc = platform.processor()
        if proc:
            model = proc

    if not model or model.lower() == "unknown":
        model = "CPU not detected"

    freq = _get_cpu_freq()
    cur_freq = _get_cpu_cur_freq()
    max_freq = _get_cpu_max_freq()
    # Cross-fallback: if one is unavailable, use the other or the general freq
    if not cur_freq:
        cur_freq = max_freq or freq
    if not max_freq:
        max_freq = cur_freq or freq
    result = {
        "model": model,
        "freq": freq,
        "cur_freq": cur_freq,
        "max_freq": max_freq,
        "cores": cores,
    }
    _get_cpu_info._cache = result
    return result


def _is_wsl():
    """Detect if running inside Windows Subsystem for Linux."""
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except (FileNotFoundError, PermissionError):
        return False


def _get_host_physical_memory():
    """Try to get actual physical RAM from Windows host (WSL2 only).

    Uses PowerShell interop to query the host's total physical memory.
    Returns the value in bytes or None if unavailable.
    """
    import subprocess

    try:
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return int(result.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, OSError):
        pass
    return None


def _get_installed_ram():
    """Return total installed physical RAM via vcgencmd (Raspberry Pi).

    Sums ``vcgencmd get_mem arm`` and ``vcgencmd get_mem gpu`` to obtain the
    full physical memory (including GPU-reserved portion invisible to Linux).
    Returns a formatted string like '512 MB' or None if vcgencmd is unavailable.
    """
    import subprocess

    total_mb = 0
    for region in ("arm", "gpu"):
        try:
            result = subprocess.run(
                ["vcgencmd", "get_mem", region],
                capture_output=True, text=True, timeout=3,
            )
            if result.returncode == 0 and "=" in result.stdout:
                val = result.stdout.split("=")[1].strip()
                # e.g. "448M" or "64M"
                num = int(re.sub(r"[^\d]", "", val))
                total_mb += num
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, OSError):
            return None
    if total_mb > 0:
        if total_mb >= 1024:
            return f"{round(total_mb / 1024, 1)} GB"
        return f"{total_mb} MB"
    return None


def _get_memory_info():
    """Return total and used RAM in human-readable format.

    On WSL, attempts to report the host's physical RAM via PowerShell.
    Falls back to /proc/meminfo MemTotal with an annotation when the
    true installed amount cannot be determined.

    Also attempts to detect installed physical RAM via vcgencmd on
    Raspberry Pi (``installed`` key).
    """
    installed = _get_installed_ram()
    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = parts[1].strip().split()[0]  # value in kB
                    meminfo[key] = int(val)

        total_kb = meminfo.get("MemTotal", 0)
        available_kb = meminfo.get("MemAvailable", 0)
        used_kb = total_kb - available_kb

        allocated = _format_bytes(total_kb * 1024)
        used = _format_bytes(used_kb * 1024)

        if _is_wsl():
            host_mem = _get_host_physical_memory()
            if host_mem:
                return {
                    "total": _format_bytes(host_mem),
                    "used": used,
                    "installed": installed,
                    "allocated": allocated,
                    "note": f"WSL allocated: {allocated}",
                }
            return {
                "total": allocated,
                "used": used,
                "installed": installed,
                "allocated": allocated,
                "note": "WSL allocated",
            }

        return {"total": allocated, "used": used, "installed": installed, "allocated": None, "note": None}
    except (FileNotFoundError, PermissionError):
        return {"total": "N/A", "used": "N/A", "installed": installed, "allocated": None, "note": None}


def _get_storage_info():
    """Return total and used disk space for the root filesystem."""
    try:
        stat = os.statvfs("/")
        total = stat.f_frsize * stat.f_blocks
        used = stat.f_frsize * (stat.f_blocks - stat.f_bfree)
        return {
            "total": _format_bytes(total),
            "used": _format_bytes(used),
        }
    except OSError:
        return {"total": "N/A", "used": "N/A"}


def _get_os_info():
    """Return OS name, version, distribution ID, and pretty name."""
    name = "Unknown"
    version = None
    distro_id = None
    pretty_name = None

    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME="):
                    pretty_name = line.split("=", 1)[1].strip().strip('"')
                elif line.startswith("VERSION="):
                    version = line.split("=", 1)[1].strip().strip('"')
                elif line.startswith("NAME=") and not line.startswith("NAME=\"\n"):
                    name = line.split("=", 1)[1].strip().strip('"')
                elif line.startswith("ID="):
                    distro_id = line.split("=", 1)[1].strip().strip('"')
    except (FileNotFoundError, PermissionError):
        name = f"{platform.system()} {platform.release()}"

    return {
        "name": name,
        "version": version,
        "distro": distro_id,
        "pretty_name": pretty_name or name,
    }


def _get_architecture():
    """Return the system architecture (e.g. x86_64, aarch64)."""
    return platform.machine() or "Unknown"


def _get_device_model():
    """Return the device model (e.g. Raspberry Pi 4 Model B)."""
    try:
        with open("/proc/device-tree/model") as f:
            return f.read().strip().rstrip("\x00")
    except (FileNotFoundError, PermissionError):
        return platform.machine() or "Unknown"


def _get_temperature():
    """Return CPU temperature as a formatted string.

    Priority: psutil sensors -> vcgencmd -> thermal_zone0 sysfs -> None.
    """
    # 1. psutil (cross-platform)
    if psutil is not None:
        try:
            temps = psutil.sensors_temperatures()
            for name in ("cpu_thermal", "cpu-thermal", "coretemp", "k10temp"):
                if name in temps and temps[name]:
                    current = temps[name][0].current
                    if current and current > 0:
                        return f"{current:.0f} °C"
            # Fallback: first available sensor
            for entries in temps.values():
                if entries and entries[0].current > 0:
                    return f"{entries[0].current:.0f} °C"
        except Exception:
            pass

    # 2. vcgencmd (Raspberry Pi)
    import subprocess
    try:
        result = subprocess.run(
            ["vcgencmd", "measure_temp"],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0 and "temp=" in result.stdout:
            temp_str = result.stdout.split("=")[1].split("'")[0]
            return f"{float(temp_str):.0f} °C"
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError, OSError):
        pass

    # 3. sysfs thermal zone
    try:
        with open("/sys/class/thermal/thermal_zone0/temp") as f:
            millideg = int(f.read().strip())
            if millideg > 0:
                return f"{millideg / 1000:.0f} °C"
    except (FileNotFoundError, PermissionError, ValueError):
        pass

    return None

def _get_uptime():
    """Return system uptime as a human-readable string."""
    try:
        with open("/proc/uptime") as f:
            seconds = int(float(f.read().split()[0]))
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)
        parts = []
        if days:
            parts.append(f"{days}d")
        if hours:
            parts.append(f"{hours}h")
        parts.append(f"{minutes}m")
        return " ".join(parts)
    except (FileNotFoundError, PermissionError):
        return "N/A"


def _get_last_boot():
    """Return last boot time as a formatted string."""
    try:
        with open("/proc/uptime") as f:
            uptime_seconds = float(f.read().split()[0])
        import time
        boot_timestamp = time.time() - uptime_seconds
        from datetime import datetime
        boot_dt = datetime.fromtimestamp(boot_timestamp)
        return boot_dt.strftime("%Y-%m-%d %H:%M")
    except (FileNotFoundError, PermissionError):
        return "N/A"


def _get_local_ip():
    """Return the local IP address."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.settimeout(2)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            return ip
        finally:
            try:
                s.close()
            except Exception:
                pass
    except (OSError, socket.error):
        return "N/A"


def _get_hostname():
    """Return the system hostname."""
    return socket.gethostname()


def _get_display_info(display_manager):
    """Return display information using the same detection path as SystemStatus.

    Mirrors the ``_get_display_value`` / ``_parse_epd_code`` logic already used
    by the SystemStatus plugin so that the System Info page shows the identical
    resolved display name.  No manual per-model catalog is maintained - the EPD
    code is parsed dynamically from the ``display_type`` config value.
    """
    device_config = display_manager.device_config
    display_type = device_config.get_config("display_type", default="unknown")

    name = _resolve_display_name(display_type)

    # Resolution from the same config source used by display rendering
    resolution = None
    try:
        w, h = device_config.get_resolution()
        resolution = f"{w} × {h}"
    except (TypeError, ValueError, KeyError):
        pass

    return {"name": name, "type": display_type, "resolution": resolution}


# -- Display name resolution (mirrors SystemStatus._get_display_value) --

_DISPLAY_NAME_MAP = {
    "inky": "Inky e-Paper",
    "mock": "Mock Display",
}

_EPD_PATTERN = re.compile(
    r"^epd(\d+)in(\d+)([a-z]*)(?:_(v\d+|hd))?(?:([a-z]*)(?:_(v\d+|hd))?)?$",
    re.IGNORECASE,
)


def _parse_epd_code(code):
    """Parse a Waveshare EPD code into a friendly name.

    Examples::

        epd7in3e    -> Waveshare 7.3inch e-Paper
        epd5in83_v2 -> Waveshare 5.83inch e-Paper V2
        epd7in5b_hd -> Waveshare 7.5inch e-Paper HD
        epd13in3k   -> Waveshare 13.3inch e-Paper
    """
    m = _EPD_PATTERN.match(code)
    if not m:
        return None
    inches = m.group(1)
    decimal = m.group(2)
    size = f"{inches}.{decimal}"

    suffixes = []
    for g in (m.group(4), m.group(5), m.group(6)):
        if g:
            suffixes.append(g.upper())

    suffix_str = f" {' '.join(suffixes)}" if suffixes else ""
    return f"Waveshare {size}inch e-Paper{suffix_str}"


def _resolve_display_name(display_type):
    """Return a human-readable display name from the config display_type value.

    Uses the same strategy as SystemStatus._get_display_value:
    1. Check the static name map (inky, mock)
    2. Parse Waveshare EPD codes dynamically
    3. Fall back to the raw display_type string
    """
    if not display_type:
        return "Unknown"

    normalized = str(display_type).strip().lower()
    if not normalized:
        return "Unknown"

    friendly = _DISPLAY_NAME_MAP.get(normalized)
    if friendly:
        return friendly

    if fnmatch.fnmatch(normalized, "epd*in*"):
        parsed = _parse_epd_code(normalized)
        if parsed:
            return f"{parsed} ({display_type})"
        return f"Waveshare e-Paper ({display_type})"

    return display_type


def _get_kernel_info():
    """Return kernel version string."""
    return platform.release()


def _get_device_name(device_config):
    """Return the configured device name from InkyPi config."""
    return device_config.get_config("name", default="InkyPi")


def _format_bytes(num_bytes):
    """Format bytes into a human-readable string (e.g. 3.7 GB)."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"


def _ram_secondary(mem):
    """Build secondary text for the RAM card, annotating WSL when applicable."""
    usage = f"{mem['used']} of {mem['total']} used"
    note = mem.get("note")
    if note:
        return f"{usage} ({note})"
    return usage


def _collect_system_info(display_manager):
    """Collect all system information split into highlight cards and specification sections."""
    cpu = _get_cpu_info()
    mem = _get_memory_info()
    storage = _get_storage_info()
    os_info = _get_os_info()
    display = _get_display_info(display_manager)
    local_ip = _get_local_ip()
    uptime = _get_uptime()
    temperature = _get_temperature()
    device_config = display_manager.device_config

    cards = [
        {
            "icon": "display",
            "label": "Display",
            "value": display["name"],
            "secondary": display["resolution"],
        },
        {
            "icon": "memory",
            "label": "Installed RAM",
            "value": mem["installed"] or mem["total"],
            "secondary": _ram_secondary(mem),
        },
        {
            "icon": "cpu",
            "label": "CPU",
            "value": cpu["model"],
            "secondary": cpu["max_freq"] or cpu["freq"],
        },
        {
            "icon": "temperature",
            "label": "Temperature",
            "value": temperature or "N/A",
        },
        {
            "icon": "uptime",
            "label": "Uptime",
            "value": uptime,
        },
        {
            "icon": "network",
            "label": "Local IP",
            "value": local_ip,
        },
    ]

    device_specs = [
        {"label": "Device name", "value": _get_device_name(device_config)},
        {"label": "Network name", "value": _get_hostname()},
        {"label": "Architecture", "value": _get_architecture()},
        {"label": "CPU", "value": cpu["model"]},
        {"label": "CPU cores", "value": str(cpu["cores"]) if cpu["cores"] else "N/A"},
        {"label": "Current frequency", "value": cpu["cur_freq"] or "N/A"},
        {"label": "Max frequency", "value": cpu["max_freq"] or "N/A"},
    ]

    wsl_allocated = mem.get("allocated")
    if wsl_allocated:
        # WSL: total may be host physical RAM, allocated is the WSL-visible memory
        if mem["total"] != wsl_allocated:
            device_specs.append({"label": "Installed RAM", "value": mem["total"]})
        device_specs.append({"label": "Usable RAM", "value": wsl_allocated})
        device_specs.append({"label": "RAM used", "value": f"{mem['used']} of {wsl_allocated} used"})
    else:
        # Non-WSL: show vcgencmd physical RAM (RPi) if available, then system totals
        if mem.get("installed"):
            device_specs.append({"label": "Installed RAM", "value": mem["installed"]})
            device_specs.append({"label": "Usable RAM", "value": mem["total"]})
            device_specs.append({"label": "RAM used", "value": f"{mem['used']} of {mem['total']} used"})
        else:
            # Fallback when physical 'installed' value is unavailable
            device_specs.append({"label": "Installed RAM", "value": mem["total"]})
            device_specs.append({"label": "Usable RAM", "value": f"{mem['used']} of {mem['total']} used"})

    device_specs.extend([
        {"label": "Storage", "value": storage["total"]},
        {"label": "Storage used", "value": f"{storage['used']} of {storage['total']} used"},
    ])

    system_specs = [
        {"label": "OS name", "value": os_info["name"]},
        {"label": "OS version", "value": os_info["version"] or "N/A"},
        {"label": "Distribution", "value": os_info["distro"] or "N/A"},
        {"label": "Kernel", "value": _get_kernel_info()},
    ]

    return cards, device_specs, system_specs


def _format_time_ago(dt):
    """Return a human-readable 'X ago' string from a datetime."""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    total_seconds = int(delta.total_seconds())
    if total_seconds < 60:
        return "just now"
    minutes = total_seconds // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


def _collect_overview():
    """Collect live system overview data.

    Returns a tuple of two lists (line1, line2), each containing
    dicts with 'label' and 'value' keys.
    line1: Active playlist (shown alone on first row).
    line2: Active plugin, Last refresh, Installed plugins.
    """
    line1 = []
    line2 = []

    device_config = current_app.config.get("DEVICE_CONFIG")

    if device_config:
        # Active playlist (line 1)
        playlist_value = "None (no active schedule now)"
        playlist_manager = device_config.get_playlist_manager()
        if playlist_manager:
            active = playlist_manager.determine_active_playlist(datetime.now())
            if active:
                playlist_value = f"{active.name} ({active.start_time}\u2013{active.end_time})"
        line1.append({"label": "Active playlist", "value": playlist_value})

        # Active plugin (line 2)
        refresh_info = device_config.get_refresh_info()
        plugin_name = "None"
        if refresh_info and refresh_info.plugin_id:
            plugin_name = refresh_info.plugin_id
            plugin_cfg = device_config.get_plugin(refresh_info.plugin_id)
            if plugin_cfg:
                plugin_name = plugin_cfg.get("display_name", plugin_name)
        line2.append({"label": "Active plugin", "value": plugin_name})

        # Last refresh (line 2)
        last_refresh = "None"
        if refresh_info and refresh_info.refresh_time:
            refresh_dt = refresh_info.get_refresh_datetime()
            if refresh_dt:
                last_refresh = _format_time_ago(refresh_dt)
        line2.append({"label": "Last refresh", "value": last_refresh})

        # Installed plugins (line 2)
        plugins = device_config.get_plugins()
        if plugins:
            line2.append({"label": "Installed plugins", "value": str(len(plugins))})

    return line1, line2


def _collect_plugin_info():
    """Collect installed plugin metadata from plugin-info.json files.

    Returns a dict with 'builtin' and 'third_party' lists plus counts.
    Uses the same logic as the CLI ``inkypi plugin list`` command:
    a plugin is third-party when its plugin-info.json has a non-empty
    ``repository`` field, builtin otherwise.
    """
    plugins_dir = _PLUGINS_DIR

    builtin = []
    third_party = []

    if not plugins_dir.is_dir():
        return {
            "builtin": builtin,
            "third_party": third_party,
            "total": 0,
            "builtin_count": 0,
            "third_party_count": 0,
        }

    for entry in sorted(plugins_dir.iterdir()):
        if not entry.is_dir():
            continue
        plugin_id = entry.name
        if plugin_id in ("base_plugin", "__pycache__"):
            continue

        info_file = entry / "plugin-info.json"
        if not info_file.is_file():
            continue

        display_name = plugin_id.replace("_", " ").title()
        repository = ""

        try:
            with open(info_file) as f:
                info = json.load(f)
            display_name = info.get("display_name", display_name)
            repository = info.get("repository", "")
        except (json.JSONDecodeError, OSError):
            pass

        plugin_data = {"id": plugin_id, "name": display_name}

        # If metadata contains a repository the plugin is third-party.
        # Only include the `repository` field when it's a safe http(s)
        # URL with a non-empty netloc; otherwise omit the field but keep
        # the plugin classified as third-party.
        repo = (repository or "").strip()
        if repo:
            try:
                parsed = urlparse(repo)
                scheme = (parsed.scheme or "").lower()
                if scheme in ("http", "https") and parsed.netloc:
                    plugin_data["repository"] = repo
            except Exception:
                pass
            third_party.append(plugin_data)
        else:
            builtin.append(plugin_data)

    builtin.sort(key=lambda p: p["name"].casefold())
    third_party.sort(key=lambda p: p["name"].casefold())

    total = len(builtin) + len(third_party)
    return {
        "builtin": builtin,
        "third_party": third_party,
        "total": total,
        "builtin_count": len(builtin),
        "third_party_count": len(third_party),
    }


@system_info_bp.route("/system-info")
def system_info_page():
    display_manager = current_app.config["DISPLAY_MANAGER"]
    hostname = _get_hostname()
    device_name = _get_device_name(display_manager.device_config)
    cards, device_specs, system_specs = _collect_system_info(display_manager)
    overview_line1, overview_line2 = _collect_overview()
    plugin_info = _collect_plugin_info()
    return render_template(
        "system_info.html",
        hostname=hostname,
        device_name=device_name,
        overview_line1=overview_line1,
        overview_line2=overview_line2,
        cards=cards,
        device_specs=device_specs,
        system_specs=system_specs,
        plugin_info=plugin_info,
    )


@system_info_bp.route("/api/system-info")
def system_info_api():
    display_manager = current_app.config["DISPLAY_MANAGER"]
    hostname = _get_hostname()
    cards, device_specs, system_specs = _collect_system_info(display_manager)
    overview_line1, overview_line2 = _collect_overview()
    plugin_info = _collect_plugin_info()
    return jsonify({
        "hostname": hostname,
        "overview_line1": overview_line1,
        "overview_line2": overview_line2,
        "cards": cards,
        "device_specs": device_specs,
        "system_specs": system_specs,
        "plugin_info": plugin_info,
    })
