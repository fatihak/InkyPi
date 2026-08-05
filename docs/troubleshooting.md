# Troubleshooting

## Timer/service not running

Check whether the timer is active:
```bash
systemctl status pi-weather-display.timer
```
This should show `Active: active (waiting)` (it's a timer, so it's normally
"waiting" between runs, not continuously "running").

Check the most recent run of the render itself:
```bash
systemctl status pi-weather-display.service
```

## Debugging

View the latest logs:
```bash
journalctl -u pi-weather-display.service -n 100
```

Tail the logs (useful while waiting for the next scheduled run):
```bash
journalctl -u pi-weather-display.service -f
```

## Force an immediate render

```bash
sudo systemctl start pi-weather-display.service
```

## Run manually

To diagnose an issue outside of systemd, run the script directly - this
prints logs straight to the terminal:
```bash
sudo /usr/local/pi-weather-display/venv/bin/python /usr/local/pi-weather-display/app/main.py
```

## No EEPROM detected

```bash
RuntimeError: No EEPROM detected! You must manually initialise your Inky board.
```

This project uses the [inky python library](https://github.com/pimoroni/inky)
from Pimoroni to detect and interface with Inky displays. However, the
auto-detect functionality does not work on some boards, which requires
manual setup (see [Manual Setup](https://github.com/pimoroni/inky?tab=readme-ov-file#manual-setup)).

Manually import and instantiate the correct Inky module in
`pi_weather_display/display/inky_driver.py`. For the 7.3 Inky Impression,
modify the file as follows:
```
@@ -1,6 +1,6 @@
 import logging
-from inky.auto import auto
+from inky.inky_ac073tc1a import Inky
 
 class InkyDriver:
     def __init__(self, saturation: float = 0.5):
-        self.inky_display = auto()
+        self.inky_display = Inky()
```

Then restart the timer:
```bash
sudo systemctl restart pi-weather-display.timer
```

## Colors look washed out or incorrect

Some color inaccuracies are expected due to the physical limitations of
e-ink displays, especially on multi-color panels with a limited color
palette and dithering.

There's no Settings page here - image/saturation adjustments are made
directly in `pi_weather_display/config.py`. The `inky_saturation` field
controls the saturation of the palette the image is dithered to by the
`inky` library; try `0` first, which tends to improve image quality. See
[this response](https://github.com/pimoroni/inky/issues/225#issuecomment-3213935144)
from the Pimoroni team for more details.

## Known Issues during Pi Zero W Installation

Due to limitations with the Pi Zero W, there are some known issues during
installation. For more details and community discussion, refer to this
[GitHub Issue](https://github.com/fatihak/InkyPi/issues/5) on the upstream
project (same underlying hardware/pip issues apply here).

### Pip Installation Error

#### Error message
```bash
WARNING: Retrying (Retry(total=4, connect=None, read=None, redirect=None, status=None)) after connection broken by 'ProtocolError('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))':
```

#### Recommended solution
Manually install the required pip packages in the venv:
```bash
source "/usr/local/pi-weather-display/venv/bin/activate"
pip install -r install/pi-weather-display-requirements.txt
deactivate
```
Restart the timer to apply the changes:
```bash
sudo systemctl restart pi-weather-display.timer
```

### Numpy/Pillow ImportError

#### Error message
```bash
ImportError: Error importing numpy: you should not try to import numpy from
its source directory; please exit the numpy source tree, and relaunch
your python interpreter from there.
```

#### Recommended solution
Manually reinstall Pillow in the venv:
```bash
sudo su
source "/usr/local/pi-weather-display/venv/bin/activate"
pip uninstall Pillow
pip install Pillow
deactivate
```
Restart the timer to apply the changes:
```bash
sudo systemctl restart pi-weather-display.timer
```
