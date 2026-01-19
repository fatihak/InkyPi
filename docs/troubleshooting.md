# Troubleshooting

## InkyPi Service not running

Check the status of the service:
```bash
sudo systemctl status inkypi.service
```

If the service is running, this should output `Active: active (running)`:
```bash
● inkypi.service - InkyPi App
     Loaded: loaded (/etc/systemd/system/inkypi.service; enabled; preset: enabled)
     Active: active (running) since Sun 2024-12-22 20:48:53 GMT; 28s ago
   Main PID: 48333 (bash)
      Tasks: 6 (limit: 166)
        CPU: 6.333s
     CGroup: /system.slice/inkypi.service
             ├─48333 bash /usr/local/bin/inkypi -d
             └─48336 python -u /home/pi/inky/src/inkypi.py -d
```

If the service is not running, check the logs for any errors or issues.

## Debugging

View the latest logs for the InkyPi service:
```bash
journalctl -u inkypi -n 100
```

Tail the logs:
```bash
journalctl -u inkypi -f
```

## Restart the InkyPi Service

```bash
sudo systemctl restart inkypi.service
```


## Run InkyPi Manually

If the InkyPi service is not running, try manually running the startup script to diagnose. This should output the logs to the terminal and make it easier to troubleshoot any errors:

```bash
sudo /usr/local/bin/inkypi -d
```

## API Key not configured

Some plugins require API Keys to be configured in order to run. These need to be configured in a .env file at the root of the project. See [API Keys](api_keys.md) for details.

## Clock/Sunset/Sunrise Time is wrong

If the displayed time is incorrect, your timezone setting may not be configured. You can update this in the Settings page of the Web UI.

## Failed to retrieve weather data

```bash
Failed to retrieve weather data
ERROR - root - Failed to retrieve weather data: b'{"cod":401, "message": "Please note that using One Call 3.0 requires a separate subscription to the One Call by Call plan. Learn more here https://openweathermap.org/price. If you have a valid subscription to the One Call by Call plan, but still receive this error, then please see https://openweathermap.org/faq#error401 for more info."}'
```

InkyPi uses the One Call API 3.0 API which requires a subscription but is free for up to 1,000 requests a day. See [API Keys](api_keys.md) for instructions.

## No EEPROM detected

```bash
RuntimeError: No EEPROM detected! You must manually initialise your Inky board.
```

