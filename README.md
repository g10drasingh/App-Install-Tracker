# App Install & Review Tracker

Scrapes Play Store install counts (all apps) and reviews (eSewa only) daily,
via GitHub Actions, appending to CSV files.

## How it works

### Installs (`data/app_installs.csv`)
- Fetches `installs`, `minInstalls`, `realInstalls`, `score`, and `ratings`
  for every app in the `APPS` dict.
- Long/tidy format: one row per `(date, app_id)`.
- Row is dated **yesterday** (Asia/Kathmandu time) — the 9am NPT run captures
  the previous full day's snapshot.
- Skipped if that `(date, app_id)` row already exists — safe to re-run.

### Reviews (`data/reviews_YYYY-MM.csv`)
- Only scraped for the app IDs in `REVIEW_APP_IDS` (eSewa by default — Khalti
  and eSewa Business are excluded).
- One row per review, for yesterday's date only. Paginates newest-first and
  stops once it reaches reviews older than the target date.
- Stored in a **per-month file** (e.g. `reviews_2026-07.csv`, `reviews_2026-08.csv`)
  so a new file is created automatically at the start of each month, keeping
  individual files a manageable size.
- Skipped entirely for an app/date if any row for that date already exists
  in the relevant monthly file (checked per file, so it correctly handles
  the boundary where yesterday was in the previous month).

`.github/workflows/daily-app-installs.yml` runs the script at 03:15 UTC
(= 09:00 NPT) every day, then commits everything under `data/` back to the repo.

## Setup

1. Push this repo to GitHub.
2. No secrets needed — `GITHUB_TOKEN` (auto-provided) is enough to commit
   files back, since the workflow has `contents: write` permission.
3. To add/remove apps tracked for **installs**, edit `APPS` in
   `scripts/get_installs.py`:

   ```python
   APPS = {
       "com.f1soft.esewa": "eSewa",
       "com.khalti": "Khalti",
       "com.esewa.merchant": "eSewa Business",
   }
   ```

4. To add/remove apps tracked for **reviews**, edit `REVIEW_APP_IDS`:

   ```python
   REVIEW_APP_IDS = ["com.f1soft.esewa"]
   ```

   The key is the Play Store package name (from the app's Play Store URL,
   e.g. `.../details?id=com.f1soft.esewa`).

5. To test manually: go to the **Actions** tab → **Daily App Install Count**
   → **Run workflow**.

## Local testing

```bash
pip install -r requirements.txt
python scripts/get_installs.py
```

This writes/appends to the CSVs in `data/` locally, same as the Action does.

## CSV columns

### `app_installs.csv`
| column            | meaning                                      |
|-------------------|-----------------------------------------------|
| date              | snapshot date (yesterday, Asia/Kathmandu)     |
| app_id            | Play Store package name                       |
| app_name          | app title as shown on Play Store              |
| installs_display  | rounded public figure, e.g. `10,000,000+`     |
| min_installs      | numeric lower bound of installs_display       |
| real_installs     | Google's more precise install estimate        |
| score             | average rating (out of 5)                     |
| ratings           | total number of ratings                       |

### `reviews_YYYY-MM.csv`
| column                   | meaning                                  |
|--------------------------|-------------------------------------------|
| date                     | review date (target day, Asia/Kathmandu)  |
| app_id                   | Play Store package name                   |
| review_id                | Google's unique review ID                 |
| user_name                | reviewer's display name                   |
| rating                   | star rating (1-5) given with the review   |
| thumbs_up_count          | helpful votes on the review                |
| review_created_version   | app version the reviewer had installed     |
| content                  | review text                               |
| reply_content            | developer's reply text, if any             |
| review_at                | full timestamp of the review (ISO 8601)   |

**Note:** review timestamps are whatever the Play Store reports via the
scraper and aren't guaranteed to be Nepal-time — a review posted right at a
day boundary could land in the adjacent day's bucket. Fine for day-to-day
sentiment tracking, not meant for audit-grade precision.
