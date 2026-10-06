import subprocess
import logging
from datetime import datetime

from PIL import Image, ImageDraw
from plugins.base_plugin.base_plugin import BasePlugin
import socket
import psutil



logger = logging.getLogger(__name__)


class ServerStatus(BasePlugin):

    def __init__(self, config):
        super().__init__(config)
        self.config = config

    def generate_settings_template(self):
        return super().generate_settings_template()

    def generate_image(self, settings, device_config):

        status = self.get_status()

        w, h = device_config.get_resolution()

        img = Image.new("RGB", (w, h), "white")
        draw = ImageDraw.Draw(img)

        # Font opzionale
        try:
            from PIL import ImageFont
            font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            18
        )
            title_font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            22
        )
        except Exception:
            font = None
            title_font = None


    # Titolo
        draw.text(
        (20, 15),
        status["title"],
        fill="black",
        font=title_font
    )


    # Linea separazione
        draw.line(
        (w // 2, 45, w // 2, h - 30),
        fill="black",
        width=1
    )


    # Colonna sinistra - Sistema
        x1 = 15
        y1 = 55

        system_lines = [
        f"Temp : {status['temperature']} C",
        f"CPU  : {status['cpu']:.0f} %",
        f"RAM  : {status['ram']:.0f} %",
        f"Disk : {status['disk']:.0f} %",
        f"Up   : {status['uptime']}",
    ]

        for text in system_lines:
            draw.text(
            (x1, y1),
            text,
            fill="black",
            font=font
        )
            y1 += 25


    # Colonna destra - Servizi
        x2 = w // 2 + 15
        y2 = 55

        service_lines = [
        f"Net: {status['network']}",
        f"IP: {status['ip']}",
        "",
        f"Pi-hole:",
        f" {status['pihole']}",
        "",
        f"WireGuard:",
        f" {status['wireguard']}",
        f"Peers: {status['peers']}",
    ]

        for text in service_lines:
            draw.text(
            (x2, y2),
            text,
            fill="black",
            font=font
        )
            y2 += 23


    # Ora aggiornamento
        draw.text(
        (20, h - 25),
        f"Aggiornato: {status['time']}",
        fill="black",
        font=font
    )


        return img



    def get_status(self):

        system = self.get_system_info()

        return {
        "title": "RASPI STATUS",

        "temperature": system["temperature"],
        "cpu": system["cpu"],
        "ram": system["ram"],
        "disk": system["disk"],
        "uptime": system["uptime"],

        "network": system["network"],
        "ip": system["ip"],

        "pihole": self.service_status("pihole-FTL"),
        "wireguard": self.service_status("wg-quick@wg0"),
        "peers": self.wg_peers(),

        "time": datetime.now().strftime("%H:%M")
        }

    
    def get_system_info(self):

        # Temperatura CPU
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                temperature = round(int(f.read()) / 1000, 1)
        except Exception:
            temperature = None

        # CPU
        cpu = psutil.cpu_percent(interval=0.5)

        # RAM
        ram = psutil.virtual_memory().percent

        # Disco (/)
        disk = psutil.disk_usage("/").percent

        # Uptime
        boot = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot

        days = uptime.days
        hours = uptime.seconds // 3600

        if days > 0:
            uptime_str = f"{days}d {hours}h"
        else:
            uptime_str = f"{hours}h"

        # IP locale
        ip = "-"

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            network = "OK"
        except Exception:
            network = "DOWN"

        return {
            "temperature": temperature,
            "cpu": cpu,
            "ram": ram,
            "disk": disk,
            "uptime": uptime_str,
            "network": network,
            "ip": ip
        }



    def service_status(self, service):
        try:
            result = subprocess.check_output(
                ["systemctl", "is-active", service],
                text=True
            ).strip()

            return "OK" if result == "active" else "DOWN"

        except Exception:
            return "DOWN"


    def wg_peers(self):
        try:
            data = subprocess.check_output(
                ["wg", "show", "wg0", "latest-handshakes"],
                text=True
            )

            now = int(datetime.now().timestamp())
            active = 0

            for line in data.strip().splitlines():
                parts = line.split()

                if len(parts) == 2:
                    timestamp = int(parts[1])

                    if timestamp > now - 300:
                        active += 1

            return active

        except Exception as e:
            logger.error(e)
            return -1

