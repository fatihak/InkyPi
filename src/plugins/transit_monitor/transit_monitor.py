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
        #stops = ['14621', '14622', '15014', '15015']

        all_busses = []
        for stop in stops:
            all_busses.extend(self.whenArrive(stop, api_key))

        all_busses.sort(key=lambda x: x["minutes_to_arrival"])
        items = all_busses[:3]

        return self.render_image(
            dimensions=(400, 300),
            html_file="transit_monitor.html",
            css_file="transit_monitor.css",
            template_params={"items": items, "plugin_settings": settings}
        )
    
    
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