"""
R4 Translink delay collector.
Runs forever, polling TransLink's live GTFS-Realtime feed every 60 seconds,
and appending any R4 updates at UBC (Bay 4 / Unloading Only) to a CSV file.

Reads the API key from the TRANSLINK_API_KEY environment variable
(set this in Railway's project settings, not in this file).
"""

import os
import time
import csv
from datetime import datetime, timezone

import requests
from google.transit import gtfs_realtime_pb2

API_KEY = os.environ["TRANSLINK_API_KEY"]
URL = f"https://gtfsapi.translink.ca/v3/gtfsrealtime?apikey={API_KEY}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

R4_ROUTE_ID = "37810"
BAY4_ID = "12361"       # departing UBC
UNLOADING_ID = "12600"  # arriving at UBC

CSV_PATH = "r4_ubc_live_log.csv"
POLL_SECONDS = 60  # how often to check the live feed

FIELDNAMES = [
    "collected_at", "trip_id", "route_id", "stop_id",
    "direction", "arrival_delay_sec", "departure_delay_sec"
]


def ensure_csv_header():
    if not os.path.exists(CSV_PATH):
        with open(CSV_PATH, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()


def collect_once():
    response = requests.get(URL, headers=HEADERS, timeout=30)
    response.raise_for_status()

    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(response.content)

    rows = []
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        trip = entity.trip_update.trip
        if trip.route_id != R4_ROUTE_ID:
            continue

        for update in entity.trip_update.stop_time_update:
            if update.stop_id in (BAY4_ID, UNLOADING_ID):
                direction = "departing_UBC" if update.stop_id == BAY4_ID else "arriving_UBC"
                rows.append({
                    "collected_at": datetime.now(timezone.utc).isoformat(),
                    "trip_id": trip.trip_id,
                    "route_id": trip.route_id,
                    "stop_id": update.stop_id,
                    "direction": direction,
                    "arrival_delay_sec": update.arrival.delay if update.HasField("arrival") else "",
                    "departure_delay_sec": update.departure.delay if update.HasField("departure") else "",
                })

    if rows:
        with open(CSV_PATH, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writerows(rows)

    return len(rows)


def main():
    ensure_csv_header()
    print(f"Starting R4/UBC collector. Polling every {POLL_SECONDS}s.", flush=True)

    while True:
        try:
            n = collect_once()
            print(f"{datetime.now(timezone.utc).isoformat()} - collected {n} rows", flush=True)
        except Exception as e:
            # Never let one bad request kill the whole collector
            print(f"{datetime.now(timezone.utc).isoformat()} - ERROR: {e}", flush=True)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
