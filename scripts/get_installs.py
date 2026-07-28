#!/usr/bin/env python3
"""
Get Play Store install counts for one or more apps and append them to a CSV.

Designed to run daily via GitHub Actions (see .github/workflows/daily-app-installs.yml).

- Row date = "yesterday" in Asia/Kathmandu time, since a 9am NPT run is meant to
  capture the previous full day's snapshot.
- Long/tidy format: one row per (date, app_id). Easy to plot, easy to append to.
- Idempotent: if a (date, app_id) row already exists in the CSV, it's skipped
  instead of duplicated (safe to re-run / re-trigger manually).
"""

import csv
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google_play_scraper import app as gplay_app

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Map: app_id -> friendly name (friendly name is just for your own reference;
# the scraper always fetches the live title too).
APPS = {
    "com.f1soft.esewa": "eSewa",
    "com.khalti": "Khalti",
    "com.esewa.merchant": "eSewa Business",
    # Add more here, e.g.:
    # "com.swifttechnology.imepay": "IME Pay",
    # "com.mobile.smartcard": "SmartCard",
}

CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "app_installs.csv")

NEPAL_TZ = ZoneInfo("Asia/Kathmandu")

FIELDNAMES = [
    "date",
    "app_id",
    "app_name",
    "installs_display",
    "min_installs",
    "real_installs",
    "score",
    "ratings",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_target_date() -> str:
    """Yesterday's date in Nepal time, as YYYY-MM-DD."""
    now_npt = datetime.now(NEPAL_TZ)
    yesterday = now_npt - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")


def fetch_app_snapshot(app_id: str, friendly_name: str) -> dict:
    """Fetch current Play Store stats for a single app."""
    details = gplay_app(app_id, lang="en", country="np")
    return {
        "app_id": app_id,
        "app_name": details.get("title") or friendly_name,
        "installs_display": details.get("installs"),
        "min_installs": details.get("minInstalls"),
        "real_installs": details.get("realInstalls"),
        "score": details.get("score"),
        "ratings": details.get("ratings"),
    }


def load_existing_keys(csv_path: str) -> set:
    """Return set of (date, app_id) tuples already present in the CSV."""
    if not os.path.exists(csv_path):
        return set()
    keys = set()
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            keys.add((row["date"], row["app_id"]))
    return keys


def append_rows(csv_path: str, rows: list[dict]) -> None:
    """Append rows to CSV, creating it with a header if it doesn't exist yet."""
    file_exists = os.path.exists(csv_path)
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    target_date = get_target_date()
    print(f"Target date (yesterday, Asia/Kathmandu): {target_date}")

    existing_keys = load_existing_keys(CSV_PATH)

    new_rows = []
    errors = []

    for app_id, friendly_name in APPS.items():
        key = (target_date, app_id)
        if key in existing_keys:
            print(f"  skip  {app_id}: row for {target_date} already exists")
            continue
        try:
            snapshot = fetch_app_snapshot(app_id, friendly_name)
            row = {"date": target_date, **snapshot}
            new_rows.append(row)
            print(f"  ok    {app_id}: realInstalls={row['real_installs']}")
        except Exception as exc:  # noqa: BLE001 - log and continue with other apps
            errors.append((app_id, str(exc)))
            print(f"  ERROR {app_id}: {exc}", file=sys.stderr)

    if new_rows:
        append_rows(CSV_PATH, new_rows)
        print(f"Appended {len(new_rows)} row(s) to {CSV_PATH}")
    else:
        print("No new rows to append.")

    if errors:
        print(f"Completed with {len(errors)} error(s).", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
