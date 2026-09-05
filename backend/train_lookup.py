"""this file is to view the database from the trains.db where the actual file of the sqlite code is the build_train_db.py
define the find_station_by_name() and count_trains_at_station() function to get the related data from the database."""

import sqlite3
from datetime import datetime

DB_FILE = "trains.db"

# Maps Python's weekday names to our database column names
DAY_COLUMN_MAP = {
    "Monday": "runs_mon", "Tuesday": "runs_tue", "Wednesday": "runs_wed",
    "Thursday": "runs_thu", "Friday": "runs_fri", "Saturday": "runs_sat",
    "Sunday": "runs_sun",
}


def date_to_day_column(travel_date: str) -> str:
    """'2026-09-15' -> 'runs_tue' (whatever weekday that actually is)"""
    dt = datetime.strptime(travel_date, "%Y-%m-%d")
    weekday_name = dt.strftime("%A")  # e.g. "Tuesday"
    return DAY_COLUMN_MAP[weekday_name]


def find_connecting_trains(source_station: str, destination_station: str, travel_date: str) -> list[dict]:
    """
    Find trains that stop at BOTH source_station and destination_station,
    AND actually run on the given travel_date's day of week.
    """
    day_column = date_to_day_column(travel_date)

    conn = sqlite3.connect(DB_FILE)
    # Join train_stops to itself: one row for the source stop, one for the
    # destination stop, matched on the same train_number — and only where
    # the source stop comes BEFORE the destination stop (stop_order),
    # since a train "passing through" doesn't help if it's going the
    # wrong direction for this journey.
    query = f"""
        SELECT DISTINCT t.train_number, t.train_name, t.train_class,
               s1.departure_time AS source_departure,
               s2.arrival_time AS destination_arrival
        FROM train_stops s1
        JOIN train_stops s2 ON s1.train_number = s2.train_number
        JOIN trains t ON t.train_number = s1.train_number
        WHERE s1.station_name = ?
          AND s2.station_name = ?
          AND s1.stop_order < s2.stop_order
          AND t.{day_column} = 1
    """
    rows = conn.execute(query, (source_station, destination_station)).fetchall()
    conn.close()

    return [
        {
            "train_number": r[0], "train_name": r[1], "train_class": r[2],
            "departure_time": r[3], "arrival_time": r[4],
        }
        for r in rows
    ]


# Indian cities the Railways still label by their pre-rename spelling, while
# OSM (and everyone else) uses the new one. Without this, a search for the
# OSM name "Mysuru" runs `LIKE '%MYSURU%'` and misses "MYSORE JN - MYS"
# entirely — which is how Coorg lost its nearest real railhead.
CITY_RENAMES = {
    "MYSURU": "MYSORE",
    "BENGALURU": "BANGALORE",
    "MANGALURU": "MANGALORE",
    "KOZHIKODE": "CALICUT",
    "KALABURAGI": "GULBARGA",
    "BELAGAVI": "BELGAUM",
    "SHIVAMOGGA": "SHIMOGA",
    "PUDUCHERRY": "PONDICHERRY",
    "PRAYAGRAJ": "ALLAHABAD",
    "VADODARA": "BARODA",
}
# match works in both directions (search the old OR the new name, get both)
_RENAMES_BOTH_WAYS = {**CITY_RENAMES, **{old: new for new, old in CITY_RENAMES.items()}}


def place_name_variants(name: str) -> list[str]:
    """['Mysuru'] -> ['Mysuru', 'Mysore']  (so either spelling finds the station)."""
    variants = [name]
    alias = _RENAMES_BOTH_WAYS.get(name.strip().upper())
    if alias:
        variants.append(alias.title())
    return variants


def find_station_by_name(place_name: str) -> list[dict]:
    """
    Search train_stops for station names containing the given place name.
    Returns distinct matching station names (a place might match multiple
    stations, e.g. multiple stations in the same city).
    """
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute("""
        SELECT DISTINCT station_name
        FROM train_stops
        WHERE station_name LIKE ?
    """, (f"%{place_name.upper()}%",)).fetchall()
    conn.close()

    return [r[0] for r in rows]


def count_trains_at_station(station_name: str) -> int:
    """How many distinct trains stop at this exact station name — our
    'does this station actually matter' signal."""
    conn = sqlite3.connect(DB_FILE)
    count = conn.execute("""
        SELECT COUNT(DISTINCT train_number)
        FROM train_stops
        WHERE station_name = ?
    """, (station_name,)).fetchone()[0]
    conn.close()
    return count




if __name__ == "__main__":
    matches = find_station_by_name("Guntur")
    print("Matches for 'Guntur':", matches)

    for station in matches:
        count = count_trains_at_station(station)
        print(f"  {station}: {count} trains")