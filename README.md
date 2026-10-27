# R4 / UBC Bus Delay Collector

Tracks live delays for the TransLink R4 bus at UBC Exchange, using
TransLink's GTFS-Realtime feed. Runs continuously on Railway, appending
one row per observed update to a CSV on a persistent volume.

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
  a stop gets polled repeatedly (once per minute) until it leaves.
  `trip_id` is a *scheduled* trip that repeats every day, so a "run" is
  a `trip_id` plus a gap rule: a gap of more than 3 hours starts a new
  run. `analyze_r4.py` keeps each run's **last** recorded delay.
- All timestamps are converted from UTC to America/Vancouver before
  grouping by hour or weekday.
- Some early predictions in TransLink's feed have been observed 10-30
  minutes off, self-correcting over the next few polls. Using each
  run's last observation (above) avoids counting these as real delays.
- Rows with a blank delay mean the feed reported the trip but hadn't
  attached timing info yet — these are dropped before analysis.

## What I learned from doing this project

- **Persistence:** The collector originally wrote to a relative path
  (`r4_ubc_live_log.csv`), which isn't guaranteed to persist across
  container restarts. Fixed by writing to `/app/data/` (the mounted
  volume) instead. **Always verify** persistence directly (row count
  before/after a deliberate redeploy) rather than assuming a fix worked.
- **Caching:** The built-in status/download pages initially had no
  cache-control headers, which could show a stale row count in a browser.
  Fixed by adding `Cache-Control: no-store` to both routes.
- **Test assumptions against the data:** I assumed the R4 arrives at Bay 1, but the static schedule showed no R4 trip stops there; arrivals use “Unloading Only” (12600). The live feed never reports that stop, so all collected data is for departures from Bay 4 (12361).
- **Check data types when a join returns nothing:** `route_id` loaded as
  text and `stop_id` as a number, so filters matched nothing. Printing
  the dtypes found it.
- **Read the status code, not just the error:** a confusing protobuf
  "Wire format was corrupt" error was really an HTML 403 from the API
  gateway, which rejected Python's default User-Agent.
- **IDs repeat:** `trip_id` repeats every day, so grouping by it merged
  different days. A run is now a `trip_id` plus a gap of more than 3
  hours. Times are also converted from UTC to Vancouver time before
  grouping by hour and weekday. Both fixes changed earlier results.
- **Blank is not zero:** about half the feed rows have no delay value.
  They are dropped, because treating them as 0 would fake on-time buses.
- **Be careful with outliers:** one run showed a 71.9-minute delay that
  stayed frozen for 8 polls before the trip vanished from the feed. I
  could not tell a real disruption from a feed glitch, so I kept it and
  reported results with and without it.
- **Small samples:** hourly and weekday results rest on few runs (for
  example, 7pm is 48 runs), so I report them as things to watch, not
  conclusions. My first model score (ROC-AUC 0.83, from 26 late runs)
  dropped to about 0.77 with more data (35 late runs).
- **Validate models on later data:** I used time-ordered folds, not
  random splits, and compared against shuffled labels and the base rate.
- **Gaps in collection happen:** the collector was offline Oct 20 to 25
  when the hosting trial ran out. I documented the gap rather than not addressing it.

## Predictive model

`R4_delay_analysis.ipynb` (Step 10) trains logistic regression and random
forest models to predict whether a run will be more than 5 minutes late,
using hour of day, weekday and weekend only. It is tested on later weeks
(time-ordered split, no shuffling) and checked against shuffled labels.
Result: it ranks risky hours well above chance (mean ROC-AUC about 0.83),
but only 26 runs were late, so it is a ranking of riskier hours, not a
forecast for a single bus.
