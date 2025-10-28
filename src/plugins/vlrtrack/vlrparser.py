import requests
import json
import os
from bs4 import BeautifulSoup
from datetime import datetime


def getGames():
    res = requests.get("https://vlrggapi.vercel.app/match?q=upcoming&num_pages=1&max_retries=3&request_delay=1&timeout=30")
    data = res.json()

    # Save JSON to a file
    with open(os.path.join(os.path.dirname(__file__), "matches.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    print("JSON data saved to matches.json ✅")

    def getdata(url): 
        r = requests.get(url) 
        return r.text 

    # Extract the required data
    extracted_data = []

    for segment in data["data"]["segments"]:
        if not (segment["team1"] == "TBD" or segment["team2"] == "TBD"):  # Filter out matches where both teams are TBD
            # Scrape the match page for logos
            htmldata = getdata(segment["match_page"])
            soup = BeautifulSoup(htmldata, 'html.parser')
            images = [item['src'] for item in soup.find_all('img')]
            
            # Add the extracted data
            extracted_data.append({
                "team1": segment["team1"].upper(),
                "team2": segment["team2"].upper(),
                "unix_timestamp": datetime.strptime(segment["unix_timestamp"], "%Y-%m-%d %H:%M:%S").strftime("%b %d, %I:%M %p"),
                "match_series": segment["match_series"].upper(),
                "match_event": segment["match_event"].upper(),
                "match_page": segment["match_page"],
                "team1_logo": "http:" + (images[2] if len(images) > 2 else None),
                "team2_logo": "http:" + (images[3] if len(images) > 3 else None)
            })

    print("Formatted JSON data saved to formatted_matches.json ✅")
    return extracted_data[0] if extracted_data else {}