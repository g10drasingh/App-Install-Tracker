# App Install Tracker

Scrapes Play Store install counts for one or more apps daily and appends
them to `data/app_installs.csv`, via GitHub Actions.

## How it works

- `scripts/get_installs.py` fetches `installs`, `minInstalls`, `realInstalls`,
  `score`, and `ratings` for each app in the `APPS` dict.
- The row is dated as **yesterday** (Asia/Kathmandu time) — the 9am NPT run
  captures the previous full day's snapshot.
- Format is long/tidy: one row per `(date, app_id)`. If that row already
  exists, it's skipped — safe to re-run.
- `.github/workflows/daily-app-installs.yml` runs the script at 03:15 UTC
  (= 09:00 NPT) every day, then commits the updated CSV back to the repo.

## Setup

1. Push this repo to GitHub.
2. No secrets needed — `GITHUB_TOKEN` (auto-provided) is enough to commit
   the CSV back, since the workflow has `contents: write` permission.
3. To add/remove apps, edit the `APPS` dict at the top of
   `scripts/get_installs.py`:

   ```python
   APPS = {
       "com.f1soft.esewa": "eSewa",
       "com.khalti": "Khalti",
       "com.esewa.merchant": "eSewa Business",
   }
   ```

   The key is the Play Store package name (from the app's Play Store URL,
   e.g. `.../details?id=com.f1soft.esewa`).

4. To test manually: go to the **Actions** tab → **Daily App Install Count**
   → **Run workflow**.

## Local testing

```bash
pip install -r requirements.txt
python scripts/get_installs.py
```

This writes/appends to `data/app_installs.csv` locally, same as the Action does.

## CSV columns

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
