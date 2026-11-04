import requests
from PIL import Image, ImageEnhance, ImageOps, ImageFilter
from io import BytesIO
import os
import logging
import hashlib
import tempfile
import subprocess
import shutil
import platform
from pathlib import Path

logger = logging.getLogger(__name__)

def get_image(image_url):
    response = requests.get(image_url, timeout=30)
    img = None
    if 200 <= response.status_code < 300 or response.status_code == 304:
        img = Image.open(BytesIO(response.content))
    else:
        logger.error(f"Received non-200 response from {image_url}: status_code: {response.status_code}")
    return img

def change_orientation(image, orientation, inverted=False):
    if orientation == 'horizontal':
        angle = 0
    elif orientation == 'vertical':
        angle = 90

    if inverted:
        angle = (angle + 180) % 360

    return image.rotate(angle, expand=1)

def resize_image(image, desired_size, image_settings=[]):
    img_width, img_height = image.size
    desired_width, desired_height = desired_size
    desired_width, desired_height = int(desired_width), int(desired_height)

    img_ratio = img_width / img_height
    desired_ratio = desired_width / desired_height

    keep_width = "keep-width" in image_settings

    x_offset, y_offset = 0,0
    new_width, new_height = img_width,img_height
    # Step 1: Determine crop dimensions
    desired_ratio = desired_width / desired_height
    if img_ratio > desired_ratio:
        # Image is wider than desired aspect ratio
        new_width = int(img_height * desired_ratio)
        if not keep_width:
            x_offset = (img_width - new_width) // 2
    else:
        # Image is taller than desired aspect ratio
        new_height = int(img_width / desired_ratio)
        if not keep_width:
            y_offset = (img_height - new_height) // 2

    # Step 2: Crop the image
    image = image.crop((x_offset, y_offset, x_offset + new_width, y_offset + new_height))

    # Step 3: Resize to the exact desired dimensions (if necessary)
    return image.resize((desired_width, desired_height), Image.LANCZOS)

def apply_image_enhancement(img, image_settings={}):
    # Convert image to RGB mode if necessary for enhancement operations
    # ImageEnhance requires RGB mode for operations like blend
    if img.mode not in ('RGB', 'L'):
        img = img.convert('RGB')

    # Each enhance() call blends over the full image, so skip factors of 1.0
    # (the no-op default) to avoid wasted full-frame passes on low-resource devices.
    enhancements = [
        (ImageEnhance.Brightness, image_settings.get("brightness", 1.0)),
        (ImageEnhance.Contrast, image_settings.get("contrast", 1.0)),
        (ImageEnhance.Color, image_settings.get("saturation", 1.0)),
        (ImageEnhance.Sharpness, image_settings.get("sharpness", 1.0)),
    ]
    for enhancer, factor in enhancements:
        if factor != 1.0:
            img = enhancer(img).enhance(factor)

    return img

def compute_image_hash(image):
    """Compute SHA-256 hash of an image."""
    image = image.convert("RGB")
    img_bytes = image.tobytes()
    return hashlib.sha256(img_bytes).hexdigest()

def take_screenshot_html(html_str, dimensions, timeout_ms=None):
    image = None
    try:
        # Create a temporary HTML file
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as html_file:
            html_file.write(html_str.encode("utf-8"))
            html_file_path = html_file.name

        image = take_screenshot(html_file_path, dimensions, timeout_ms)

        # Remove html file
        os.remove(html_file_path)

    except Exception as e:
        logger.error(f"Failed to take screenshot: {str(e)}")

    return image

# ---------------------------------------------------------------------------
# Screenshot backends
#
# Recent Chromium builds crash with SIGILL (return code 132) on ARMv6 boards
# such as the Raspberry Pi Zero W and Pi 1. On those boards Chromium is skipped
# and headless Firefox ESR is used instead.
#
# Override the order with INKYPI_SCREENSHOT_BACKEND, e.g. "firefox" or
# "chromium,firefox". "wkhtmltoimage" is available but only if listed here.
# ---------------------------------------------------------------------------

ALL_BACKENDS = ("chromium", "firefox", "wkhtmltoimage")
SIGILL_RETURN_CODES = (132, -4)  # 128 + SIGILL, or killed by signal 4

