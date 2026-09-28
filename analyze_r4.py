"""
R4 / UBC delay analysis.

Reads the collector's CSV export and prints a summary of on-time performance,
plus saves two charts (delay by hour, delay by weekday) as PNG files.

Usage:
    python analyze_r4.py path/to/r4_ubc_live_log.csv

Notes on this data (read before re-running with new data):
- Only "departing_UBC" (Bay 4) has ever shown up in a full week of live
  polling. "arriving_UBC" (Unloading Only, stop 12600) is in the *scheduled*
  GTFS data but TransLink's real-time feed has not reported updates for it.
  If that changes in future data, this script will still work -- it reports
  each direction separately, and simply won't print an "arriving_UBC"
  section if there is no data for it.
- All times are converted from UTC to America/Vancouver before grouping by
  hour or weekday.
- Some rows have blank delay values. That happens when the live feed knows
  a trip exists but hasn't attached timing info yet. This script drops
  those rows before computing delay stats (they carry no delay information).
- Some trips are polled many times as the bus approaches/loops near the
  stop. trip_id is a scheduled trip that repeats every day, so a "run" is
  a trip_id plus a >3 hour gap rule. This script collapses each run down
  to ONE row -- its LAST recorded delay -- since that is closest to the bus's actual departure
  time and least likely to be a stale early prediction. Early predictions
  in this feed have sometimes been off by 10-30 minutes and self-corrected
  over subsequent polls; using the last value avoids counting that as a
  real delay.
"""

import sys
from pathlib import Path

import pandas as pd
import matplotlib
matplotlib.use("Agg")  # no display needed, just save PNG files
import matplotlib.pyplot as plt

ON_TIME_THRESHOLD_MIN = 5  # a trip counts as "on time" if within this many minutes


def load_and_clean(csv_path):
    df = pd.read_csv(csv_path)
    # Convert from UTC to Vancouver time so "hour" and "weekday" match the
    # clock riders actually experience.
    df["collected_at"] = pd.to_datetime(df["collected_at"], utc=True).dt.tz_convert(
        "America/Vancouver"
    )
    df = df.dropna(subset=["arrival_delay_sec"]).copy()
    df["arrival_delay_sec"] = df["arrival_delay_sec"].astype(int)
    df["delay_min"] = df["arrival_delay_sec"] / 60
    return df


def one_row_per_trip(df):
    """Collapse repeated polls of the same bus run down to its last observation.

    IMPORTANT: trip_id is a *scheduled* trip, and the same trip_id runs every
    day. So grouping by trip_id alone would merge different days together.
    Instead, a new "run" starts whenever the same trip_id reappears after a
    gap of more than 3 hours since its previous poll.
    """
    df = df.sort_values(["trip_id", "collected_at"]).copy()
    gap = df.groupby("trip_id")["collected_at"].diff()
    new_run = gap.isna() | (gap > pd.Timedelta(hours=3))
    df["run_id"] = new_run.cumsum()
    return (
        df.sort_values("collected_at")
        .groupby("run_id")
        .last()
        .reset_index()
    )


def analyze_direction(df, direction, out_dir):
    sub = df[df["direction"] == direction]
    if sub.empty:
        print(f"\nNo data for direction '{direction}' in this file.")
        return

    trips = one_row_per_trip(sub)
    trips["hour"] = trips["collected_at"].dt.hour
    trips["weekday"] = trips["collected_at"].dt.day_name()
    trips["on_time"] = trips["delay_min"].abs() <= ON_TIME_THRESHOLD_MIN

    print(f"\n{'=' * 60}")
    print(f"Direction: {direction}")
    print(f"{'=' * 60}")
    print(f"Trips tracked: {len(trips)}")
    print(f"Date range: {trips['collected_at'].min()} to {trips['collected_at'].max()}")
    print(f"Median delay: {trips['delay_min'].median():.1f} min")
    print(f"Mean delay:   {trips['delay_min'].mean():.1f} min")
    print(f"On-time rate (within {ON_TIME_THRESHOLD_MIN} min): {trips['on_time'].mean() * 100:.1f}%")

    # Flag the biggest outliers so they can be sanity-checked, not just trusted blindly
    worst = trips.reindex(trips["delay_min"].abs().sort_values(ascending=False).index).head(5)
    print("\nLargest delays this period (double-check these aren't feed glitches):")
    print(worst[["collected_at", "trip_id", "delay_min"]].to_string(index=False))

    by_hour = trips.groupby("hour")["delay_min"].agg(["mean", "median", "count"])
    by_weekday = trips.groupby("weekday")["delay_min"].agg(["mean", "median", "count"])
    weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    by_weekday = by_weekday.reindex([d for d in weekday_order if d in by_weekday.index])

    print("\nBy hour of day (mean delay, min | trip count):")
    print(by_hour.round(1).to_string())
    print("\nBy weekday (mean delay, min | trip count):")
    print(by_weekday.round(1).to_string())

    # Save charts
    fig, ax = plt.subplots(figsize=(10, 4))
    by_hour["mean"].plot(kind="bar", ax=ax, color="#4C72B0")
    ax.set_title(f"R4 {direction}: Average Delay by Hour")
    ax.set_xlabel("Hour of day")
    ax.set_ylabel("Average delay (min)")
    fig.tight_layout()
    hour_path = out_dir / f"{direction}_by_hour.png"
    fig.savefig(hour_path, dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4))
    by_weekday["mean"].plot(kind="bar", ax=ax, color="#55A868")
    ax.set_title(f"R4 {direction}: Average Delay by Weekday")
    ax.set_xlabel("Weekday")
    ax.set_ylabel("Average delay (min)")
    fig.tight_layout()
    weekday_path = out_dir / f"{direction}_by_weekday.png"
    fig.savefig(weekday_path, dpi=150)
    plt.close(fig)

    print(f"\nSaved charts:\n  {hour_path}\n  {weekday_path}")


def main():
    if len(sys.argv) != 2:
        print("Usage: python analyze_r4.py path/to/r4_ubc_live_log.csv")
        sys.exit(1)

    csv_path = Path(sys.argv[1])
    if not csv_path.exists():
        print(f"File not found: {csv_path}")
        sys.exit(1)

    out_dir = Path.cwd()
    df = load_and_clean(csv_path)

    print(f"Loaded {len(df)} rows with delay data from {csv_path}")
    print(f"Overall date range: {df['collected_at'].min()} to {df['collected_at'].max()}")

    for direction in sorted(df["direction"].unique()):
        analyze_direction(df, direction, out_dir)


if __name__ == "__main__":
    main()
