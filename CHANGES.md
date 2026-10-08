# Pick'em fix: install steps

Back up your project folder (including db.sqlite3) before you start.

## 1. Files
Copy the `api/`, `accounts/` and `main/` folders from this zip over the ones in your
project (same paths). Then DELETE `api/jobs.py` (it is replaced by `api/services.py`).

## 2. Secrets (.env)
Get a NEW RapidAPI key (the old one was pasted in chat and sat in jobs.py) and add:

    NFL_API_KEY=your-new-key
    SYNC_TOKEN=any-long-random-string

Make a token with:  python -c "import secrets; print(secrets.token_urlsafe(32))"

## 3. settings.py
Change:   TIME_ZONE = 'America/New_York'
Remove:   'django_apscheduler'   from INSTALLED_APPS  (no more in-app scheduler)
Add at the bottom:

    NFL_API_KEY = config('NFL_API_KEY')
    NFL_API_HOST = config('NFL_API_HOST', default='tank01-nfl-live-in-game-real-time-statistics-nfl.p.rapidapi.com')
    NFL_SEASON = config('NFL_SEASON', default=2026, cast=int)
    SYNC_TOKEN = config('SYNC_TOKEN')

## 4. Database
    python manage.py makemigrations api
    python manage.py migrate
    python manage.py check
    python manage.py test api

Old 2024 rows are kept and labelled season 2024; the site only shows the season in NFL_SEASON.

## 5. Load this season
    python manage.py sync_nfl --through N      (N = the current NFL week)

It prints, per week: games, how many have kickoff times, how many are final.
If "with kickoff times" is 0, picks lock at 9:00 AM ET on game day instead (safe, just early).

## 6. Scheduler (free)
At cron-job.org (or a GitHub Actions schedule) call this every 30 minutes, all week:

    https://YOUR-SITE/api/sync/?token=YOUR_SYNC_TOKEN

It only spends API calls when a game has started and isn't final.

## 7. Accounts
Your friends must be normal users (not superusers). The leaderboard hides superusers.
