
"""
Fetch real scheduled departures from an airport on a given date, and
store them: flight number, airline, destination, scheduled times.
Flight schedules are largely stable week to week, so one fetch per
airport gives a reasonably representative snapshot.
"""
import os
import sqlite3
import time
import requests
from dotenv import load_dotenv

load_dotenv()

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY")
RAPIDAPI_HOST = "aerodatabox.p.rapidapi.com"
DB_FILE = "flights.db"

HEADERS = {
    "x-rapidapi-key": RAPIDAPI_KEY,
    "x-rapidapi-host": RAPIDAPI_HOST,
    "Content-Type": "application/json",
}

def init_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS airports (
            iata TEXT PRIMARY KEY, name TEXT, lat REAL, lon REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS flights (
            flight_number TEXT,
            airline TEXT,
            origin_iata TEXT,
            destination_iata TEXT,
            destination_name TEXT,
            scheduled_departure_local TEXT,
            scheduled_arrival_local TEXT,
            checked_date TEXT,
            PRIMARY KEY (flight_number, scheduled_departure_local)
        )
    """)
    conn.commit()
    conn.close()


def fetch_departures(iata_code: str, from_local: str, to_local: str) -> list[dict]:
    url = f"https://{RAPIDAPI_HOST}/flights/airports/iata/{iata_code}/{from_local}/{to_local}"
    params = {
        "withLeg": "true",
        "direction": "Departure",
        "withCancelled": "false",
        "withCodeshared": "false",
        "withCargo": "false",
        "withPrivate": "false",
        "withLocation": "false",
    }

    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=30)
    except requests.exceptions.RequestException as e:
        print(f"Network error fetching {iata_code}: {e}")
        return []  # fail gracefully — caller just gets an empty list, not a crash

    if response.status_code != 200:
        print(f"AeroDataBox error for {iata_code}: {response.status_code} — {response.text[:200]}")
        return []

    data = response.json()
    flights = []
    for dep in data.get("departures", []):
        arrival_airport = dep.get("arrival", {}).get("airport", {})
        if not arrival_airport.get("iata"):
            continue

        flights.append({
            "flight_number": dep.get("number"),
            "airline": dep.get("airline", {}).get("name"),
            "destination_iata": arrival_airport.get("iata"),
            "destination_name": arrival_airport.get("name"),
            "scheduled_departure_local": dep.get("departure", {}).get("scheduledTime", {}).get("local"),
            "scheduled_arrival_local": dep.get("arrival", {}).get("scheduledTime", {}).get("local"),
        })
    return flights


def store_departures(origin_iata: str, origin_name: str, origin_lat: float, origin_lon: float, date: str):
    conn = sqlite3.connect(DB_FILE)
    conn.execute(
        "INSERT OR REPLACE INTO airports VALUES (?, ?, ?, ?)",
        (origin_iata, origin_name, origin_lat, origin_lon),
    )

    windows = [
        (f"{date}T00:00", f"{date}T12:00"),
        (f"{date}T12:00", f"{date}T23:59"),
    ]

    total = 0
    for from_local, to_local in windows:
        flights = fetch_departures(origin_iata, from_local, to_local)
        for f in flights:
            conn.execute("""
                INSERT OR REPLACE INTO flights VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                f["flight_number"], f["airline"], origin_iata,
                f["destination_iata"], f["destination_name"],
                f["scheduled_departure_local"], f["scheduled_arrival_local"],
                date,
            ))
            total += 1
        time.sleep(2)

    conn.commit()
    conn.close()
    print(f"Stored {total} departures for {origin_iata} on {date}")


if __name__ == "__main__":
    init_db()

    AIRPORTS_TO_LOAD = [
        {"iata": "TIR", "name": "Tirupati Airport", "lat": 13.6326216, "lon": 79.5415119},
    ]
    CHECK_DATE = "2026-09-10"  # a representative near-future weekday

    for airport in AIRPORTS_TO_LOAD:
        store_departures(airport["iata"], airport["name"], airport["lat"], airport["lon"], CHECK_DATE)
        time.sleep(3)