InkyPi uses the [inky python library](https://github.com/pimoroni/inky) from Pimoroni to detect and interface with Inky displays. However, the auto-detect functionality does not work on some boards, which requires manual setup (see [Manual Setup](https://github.com/pimoroni/inky?tab=readme-ov-file#manual-setup)).

Manually import and instantiate the correct Inky module in src/display_manager.py. For the 7.3 Inky Impression, modify the file as follows:
```
@@ -1,5 +1,5 @@
 import os
-from inky.auto import auto
+from inky.inky_ac073tc1a import Inky
 from utils.image_utils import resize_image, change_orientation
 from plugins.plugin_registry import get_plugin_instance

@@ -8,7 +8,7 @@ class DisplayManager:
     def __init__(self, device_config):
         """Manages the display and rendering of images."""
         self.device_config = device_config
-        self.inky_display = auto()
+        self.inky_display = Inky()
         self.inky_display.set_border(self.inky_display.BLACK)
```

Then restart the inkypi service:
```
sudo systemctl restart inkypi.service
```

## Waveshare e-Paper EPD Devices

### Missing modules

Ensure that the necessary modeules are available in the python environment. Waveshare requires:

- gpiozero
- lgpio
- RPi.GPIO

in addition to the libraries that are normally installed for Inky screens.

### Screen not updating

Verify SPI configuration using `ls /dev/sp*`.  There should be two entries for _spidev0.0_ and _spidev0.1_.  

If only the first is visible, check _/boot/firmware/config.txt_. The regular install of InkyPi adds `dtoverlay=spi0-0cs` to the this file.  If it is there, either delete it (for default behaviour) or specifically add `dtoverlay=spi0-2cs`.

### ERROR: Failed to download Waveshare driver

The installation script attempts to fetch the EPD driver library based on the -W argument provided. Please double-check that:
- You’ve entered the correct display model.
- The corresponding driver file exists in the [waveshare e-Paper github repository](https://github.com/waveshareteam/e-Paper/tree/master/RaspberryPi_JetsonNano/python/lib/waveshare_epd).

Note: Some displays, such as the epd4in0e, are not included in the main library path above. Instead, they may be located under the [E-paper_Seperate_Program](https://github.com/waveshareteam/e-Paper/tree/master/E-paper_Separate_Program) path. If your model is there, look under:
```bash
/RaspberryPi_JetsonNano/python/lib/waveshare_epd/
```

In this case, you’ll need to manually copy both the epdXinX.py and epdconfig.py files into:
```bash
InkyPi/src/display/waveshare_epd/
```

For example, to copy the driver and epdconfig files for epd13in3E (Waveshare Spectra 6 (E6) Full Color 13.3 inch display):
```bash
cd InkyPi/src/display/waveshare_epd/
curl -L -O https://raw.githubusercontent.com/waveshareteam/e-Paper/refs/heads/master/E-paper_Separate_Program/13.3inch_e-Paper_E/RaspberryPi/python/lib/epd13in3E.py
curl -L -O https://raw.githubusercontent.com/waveshareteam/e-Paper/refs/heads/master/E-paper_Separate_Program/13.3inch_e-Paper_E/RaspberryPi/python/lib/epdconfig.py
```

Additionally, you'll need the DEV_config* files in the same directory for your system. If you don’t know which file applies to your hardware, you can download all available DEV config files.
For example, for the epd13in3E display & Pi Zero 2 W, pull the following file:
```bash
curl -L -O https://raw.githubusercontent.com/waveshareteam/e-Paper/refs/heads/master/E-paper_Separate_Program/13.3inch_e-Paper_E/RaspberryPi/python/lib/DEV_Config_64_b.so
```

Once the files are in place, rerun the installation script. The script will detect the driver locally and skip the download step.

## Today's Newspaper not found

Daily newspaper front pages are sourced from [Freedom Forum](https://frontpages.freedomforum.org/gallery). The list of available newspapers may change periodically. InkyPi maintains an up-to-date list of newspapers provided by Freedom Forum, but there may be times when the list becomes outdated.

If you encounter this error, please feel free to open an Issue, including the name of the newspaper you were trying to access, and we'll work to update the list.

Also consider supporting the important work of Freedom Forum, an organization dedicated to promoting and protecting free press and the First Amendment: https://www.freedomforum.org/take-action/

## Known Issues during Pi Zero W Installation

Due to limitations with the Pi Zero W, there are some known issues during the InkyPi installation process. For more details and community discussion, refer to this [GitHub Issue](https://github.com/fatihak/InkyPi/issues/5).

### Pip Installation Error

#### Error message
```bash
WARNING: Retrying (Retry(total=4, connect=None, read=None, redirect=None, status=None)) after connection broken by 'ProtocolError('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))':
```

#### Recommended solution
Manually install the required pip packages in the inkypi virtual environment:
```bash
source "/usr/local/inkypi/venv_inkypi/bin/activate"
pip install -r install/requirements.txt
deactivate
```
Restart the inkypi service to apply the changes:
```bash
sudo systemctl restart inkypi.service
```

### Numpy ImportError

#### Error message
```bash
ImportError: Error importing numpy: you should not try to import numpy from
its source directory; please exit the numpy source tree, and relaunch
your python interpreter from there.
```

#### Recommended solution
To resolve this issue, manually reinstall the Pillow library in the inkypi virtual environment:
```bash
sudo su
source "/usr/local/inkypi/venv_inkypi/bin/activate"
pip uninstall Pillow
pip install Pillow
deactivate
```

Restart the inkypi service to apply the changes:
```bash
sudo systemctl restart inkypi.service
```

## Colors look washed out or incorrect

Some color inaccuracies are expected due to the physical limitations of e-ink displays, especially on multi-color panels with a limited color palette and dithering.

InkyPi provides several image enhancement controls in the Settings page that can help improve how images appear on your display: Saturation, Contrast, Sharpness, Brightness. These adjustments are applied to images using the Pillow ImageEnhance module before they are displayed. You can experiment with these values to find what looks best for your specific panel and content.

For more details on how each setting behaves, see the [Pillow documentation](https://pillow.readthedocs.io/en/stable/reference/ImageEnhance.html).

### Inky Driver Saturation

For Inky displays from Pimoroni, there is an additional option for `Inky Driver Saturation` in the Settings page. This controls the saturation of the palette to which an image is dithered to in the Inky library. Try setting this to '0' which seems to improve the quality of images displayed.

See [this response](https://github.com/pimoroni/inky/issues/225#issuecomment-3213935144) from the Pimoroni team for more details.
