# GameDayPicks implementation notes

This source bundle implements the agreed dashboard/achievement gaps on top of the uploaded project.

## Changes

- Added a persistent `AchievementUnlock` model and migration (`accounts/migrations/0008_achievementunlock.py`). Previously earned milestones remain unlocked if later score corrections change current metrics.
- Added graded-pick-based milestones:
  - Pick Maker: 1, 10, 25, 50, 100 graded picks.
  - Week Winner: 1, 3, 5, 10, 20 completed weeks won (ties for first count).
  - Perfect Week: 1, 3, 5, 10 complete weeks where every game was picked correctly.
  - Hot Streak: 5, 10, 25 consecutive correct picks.
  - Season Veteran: graded picks in 5, 10, 18 different weeks.
  - Season Champion: 1, 3, 5 finalized seasons won (co-champions count).
- Added a compact trophy showcase to the dashboard and a full `/accounts/achievements/` page.
- Added achievement administration to Django admin.
- Updated the default season logic: explicit season selections are respected; an in-progress configured season remains the default; when the configured season has no schedule or is finalized, the latest fully completed season is selected if available.
- Tightened season finalization: all 18 regular-season weeks must be represented, and every game must have final status and both scores before a champion can be declared.
- Updated tests for full-season finalization and added achievement-focused tests.
- Updated CSS for the trophy showcase and achievement page.

## Local verification required

Python syntax compilation succeeded with `python -m compileall -q accounts main api GDP`.

Django tests could not be executed in the review environment because Django is not installed and package installation is unavailable there. Please run these from the project's activated virtual environment:

```powershell
python manage.py migrate
python manage.py test
python manage.py check
```

Because CSS changed, after the changes are tested locally and pushed, run `collectstatic` for the PythonAnywhere deployment as usual.

## Security / bundle contents

This bundle intentionally excludes `.env`, `.git`, `db.sqlite3`, virtual environments, Python bytecode caches, and generated `staticfiles`. Keep the real `.env` and local database in your own project directory.
