"""CPU limit of the InkyPi systemd service (CPUQuota).

The service file installs a conservative CPUQuota=40% (40% of ONE core), suited to
single-core boards such as the Pi Zero. On multi-core boards it makes every render
(including the headless browser used by most plugins) several times slower. This
module reads and changes that limit with `systemctl set-property`, which applies
immediately and persists across reboots (/etc/systemd/system.control/).
"""

import logging
import os
import re
import subprocess

logger = logging.getLogger(__name__)

SERVICE = "inkypi.service"
DEFAULT, AUTO, MANUAL = "default", "auto", "manual"
MODES = (DEFAULT, AUTO, MANUAL)
INSTALL_DEFAULT_PERCENT = 40
MIN_PERCENT = 20
_CONTROL_DROPINS = (f"/etc/systemd/system.control/{SERVICE}.d/50-CPUQuota.conf",
                    f"/run/systemd/system.control/{SERVICE}.d/50-CPUQuota.conf")


def board_model():
    try:
        with open("/proc/device-tree/model", "rb") as f:
            return f.read().decode("utf-8", "replace").strip("\x00 \n")
    except OSError:
        return ""


def cpu_count():
    return os.cpu_count() or 1


def max_percent(cpus=None):
    return 100 * (cpus or cpu_count())


def recommended_percent(model=None, cpus=None):
    """Limit for this board: leaves headroom for the system on small boards."""
    model = (board_model() if model is None else model).lower()
    cpus = cpus or cpu_count()
    if cpus <= 1:
        return INSTALL_DEFAULT_PERCENT          # Pi Zero / Pi 1: keep the system responsive
    if "zero 2" in model:
        return 100                              # 4 slow cores, 512 MB: one core's worth
    if "pi 3" in model:
        return 200
    return min(300, 75 * cpus)                  # Pi 4 / Pi 5 and other quad cores: 3 cores


def target_percent(mode, manual_percent=None, model=None, cpus=None):
    if mode == AUTO:
        return recommended_percent(model, cpus)
    if mode == MANUAL:
        return parse_percent(manual_percent, cpus)
    return None  # installation default


def parse_percent(value, cpus=None):
    """Validated manual percentage, or ValueError."""
    percent = int(str(value).strip().rstrip("%"))
    if not MIN_PERCENT <= percent <= max_percent(cpus):
        raise ValueError(f"CPU limit must be between {MIN_PERCENT}% and {max_percent(cpus)}%")
    return percent


def _systemctl(*args):
    return subprocess.run(["systemctl", *args], capture_output=True, text=True, timeout=15)


def is_available():
    """True when InkyPi runs as the systemd service and can change its own limit."""
    if not os.path.isdir("/run/systemd/system") or os.geteuid() != 0:
        return False
    try:
        result = _systemctl("show", SERVICE, "-p", "LoadState", "--value")
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and result.stdout.strip() == "loaded"


def current_percent():
    """Effective limit in percent, None when unlimited or unknown."""
    try:
        result = _systemctl("show", SERVICE, "-p", "CPUQuotaPerSecUSec", "--value")
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.fullmatch(r"(?:(\d+(?:\.\d+)?)s)?(?:(\d+)ms)?", result.stdout.strip())
    if result.returncode != 0 or not match or not any(match.groups()):
        return None
    seconds = float(match.group(1) or 0) + int(match.group(2) or 0) / 1000
    return round(seconds * 100)


def apply(percent):
    """Sets the limit (None: back to the installation default). Raises RuntimeError."""
    if percent is None:
        for path in _CONTROL_DROPINS:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
        result = _systemctl("daemon-reload")
    else:
        result = _systemctl("set-property", SERVICE, f"CPUQuota={int(percent)}%")
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout or "systemctl failed").strip())
    logger.info(f"CPU limit set to {percent if percent is not None else 'installation default'}%")
