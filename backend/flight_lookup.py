"""
Flight lookup driven by the user's actual travel date — not a guessed
representative day. Caches per (airport, date), so asking about the
same airport+date twice never re-hits the API.
"""
import sqlite3
from build_flight_db import init_db, store_departures, DB_FILE


def _mark_checked(iata_code: str, travel_date: str) -> None:
    """Record that we've queried this (airport, date) - even if it returned
    ZERO flights. Without this, an airport with no departures (common on the
    free API tier) would be re-fetched from the paid API on every single plan."""
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS flight_checks (
            origin_iata TEXT, checked_date TEXT,
            PRIMARY KEY (origin_iata, checked_date)
        )
    """)
    conn.execute(
        "INSERT OR IGNORE INTO flight_checks (origin_iata, checked_date) VALUES (?, ?)",
        (iata_code, travel_date),
    )
    conn.commit()
    conn.close()


def _is_cached(iata_code: str, travel_date: str) -> bool:
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS flight_checks (
            origin_iata TEXT, checked_date TEXT,
            PRIMARY KEY (origin_iata, checked_date)
        )
    """)
    row = conn.execute(
        "SELECT 1 FROM flight_checks WHERE origin_iata = ? AND checked_date = ? LIMIT 1",
        (iata_code, travel_date),
    ).fetchone()
    conn.close()
    return row is not None


def get_destinations_from(
    iata_code: str, name: str, lat: float, lon: float, travel_date: str
) -> tuple[list[dict], bool]:
    """
    Return every destination this airport has scheduled flights to, ON
    THE GIVEN DATE, plus whether that answer can be trusted.

    `(destinations, data_ok)`:
      * `data_ok=True`  — we have real schedule data for this (airport, date);
        an empty list genuinely means "nothing flies from here that day".
      * `data_ok=False` — the provider was rate-limited or unreachable and we
        have nothing cached, so an empty list means "we don't know". The
        caller must say so rather than reporting "no flights".

    Fetches from the API only if this exact (airport, date) isn't cached yet.
    """
    init_db()

    data_ok = True
    if not _is_cached(iata_code, travel_date):
        # Only record the (airport, date) as checked when the fetch actually
        # succeeded. Marking a failed call would cache "no flights" forever,
        # so one exhausted-quota hour would blank this airport permanently.
        if store_departures(iata_code, name, lat, lon, travel_date):
            _mark_checked(iata_code, travel_date)
        else:
            data_ok = False

    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute("""
        SELECT DISTINCT destination_iata, destination_name
        FROM flights
        WHERE origin_iata = ? AND checked_date = ?
    """, (iata_code, travel_date)).fetchall()
    conn.close()

    # rows may still exist from an earlier successful run even if today's call
    # failed — data we already have is data we can use
    return [{"iata": r[0], "name": r[1]} for r in rows], (data_ok or bool(rows))


def find_connecting_flights(origin_iata: str, dest_iata: str, travel_date: str) -> list[dict]:
    """
    The actual flights origin -> dest on that date: number, airline, and the
    scheduled local departure / arrival times.

    Assumes get_destinations_from(origin_iata, ...) has already been called
    for this (airport, date) so the rows are in flights.db.
    """
    conn = sqlite3.connect(DB_FILE)
    rows = conn.execute("""
        SELECT DISTINCT flight_number, airline,
               scheduled_departure_local, scheduled_arrival_local
        FROM flights
        WHERE origin_iata = ? AND destination_iata = ? AND checked_date = ?
        ORDER BY scheduled_departure_local
    """, (origin_iata, dest_iata, travel_date)).fetchall()
    conn.close()

    return [
        {
            "flight_number": r[0], "airline": r[1],
            "departure_time": r[2], "arrival_time": r[3],
        }
        for r in rows
    ]


if __name__ == "__main__":
    # Simulates a user asking about a specific travel date
    destinations, ok = get_destinations_from(
        "TIR", "Tirupati Airport", 13.6326216, 79.5415119,
        travel_date="2026-09-15"
    )
    print("Tirupati flies to (on 2026-09-15):", destinations, "| data ok:", ok)