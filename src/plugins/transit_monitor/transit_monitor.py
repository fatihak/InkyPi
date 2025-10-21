from plugins.base_plugin.base_plugin import BasePlugin
from PIL import Image, ImageDraw, ImageFont
import requests
import os, re, json, textwrap
from datetime import datetime
from zoneinfo import ZoneInfo

def parse_stop_codes(raw: str):
    return [p for p in re.split(r"[,\s]+", raw or "") if p.isdigit()]

class TransitMonitor(BasePlugin):
    def generate_image(self, settings, device_config):
        #api_key = os.getenv("511_API_KEY")
        api_key = "779650b4-c11a-41e2-bc99-af61125240da"
        stops = parse_stop_codes(settings.get("stop_codes")) 


        all_busses = []
        for stop in stops:
            all_busses.extend(self.whenArrive(stop, api_key))

        # MVP: dump raw JSON to screen
        raw = json.dumps({"agency": "SF", "stops": stops, "busses": all_busses}, indent=2)

        img = Image.new("RGB", (400, 300), "white")
        d = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype("DejaVuSansMono.ttf", 14)
        except:
            font = ImageFont.load_default()

        y = 10
        for line in textwrap.wrap(raw, width=50):
            d.text((10, y), line, fill="black", font=font)
            y += 15
            if y > 285:
                break
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