# Translink R4 UBC Bus Delay Collector

Tracks live delays for the TransLink R4 bus at UBC Exchange, using
TransLink's GTFS-Realtime feed. Runs continuously on Railway, appending
one row per observed update to a CSV on a persistent volume. 
The R4 bus at UBC is infamous for having the longest line. As a UBC student who commutes, I want to know which is the best time to get on the bus to go as it is often delayed due to traffics, huge amount of students, etc.

## Files

- **`collect_r4.py`** — the always-on collector. Polls TransLink's live
  feed every 60 seconds, filters for R4 trips at the UBC stops, and
  appends new rows to `r4_ubc_live_log.csv` on the mounted volume. Also
  runs a small built-in web server (`/` for a status check, `/download`
  to pull the current CSV).
- **`requirements.txt`** — Python packages Railway installs before running
  the collector.
- **`Procfile`** — tells Railway how to start the collector
  (`worker: python collect_r4.py`). Required because a plain script isn't
  auto-detected the way a framework app would be.
- **`analyze_r4.py`** — run this **locally** (not on Railway) against a
  downloaded CSV to get a full summary: on-time rate, delay by hour,
  delay by weekday, and saved chart images. See "Running the analysis"
  below.

## The two UBC stops

- **Bay 4** (stop_id `12361`) — where the R4 departs UBC. This is
  `direction = departing_UBC` in the data.
- **Unloading Only** (stop_id `12600`) — where the R4 arrives at UBC.
  This is `direction = arriving_UBC` in the data.

**Known limitation:** as of the first week of collection (Sep 18-25,
2026), TransLink's real-time feed has never reported an update for the
"arriving_UBC" stop, even though it exists in the static schedule. All
data collected so far is `departing_UBC` only. This may or may not
change with more data — `analyze_r4.py` will automatically start
reporting `arriving_UBC` too if/when it ever shows up.

## Running the collector (Railway)

Already deployed. To make a change:
1. Edit `collect_r4.py` on GitHub (or push from elsewhere) — commits to
   `main` auto-deploy.
2. Check the **Deployments** tab for build/deploy status.
3. Check **Console** → `wc -l /app/data/r4_ubc_live_log.csv` to confirm
   the row count didn't unexpectedly reset after any change — this
   catches volume/path issues immediately instead of silently losing
   data.

## Downloading the data

Visit `https://<your-railway-domain>/download` in a browser. If the
count on `/` (the status page) looks stale, hard-refresh
(Ctrl+Shift+R) — both routes send no-cache headers, but browsers can
still be stubborn about it.

## Running the analysis (locally)

```
pip install pandas matplotlib
python analyze_r4.py path/to/r4_ubc_live_log.csv
```

This prints a full summary to the terminal and saves two PNG charts
(delay by hour, delay by weekday) per direction, in whatever folder you
run it from.

## Data notes

- Each row is one poll of the live feed, not one bus. A single bus near
  a stop gets polled repeatedly (once per minute) until it leaves, so
  `analyze_r4.py` collapses each `trip_id` down to its **last** recorded
  delay before analyzing.
- Some early predictions in TransLink's feed have been observed 10-30
  minutes off, self-correcting over the next few polls. Using each
  trip's last observation (above) avoids counting these as real delays.
- Rows with a blank delay mean the feed reported the trip but hadn't
  attached timing info yet — these are dropped before analysis.

## Lessons learned while working on the project

- The collector originally wrote to a relative path
  (`r4_ubc_live_log.csv`), which isn't guaranteed to persist across
  container restarts. Fixed by writing to `/app/data/` (the mounted
  volume) instead. **Always verify** persistence directly (row count
  before/after a deliberate redeploy) rather than assuming a fix worked.
- The built-in status/download pages initially had no cache-control
  headers, which could show a stale row count in a browser. Fixed by
  adding `Cache-Control: no-store` to both routes.