FIREFOX_PREFS = {
    "browser.shell.checkDefaultBrowser": False,
    "browser.startup.homepage_override.mstone": "ignore",
    "browser.aboutwelcome.enabled": False,
    "datareporting.policy.dataSubmissionEnabled": False,
    "datareporting.healthreport.uploadEnabled": False,
    "toolkit.telemetry.enabled": False,
    "toolkit.telemetry.reportingpolicy.firstRun": False,
    "app.update.enabled": False,
    "app.normandy.enabled": False,
    "extensions.update.enabled": False,
    "browser.safebrowsing.malware.enabled": False,
    "browser.safebrowsing.phishing.enabled": False,
    "browser.cache.disk.enable": False,
    "network.prefetch-next": False,
    "network.dns.disablePrefetch": True,
    "media.autoplay.default": 5,
    # keep memory use down on 512MB boards
    "fission.autostart": False,
    "dom.ipc.processCount": 1,
    "dom.ipc.processPrelaunch.enabled": False,
    # file:// pages load fonts/scripts from the InkyPi static dir
    "security.fileuri.strict_origin_policy": False,
}


def is_armv6():
    """True on ARMv6 boards (Pi Zero W / Pi 1), where current browsers can't run."""
    return platform.machine().lower().startswith("armv6")


_is_armv6 = is_armv6


def _backend_order():
    override = os.environ.get("INKYPI_SCREENSHOT_BACKEND", "").strip()
    if override:
        order = [b.strip().lower() for b in override.split(",") if b.strip()]
        unknown = [b for b in order if b not in ALL_BACKENDS]
        if unknown:
            logger.warning(f"Ignoring unknown screenshot backends: {unknown}")
        return [b for b in order if b in ALL_BACKENDS]
    # wkhtmltoimage is opt-in only: its 2012-era engine can't lay out the
    # built-in plugin pages (flex/grid, min(), container-query units) and
    # produces a mostly blank image rather than an error.
    if _is_armv6():
        return ["firefox"]
    return ["chromium", "firefox"]


def _find_binary(candidates):
    for candidate in candidates:
        path = shutil.which(candidate)
        if path:
            logger.debug(f"Found binary: {candidate} at {path}")
            return path
    return None


def _find_chromium_binary():
    """Find the first available Chromium-based binary in system PATH."""
    return _find_binary(["chromium-headless-shell", "chromium", "chromium-browser", "chrome"])


def _to_uri(target):
    """Turn a local file path into a file:// URI; leave URLs untouched."""
    if "://" in target:
        return target
    return Path(os.path.abspath(target)).as_uri()


def _stderr_tail(result, lines=5):
    try:
        text = (result.stderr or b"").decode("utf-8", errors="replace").strip()
    except Exception:
        return ""
    return " | ".join(text.splitlines()[-lines:])


def _load_png(path, dimensions):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return None
    with Image.open(path) as img:
        image = img.copy()
    width, height = int(dimensions[0]), int(dimensions[1])
    if image.size != (width, height):
        # Some renderers add or drop a few pixels; crop/pad to the panel size.
        canvas = Image.new("RGB", (width, height), "white")
        canvas.paste(image.crop((0, 0, min(width, image.width), min(height, image.height))), (0, 0))
        image = canvas
    return image


def _run(command, timeout_s, env=None):
    return subprocess.run(command, capture_output=True, check=False, timeout=timeout_s, env=env)


def _screenshot_chromium(target, dimensions, timeout_ms, out_path):
    browser = _find_chromium_binary()
    if not browser:
        logger.info("Chromium not installed, skipping.")
        return None

    command = [
        browser,
        target,
        "--headless",
        f"--screenshot={out_path}",
        f"--window-size={dimensions[0]},{dimensions[1]}",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--use-gl=swiftshader",
        "--hide-scrollbars",
        "--in-process-gpu",
        "--js-flags=--jitless",
        "--disable-zero-copy",
        "--disable-gpu-memory-buffer-compositor-resources",
        "--disable-extensions",
        "--disable-plugins",
        "--mute-audio",
        "--renderer-process-limit=1",
        "--no-zygote",
        "--no-sandbox"
    ]
    if timeout_ms:
        command.append(f"--timeout={timeout_ms}")
    result = _run(command, timeout_s=(timeout_ms or 0) / 1000 + 120)

    if result.returncode in SIGILL_RETURN_CODES:
        logger.error(
            f"Chromium crashed with an illegal instruction (return code {result.returncode}). "
            f"This CPU ({platform.machine()}) is not supported by the installed Chromium build. "
            "Install firefox-esr or set INKYPI_SCREENSHOT_BACKEND=firefox."
        )
        return None
    if result.returncode != 0:
        logger.error(f"Chromium screenshot failed (return code: {result.returncode}) {_stderr_tail(result)}")
        return None
    return _load_png(out_path, dimensions)


