import os

def open_hotspot():
    os.system("nmcli device wifi hotspot ifname wlan0 ssid 'INKY' password 'INKY' band bg")

def close_hotspot():
    os.system("nmcli connection down Hotspot")

def connect_to_wifi(ssid, password):
    os.system(f"nmcli device wifi connect '{ssid}' password '{password}'")

def is_connected():
    ssid = os.popen("iwgetid -r").read().strip()
    return bool(ssid)
