import os
import time
import logging

logger = logging.getLogger(__name__)

def open_hotspot():
    os.system("sudo nmcli device wifi hotspot ifname wlan0 ssid 'INKY' password 'SuperSecret123' band bg")
    logger.info("Started hotspot!")

def close_hotspot():
    hotspot_name = os.popen("nmcli -t -f NAME,TYPE connection show --active | grep wifi | cut -d: -f1").read().strip()
    if hotspot_name:
        os.system(f"sudo nmcli connection down '{hotspot_name}'")
        os.system(f"sudo nmcli connection delete '{hotspot_name}'")

def connect_to_wifi(ssid, password):
    close_hotspot()
    time.sleep(5)
    os.system(f"sudo nmcli device wifi connect '{ssid}' password '{password}'")

def is_connected():
    ssid = os.popen("iwgetid -r").read().strip()
    return bool(ssid)

