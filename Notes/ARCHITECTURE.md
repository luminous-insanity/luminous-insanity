# GameDayPicks Architecture

Authoritative overview of the running system (as of audit Stage 3).

## Stack

- Django 5.0.2, SQLite (PythonAnywhere-friendly)
- django-allauth (username/email + Google)
- Tank01 NFL API via RapidAPI
- Timezone: America/New_York

## Applications

| App | Responsibility |
|-----|----------------|
| `main` | Public pages: home, leaderboard, divisions, playoffs, squares, profiles, about/contact/legal |
| `accounts` | Auth views, picks, dashboard, friends, challenges, achievements, crossfire, confidence, quests, path-to-playoffs, standings, ranking, playoff qualification/rounds, squares logic |
| `api` | `Game` / `QuarterScore` models, pure `rules`, schedule/score sync, `/api/sync/` endpoint |
| `relaywars` | Team draft battles for a week; uses existing users and `Game` data |

## Core data flow

1. **Schedule/scores** → `api.services.run_sync` (idempotent) writes `Game` rows.
2. **Picks** → `accounts.models.Pick` (unique per user+game); locked after `game.has_started`.
3. **Standings** → always derived in `accounts.standings` via `grade_pick` (no stored W-L totals for ranking).
4. **Leaderboard** → `accounts.leaderboard` builds on standings + ranking rules.
5. **Playoffs** → pure qualification (`playoff_qualification.py`) + adapter; field locked into `PlayoffEntry`; weekly cuts in `playoff_rounds`.
6. **Relay Wars** → separate match/draft/ability loop; does not alter main pick standings.

## Important pure modules (easy to test)

- `api/rules.py` — status normalize, grade, lock time, current week choice
- `accounts/ranking.py` — rank keys, shared ranks, win %
- `accounts/playoff_qualification.py` — capacity, Season Score, eligibility
- `accounts/standings.py` — tally from picks + finals

## Scheduled jobs

External cron → `GET/POST /api/sync/` with header `X-Sync-Token`.  
No continuous worker required. Sync is safe to re-run.

## Management commands

| Command | Purpose | Safety |
|---------|---------|--------|
| `sync_nfl` | Manual schedule/score sync | Safe; optional `--week` / `--through` |
| `shadow_playoffs` | Run qualification (default shadow) | `--write` persists entries — use carefully |
| `manage_playoffs` | `status` / `open` / `cut` | `open`/`cut` change data; require final games unless `--force` |
| `squares` | Super Bowl board build / score entry | Admin tool |
| `seed_demo` | Fake users/games for local playoff demos | **Requires `--yes`; clear with `--clear`; never on production** |

## Legacy models (retained tables)

`api.NFLWeek`, `api.Score`, `accounts.UserStatistics` — not used at runtime. Admin registration removed. Tables kept so historical rows are not lost.

## Environment

See `.env.example` and `Notes/PRODUCTION_CHECKLIST.md`.
