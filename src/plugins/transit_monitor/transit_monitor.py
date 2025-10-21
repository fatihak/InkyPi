from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageDraw, ImageFont
import requests
import json
import textwrap
from datetime import datetime
from zoneinfo import ZoneInfo


class TransitMonitor(BasePlugin):
    def generate_image(self, settings, device_config):
        api_key = device_config.get_dotenv("511_API_KEY")
        stop_code = "14621"  # hardcode for MVP

        busses = self.whenArrive(stop_code, api_key)  # your existing method
        raw = repr(busses)  # or: json.dumps(busses, indent=2)

        # make a white canvas matching your display
        w, h = device_config.get_resolution()
        img = Image.new("RGB", (w, h), "white")
        d = ImageDraw.Draw(img)

        try:
            font = ImageFont.truetype("DejaVuSansMono.ttf", 14)  # mono looks nicer for raw text
        except:
            font = ImageFont.load_default()

        # simple wrap so it stays on-screen
        max_chars = 60  # tweak for your width/font
        y = 10
        for line in textwrap.wrap(raw, width=max_chars):
            d.text((10, y), line, fill="black", font=font)
            y += 16
            if y > h - 16:
                break  # stop if we run out of space

        return img
    
    
    def whenArrive(self, stopCode, api_key):
        busses = []
        url = "http://api.511.org/transit/StopMonitoring"
        params = {
            "api_key": api_key,
            "agency": "SF",
            "stopCode": stopCode,
            "format": "json"
        }
        r = requests.get(url, params=params)
        data = json.loads(r.text.encode('utf-8').decode('utf-8-sig'))
        stops = data['ServiceDelivery']['StopMonitoringDelivery']['MonitoredStopVisit']
        
        for visit in stops:
            journey = visit['MonitoredVehicleJourney']
            line = journey['LineRef']
            call = journey['MonitoredCall']
            destination = call['DestinationDisplay']
            raw_time = call['ExpectedArrivalTime']

            arrival_time = datetime.fromisoformat(raw_time.replace("Z", "+00:00")).astimezone(ZoneInfo("America/Los_Angeles"))
            now = datetime.now(ZoneInfo("America/Los_Angeles"))
            minutes_to_arrival = int((arrival_time - now).total_seconds() / 60)

            formatted_time = arrival_time.strftime("%I:%M %p").lstrip("0")

            busses.append({
                "line": line,
                "destination": destination,
                "arrival_time": formatted_time,
                "minutes_to_arrival": minutes_to_arrival
            })
        return busses