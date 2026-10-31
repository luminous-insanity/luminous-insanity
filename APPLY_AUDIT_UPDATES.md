# GameDayPicks — Audit Cleanup Package

This package contains the verified cleanup and production-readiness updates from the full codebase audit (Stages 1–3).

It is an **update package**: extract into your existing project root (the folder that contains `manage.py`), allowing these files to replace the matching paths.

## What is included

### Code changes
| Path | Change |
|------|--------|
| `GDP/settings.py` | Env-driven `ALLOWED_HOSTS` / `CSRF_TRUSTED_ORIGINS`, stronger production security when `DEBUG=False`, structured logging |
| `api/admin.py` | Legacy `NFLWeek` / `Score` removed from admin (models/tables kept) |
| `api/models.py` | Composite indexes on `Game(season, week)` and `(season, week, status)` |
| `api/views.py` | Sync endpoint: method restriction + structured logging (token protection unchanged) |
| `api/migrations/0015_game_season_week_status_idx.py` | New indexes migration |
| `accounts/admin.py` | `UserStatistics` removed from admin; Pick admin shows confidence |
| `accounts/models.py` | Crossfire indexes given short explicit names |
| `accounts/migrations/0019_crossfire_short_index_names.py` | Rename Crossfire indexes |
| `accounts/test_integrity.py` | **New** tests: late joiners, score corrections, ties, season finalization, idempotent sync |
| `relaywars/tests.py` | Membership / permission tests added |

### Config & docs
| Path | Purpose |
|------|---------|
| `.env.example` | Template for environment variables (no secrets) |
| `Notes/ARCHITECTURE.md` | Current architecture |
| `Notes/FEATURE_STATUS.md` | Implemented vs partial features |
| `Notes/MANAGEMENT_COMMANDS.md` | Command audit |
| `Notes/PRODUCTION_CHECKLIST.md` | Deploy checklist |
| `Notes/AUDIT_STAGE1_REPORT.md` | Stage 1 verification |
| `Notes/AUDIT_STAGE2_PROGRESS.md` | Stage 2 feature/index work |
| `Notes/AUDIT_STAGE3_FINAL.md` | Final report and health scores |

## What is NOT included (on purpose)

- Your `.env` (secrets stay local)
- `db.sqlite3` or any user/pick/game data
- Full project rewrite — only changed/added files
- Deletion of legacy model *tables* (data preserved)

## How to apply

1. **Back up** your current project and database.
2. Extract this ZIP into your project root, preserving paths, overwriting the listed files.
3. From your activated virtualenv:

```bash
python manage.py check
python manage.py migrate
python manage.py test
```

4. On production (PythonAnywhere), ensure `.env` includes:

```text
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,GameDayPicks.pythonanywhere.com
CSRF_TRUSTED_ORIGINS=https://GameDayPicks.pythonanywhere.com
```

5. Run `python manage.py collectstatic --noinput` if static collection is part of your deploy.
6. Confirm cron still sends `X-Sync-Token` to `/api/sync/`.

## After apply

See `Notes/PRODUCTION_CHECKLIST.md` and `Notes/AUDIT_STAGE3_FINAL.md` for verification steps and remaining live-only checks (SMTP, first playoff lock, first Relay Wars week).
