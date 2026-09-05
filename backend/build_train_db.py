"""
Let's load it into SQLite  — structured as two tables: trains and train_stops.
A train has one name/number/running-days. A stop happens many times per train (one row per station). This is a classic
one-to-many relationship in database design — one train, many stops — so we split it into two tables linked by train_number, 
rather than repeating the train's name/running-days on every single stop row (which would be wasteful and error-prone to keep
in sync).
output of this file creating sqlite db file named with trains.db
"""

import json
import sqlite3
from pathlib import Path

DATA_DIR = Path("data")  # put the 3 JSON files in backend/data/
DB_FILE = "trains.db"

SOURCE_FILES = ["SF-TRAINS.json", "EXP-TRAINS.json", "PASS-TRAINS.json"]


def parse_distance(distance_str: str) -> int:
    """'884 kms' -> 884"""
    return int(distance_str.replace("kms", "").strip())


def build_database():
    conn = sqlite3.connect(DB_FILE)

    conn.execute("DROP TABLE IF EXISTS trains")
    conn.execute("DROP TABLE IF EXISTS train_stops")

    conn.execute("""
        CREATE TABLE trains (
            train_number TEXT PRIMARY KEY,
            train_name TEXT,
            train_class TEXT,
            runs_sun INTEGER, runs_mon INTEGER, runs_tue INTEGER,
            runs_wed INTEGER, runs_thu INTEGER, runs_fri INTEGER, runs_sat INTEGER
        )
    """)

    conn.execute("""
        CREATE TABLE train_stops (
            train_number TEXT,
            stop_order INTEGER,
            station_name TEXT,
            arrival_time TEXT,
            departure_time TEXT,
            distance_km INTEGER,
            day_number INTEGER,
            FOREIGN KEY (train_number) REFERENCES trains(train_number)
        )
    """)

    total_trains = 0
    total_stops = 0

    for filename in SOURCE_FILES:
        train_class = filename.split("-")[0]  # "SF", "EXP", or "PASS"
        filepath = DATA_DIR / filename

        with open(filepath) as f:
            trains = json.load(f)

        for train in trains:
            running = train["runningDays"]
            conn.execute("""
                INSERT OR IGNORE INTO trains VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                train["trainNumber"], train["trainName"], train_class,
                int(running["SUN"]), int(running["MON"]), int(running["TUE"]),
                int(running["WED"]), int(running["THU"]), int(running["FRI"]),
                int(running["SAT"]),
            ))
            total_trains += 1

            for stop in train["trainRoute"]:
                conn.execute("""
                    INSERT INTO train_stops VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    train["trainNumber"],
                    int(stop["sno"]),
                    stop["stationName"],
                    stop["arrives"],
                    stop["departs"],
                    parse_distance(stop["distance"]),
                    int(stop["day"]),
                ))
                total_stops += 1


    """
    this is important for performance: an index lets the database find all rows matching a station name almost instantly 
    instead of scanning all ~40,000+ stop rows one by one every time we ask "which trains stop at Guntur." 
    Think of it like a book's index — jump straight to the right page instead of reading cover to cover.
    """
    conn.execute("CREATE INDEX idx_stop_station ON train_stops(station_name)")
    conn.execute("CREATE INDEX idx_stop_train ON train_stops(train_number)")

    conn.commit()
    conn.close()
    print(f"Loaded {total_trains} trains, {total_stops} stops into {DB_FILE}")


if __name__ == "__main__":
    build_database()