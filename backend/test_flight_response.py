import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()

HEADERS = {
    "x-rapidapi-key": os.getenv("RAPIDAPI_KEY"),
    "x-rapidapi-host": "aerodatabox.p.rapidapi.com",
    "Content-Type": "application/json",
}

# Explicit date range instead of "now" — pick a near-future date so there's
# actually scheduled data to see. Adjust the date if needed.
url = "https://aerodatabox.p.rapidapi.com/flights/airports/iata/TIR/2026-09-10T06:00/2026-09-10T18:00"
params = {
    "withLeg": "true",
    "direction": "Departure",
    "withCancelled": "false",
    "withCodeshared": "false",
    "withCargo": "false",
    "withPrivate": "false",
    "withLocation": "false",
}

response = requests.get(url, headers=HEADERS, params=params, timeout=30)
print("Status:", response.status_code)
print(json.dumps(response.json(), indent=2)[:3000])