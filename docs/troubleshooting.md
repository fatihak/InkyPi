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
