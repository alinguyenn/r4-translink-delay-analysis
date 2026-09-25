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
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

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

CSV_PATH = "/app/data/r4_ubc_live_log.csv"
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


class DownloadHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/download":
            if os.path.exists(CSV_PATH):
                self.send_response(200)
                self.send_header("Content-Type", "text/csv")
                self.send_header(
                    "Content-Disposition", "attachment; filename=r4_ubc_live_log.csv"
                )
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.end_headers()
                with open(CSV_PATH, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"No data collected yet.")
        else:
            # Simple status page at "/"
            row_count = 0
            if os.path.exists(CSV_PATH):
                with open(CSV_PATH) as f:
                    row_count = sum(1 for _ in f) - 1  # minus header
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.end_headers()
            msg = f"R4/UBC collector running.\nRows collected: {row_count}\nDownload: /download\n"
            self.wfile.write(msg.encode())

    def log_message(self, format, *args):
        pass  # keep deploy logs clean; collection loop already logs progress


def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), DownloadHandler)
    print(f"Web server listening on port {port}", flush=True)
    server.serve_forever()


def main():
    ensure_csv_header()
    print(f"Starting R4/UBC collector. Polling every {POLL_SECONDS}s.", flush=True)

    # Run the tiny web server in the background so it doesn't block collection
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    web_thread.start()

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
