"""
this file is to view the database from the trains.db where the actual file of the sqlite code is the build_train_db.py
"""

import sqlite3

conn = sqlite3.connect("trains.db")

print("--- Sample trains ---")
for row in conn.execute("SELECT * FROM trains LIMIT 5"):
    print(row)

print("\n--- Sample stops ---")
for row in conn.execute("SELECT * FROM train_stops LIMIT 5"):
    print(row)

conn.close()