def _firefox_profile_dir():
    profile = os.path.join(tempfile.gettempdir(), "inkypi-firefox-profile")
    os.makedirs(profile, exist_ok=True)
    prefs = dict(FIREFOX_PREFS)
    if _is_armv6():
        # SpiderMonkey's JITs target ARMv7+; the interpreter is plenty for these pages.
        prefs.update({
            "javascript.options.baselinejit": False,
            "javascript.options.ion": False,
            "javascript.options.wasm": False,
            "javascript.options.asmjs": False,
        })
    lines = []
    for key, value in prefs.items():
        if isinstance(value, bool):
            value = "true" if value else "false"
        elif isinstance(value, str):
            value = f'"{value}"'
        lines.append(f'user_pref("{key}", {value});')
    with open(os.path.join(profile, "user.js"), "w") as f:
        f.write("\n".join(lines) + "\n")
    # A stale lock from a killed run would make Firefox refuse the profile.
    for lock in ("lock", ".parentlock", "parent.lock"):
        try:
            os.remove(os.path.join(profile, lock))
        except (FileNotFoundError, IsADirectoryError):
            pass
        except OSError:
            pass
    return profile


def _screenshot_firefox(target, dimensions, timeout_ms, out_path):
    firefox = _find_binary(["firefox-esr", "firefox"])
    if not firefox:
        logger.info("Firefox not installed, skipping. Install it with: sudo apt install firefox-esr")
        return None

    env = dict(os.environ)
    env["MOZ_HEADLESS"] = "1"
    env.setdefault("HOME", tempfile.gettempdir())
    env["MOZ_CRASHREPORTER_DISABLE"] = "1"

    command = [
        firefox,
        "--headless",
        "--no-remote",
        "--profile", _firefox_profile_dir(),
        "--screenshot", out_path,
        f"--window-size={dimensions[0]},{dimensions[1]}",
        _to_uri(target),
    ]
    # Firefox's first start on a Pi Zero W can take a minute or more.
    timeout_s = max(180, (timeout_ms or 0) / 1000 + 120)
    try:
        result = _run(command, timeout_s=timeout_s, env=env)
    except subprocess.TimeoutExpired:
        logger.error(f"Firefox screenshot timed out after {int(timeout_s)}s")
        return None

    image = _load_png(out_path, dimensions)
    if image is None:
        logger.error(f"Firefox screenshot failed (return code: {result.returncode}) {_stderr_tail(result)}")
    return image


def _screenshot_wkhtmltoimage(target, dimensions, timeout_ms, out_path):
    binary = _find_binary(["wkhtmltoimage"])
    if not binary:
        logger.info("wkhtmltoimage not installed, skipping.")
        return None
    logger.warning("Using wkhtmltoimage: pages that rely on modern JavaScript (e.g. charts) may render incompletely.")

    command = [
        binary,
        "--quiet",
        "--format", "png",
        "--width", str(dimensions[0]),
        "--height", str(dimensions[1]),
        "--enable-local-file-access",
        "--javascript-delay", "2000",
        target,
        out_path,
    ]
    try:
        result = _run(command, timeout_s=max(120, (timeout_ms or 0) / 1000 + 60))
    except subprocess.TimeoutExpired:
        logger.error("wkhtmltoimage timed out")
        return None
    image = _load_png(out_path, dimensions)
    if image is None:
        logger.error(f"wkhtmltoimage failed (return code: {result.returncode}) {_stderr_tail(result)}")
    return image


_BACKENDS = {
    "chromium": _screenshot_chromium,
    "firefox": _screenshot_firefox,
    "wkhtmltoimage": _screenshot_wkhtmltoimage,
}


def take_screenshot(target, dimensions, timeout_ms=None):
    order = _backend_order()
    for name in order:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as img_file:
            img_file_path = img_file.name
        # Start with no file so an empty placeholder is never mistaken for output.
        os.remove(img_file_path)
        try:
            image = _BACKENDS[name](target, dimensions, timeout_ms, img_file_path)
            if image is not None:
                logger.debug(f"Screenshot taken with {name}")
                return image
        except Exception as e:
            logger.error(f"{name} screenshot failed: {str(e)}")
        finally:
            if os.path.exists(img_file_path):
                os.remove(img_file_path)

    logger.error(
        f"Failed to take screenshot: no working renderer (tried {', '.join(order) or 'none'}). "
        + ("Current Chromium and Firefox builds don't run on ARMv6 boards (Pi Zero W / Pi 1); "
           "plugins that render HTML can't work here. The weather plugin draws without a browser."
           if _is_armv6() else "")
    )
    return None

def pad_image_blur(img: Image, dimensions: tuple[int, int]) -> Image:
    bkg = ImageOps.fit(img, dimensions)
    bkg = bkg.filter(ImageFilter.BoxBlur(8))
    img = ImageOps.contain(img, dimensions)

    img_size = img.size
    bkg.paste(img, ((dimensions[0] - img_size[0]) // 2, (dimensions[1] - img_size[1]) // 2))
    return bkg
