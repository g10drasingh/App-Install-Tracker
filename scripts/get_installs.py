#!/usr/bin/env python3
"""
Get Play Store install counts (all apps) and reviews (eSewa only) and append
them to CSVs. Designed to run daily via GitHub Actions
(see .github/workflows/daily-app-installs.yml).

- Row date = "yesterday" in Asia/Kathmandu time, since a 9am NPT run is meant
  to capture the previous full day's snapshot.
- Installs: long/tidy format, one row per (date, app_id), in
  data/app_installs.csv. Skipped if that (date, app_id) row already exists.
- Reviews: only scraped for the app(s) listed in REVIEW_APP_IDS (eSewa by
  default). Stored one row per review, in a per-month file
  data/reviews_YYYY-MM.csv (so a new file starts automatically each month).
  Skipped entirely for a given (date, app_id) if any row for that date
  already exists in the relevant monthly file.
"""

import csv
import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google_play_scraper import Sort
from google_play_scraper import app as gplay_app
from google_play_scraper import reviews as gplay_reviews

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

# Only these apps get their reviews scraped (installs/ratings still cover ALL of APPS above).
REVIEW_APP_IDS = ["com.f1soft.esewa"]

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
INSTALLS_CSV_PATH = os.path.join(DATA_DIR, "app_installs.csv")

NEPAL_TZ = ZoneInfo("Asia/Kathmandu")

INSTALLS_FIELDNAMES = [
    "date",
    "app_id",
    "app_name",
    "installs_display",
    "min_installs",
    "real_installs",
    "score",
    "ratings",
]

REVIEWS_FIELDNAMES = [
    "date",
    "app_id",
    "review_id",
    "user_name",
    "rating",
    "thumbs_up_count",
    "review_created_version",
    "content",
    "reply_content",
    "review_at",
]

# Safety cap on pagination when scraping reviews for a single date, in case a
# very high review volume day (or an API quirk) would otherwise loop for a
# long time. 200 reviews/page x 40 pages = 8,000 reviews/day ceiling.
MAX_REVIEW_PAGES = 40
REVIEWS_PAGE_SIZE = 200


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def get_target_date() -> str:
    """Yesterday's date in Nepal time, as YYYY-MM-DD."""
    now_npt = datetime.now(NEPAL_TZ)
    yesterday = now_npt - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")


def load_existing_dates(csv_path: str, key_fields: tuple) -> set:
    """Return set of tuples of `key_fields` values already present in the CSV."""
    if not os.path.exists(csv_path):
        return set()
    keys = set()
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            keys.add(tuple(row[field] for field in key_fields))
    return keys


def append_rows(csv_path: str, fieldnames: list, rows: list[dict]) -> None:
    """Append rows to CSV, creating it with a header if it doesn't exist yet."""
    file_exists = os.path.exists(csv_path)
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for row in rows:
            writer.writerow(row)


# ---------------------------------------------------------------------------
# Installs
# ---------------------------------------------------------------------------

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


def run_installs(target_date: str) -> int:
    """Fetch install/rating snapshots for all APPS. Returns error count."""
    print("\n=== Installs ===")
    existing_keys = load_existing_dates(INSTALLS_CSV_PATH, ("date", "app_id"))

    new_rows = []
    errors = 0

    for app_id, friendly_name in APPS.items():
        if (target_date, app_id) in existing_keys:
            print(f"  skip  {app_id}: row for {target_date} already exists")
            continue
        try:
            snapshot = fetch_app_snapshot(app_id, friendly_name)
            row = {"date": target_date, **snapshot}
            new_rows.append(row)
            print(f"  ok    {app_id}: realInstalls={row['real_installs']}")
        except Exception as exc:  # noqa: BLE001 - log and continue with other apps
            errors += 1
            print(f"  ERROR {app_id}: {exc}", file=sys.stderr)

    if new_rows:
        append_rows(INSTALLS_CSV_PATH, INSTALLS_FIELDNAMES, new_rows)
        print(f"Appended {len(new_rows)} row(s) to {INSTALLS_CSV_PATH}")
    else:
        print("No new install rows to append.")

    return errors


# ---------------------------------------------------------------------------
# Reviews
# ---------------------------------------------------------------------------

def reviews_csv_path_for(date_str: str) -> str:
    """Monthly reviews file path, e.g. data/reviews_2026-07.csv."""
    year_month = date_str[:7]  # "YYYY-MM"
    return os.path.join(DATA_DIR, f"reviews_{year_month}.csv")


def fetch_reviews_for_date(app_id: str, target_date: str) -> list[dict]:
    """
    Page through an app's reviews (newest first) and collect only the ones
    whose date matches target_date. Stops once reviews older than the target
    date start appearing.

    Note: review timestamps come from the Play Store as reported by the
    scraper and aren't guaranteed to be Nepal-time — for a review posted
    right at a day boundary the date bucket may be off by one. Good enough
    for day-to-day sentiment tracking, not meant for legal/audit precision.
    """
    target = datetime.strptime(target_date, "%Y-%m-%d").date()
    matched = []
    continuation_token = None

    for page in range(MAX_REVIEW_PAGES):
        result, continuation_token = gplay_reviews(
            app_id,
            lang="en",
            country="us",
            sort=Sort.NEWEST,
            count=REVIEWS_PAGE_SIZE,
            continuation_token=continuation_token,
        )

        if not result:
            break

        reached_older = False
        for r in result:
            review_date = r["at"].date() if r.get("at") else None
            if review_date is None:
                continue
            if review_date == target:
                matched.append(r)
            elif review_date < target:
                reached_older = True

        # Once a whole page has moved past the target date, no need to keep paging.
        if reached_older:
            break
        if continuation_token is None:
            break

    rows = []
    for r in matched:
        rows.append(
            {
                "date": target_date,
                "app_id": app_id,
                "review_id": r.get("reviewId"),
                "user_name": r.get("userName"),
                "rating": r.get("score"),
                "thumbs_up_count": r.get("thumbsUpCount"),
                "review_created_version": r.get("reviewCreatedVersion"),
                "content": r.get("content"),
                "reply_content": r.get("replyContent"),
                "review_at": r["at"].isoformat() if r.get("at") else None,
            }
        )
    return rows


def run_reviews(target_date: str) -> int:
    """Fetch reviews for REVIEW_APP_IDS for target_date. Returns error count."""
    print("\n=== Reviews ===")
    reviews_csv_path = reviews_csv_path_for(target_date)
    existing_keys = load_existing_dates(reviews_csv_path, ("date", "app_id"))

    errors = 0

    for app_id in REVIEW_APP_IDS:
        if (target_date, app_id) in existing_keys:
            print(f"  skip  {app_id}: reviews for {target_date} already exist in {reviews_csv_path}")
            continue
        try:
            rows = fetch_reviews_for_date(app_id, target_date)
            if rows:
                append_rows(reviews_csv_path, REVIEWS_FIELDNAMES, rows)
                print(f"  ok    {app_id}: appended {len(rows)} review(s) to {reviews_csv_path}")
            else:
                print(f"  ok    {app_id}: no reviews found for {target_date}")
        except Exception as exc:  # noqa: BLE001 - log and continue with other apps
            errors += 1
            print(f"  ERROR {app_id}: {exc}", file=sys.stderr)

    return errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    target_date = get_target_date()
    print(f"Target date (yesterday, Asia/Kathmandu): {target_date}")

    install_errors = run_installs(target_date)
    review_errors = run_reviews(target_date)

    total_errors = install_errors + review_errors
    if total_errors:
        print(f"\nCompleted with {total_errors} error(s).", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

