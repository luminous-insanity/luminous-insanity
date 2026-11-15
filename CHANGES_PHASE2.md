# Phase 2 changes (website / backend)

Everything below was written without being able to run Django here. What WAS executed:
`py_compile` of all 191 `.py` files (0 failures) and 18 pure-Python tests
(`python -m unittest accounts.test_playoff_all_active api.test_quarter_scores mobileapi.test_reminder_rules` from the project root: all pass).
NOT executed: the Django test suite, migrations, and anything needing a database or the live NFL/Firebase APIs.

## Deploy steps (PythonAnywhere)
1. Unzip over the project (this ZIP contains no `.env` and no `db.sqlite3`; yours are untouched).
2. `pip install -r requirements.txt` (adds `firebase-admin`).
3. `python manage.py migrate` (new migration `mobileapi/0004_pick_reminders`).
4. `python manage.py check` then `python manage.py test` and send me any failures.
5. Optional `.env` lines: `PLAYOFF_ALL_ACTIVE_MAX=50`, `FIREBASE_ADMIN_CREDENTIALS=/path/on/server.json`.
6. Keep the existing cron on `/api/sync/` running every 15 minutes. It now also deals squares, records quarter scores and sends the pick reminder. Nothing else needs to be run by staff.

## What changed
| Area | Change | Files |
|---|---|---|
| Playoffs | When 50 or fewer players are active, every active player qualifies; cuts keep everyone; all get squares. `PLAYOFF_ALL_ACTIVE_MAX=0` turns it off. The algorithm file `playoff_qualification.py` is untouched. | `accounts/playoff_all_active.py` (new), `accounts/django_adapter.py`, `GDP/settings.py` |
| Playoffs | Deactivated/deleted accounts no longer count toward N or take seats. | `accounts/django_adapter.py` |
| Squares | Board is dealt automatically after the last cut. Quarter 1-3 scores are recorded automatically from the NFL box score (never overwriting manual rows). Winners were already computed from scores. | `api/services.py`, `api/rules.py` |
| Reminders | Server sends one push per player per week, 2 hours before the first game day's first kickoff, only to players who have not picked all of that day's games. New table prevents duplicates. Default for new users: on. | `mobileapi/reminder_rules.py`, `reminders.py`, `models.py`, `migrations/0004_pick_reminders.py`, `management/commands/send_pick_reminders.py`, `api/services.py` |
| Account deletion | `POST /api/v1/me/delete/` and web page `/accounts/delete/` (public URL for Google Play). Anonymizes and deactivates; never changes other players' records. Link on profile page; privacy policy updated. | `accounts/account_deletion.py`, `account_views.py`, `urls.py`, `templates/accounts/delete_account.html`, `mobileapi/auth.py`, `mobileapi/urls.py`, `main/templates/main/profile.html`, `privacy.html` |
| Security | Google sign-in no longer attaches to a password account whose email is unverified (returns 409). | `mobileapi/auth.py` |
| Push | `FIREBASE_ADMIN_CREDENTIALS` setting and `firebase-admin` requirement added (were documented but never applied). | `GDP/settings.py`, `requirements.txt`, `.env.example` |
| Tests | New: `accounts/test_playoff_all_active.py`, `api/test_quarter_scores.py`, `mobileapi/test_reminder_rules.py` (pure, executed) and `mobileapi/test_account_security.py` (Django, NOT executed). | |

## Test result from your machine
Full suite: 457 tests, 456 passed, 1 error. The error was a real bug in existing code found by the new deletion test: `POST /api/v1/auth/refresh/` returned a 500 (uncaught `TokenError`) for a blacklisted/expired refresh token. Fixed in `mobileapi/auth.py` (`TokenRefreshView` now returns 401). Please re-run `python manage.py test mobileapi` to confirm.

## Known limits / decisions
* Quarter-score parsing: the Tank01 `getNFLBoxScore` field names were not verified against the live feed. Several spellings are accepted; if none match, nothing is recorded (and a warning appears in the sync report). Test with last season's game ID before the Super Bowl.
* A quarter is only recorded once it is provably complete (final, later quarter has points, or feed period is past it). This can delay a quarter's result; it can never record a partial quarter.
* Reminder rule: only the first game day of the week (Eastern calendar day). If Thursday's game kicks off later than scheduled after the reminder was sent, no second reminder is sent.
* Existing users who already have a notification-preference row keep their stored `pick_reminders` value (default was off).
* Google linking: a password account created on the website with an unverified email cannot be linked to Google until email verification exists. It can still sign in with its password.
* Deleted accounts remain on leaderboards as "deleted-<id>" so nobody else's rank changes.
* PythonAnywhere free accounts restrict outbound internet; FCM and the NFL API may be blocked until you move to paid hosting.
* Not done: N+1 query fix, shared throttle cache, Postgres, email verification / password reset.
