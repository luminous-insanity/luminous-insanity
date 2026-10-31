# Audit Stage 1 Report — Verification & First Implementations

Date: 2026-10-31

## 1. Legacy Models — VERIFIED

| Model | Runtime references | Admin only | DB rows (sample) | Verdict |
|-------|-------------------|------------|------------------|---------|
| `api.models.NFLWeek` | None (current week is computed by `api.services.current_week()` from Game rows) | Yes | 1 | Obsolete for runtime |
| `api.models.Score` | None (scores live on `Game`) | Yes | 17 | Obsolete for runtime |
| `accounts.models.UserStatistics` | None (standings derived in `accounts/standings.py`) | Yes | 2 | Obsolete for runtime |

**Actions taken**
- Removed `NFLWeek` and `Score` from `api/admin.py` registration.
- Removed `UserStatistics` from `accounts/admin.py` registration.
- Models and database tables **left intact** so historical rows are not lost and no migration is required yet.
- Comments in admin explain why.

**Not done (by design)**  
Dropping tables / creating delete migrations. That would be a later, explicit decision after confirming no external reports depend on the data.

## 2. Production Settings — IMPROVED

**Changes in `GDP/settings.py`**
- `ALLOWED_HOSTS` now environment-driven via `config(..., cast=Csv())`.
- Added `CSRF_TRUSTED_ORIGINS` (env-driven; empty by default for local).
- When `DEBUG=False`: stronger HSTS defaults (1 year, configurable), `SECURE_CONTENT_TYPE_NOSNIFF`, `SECURE_REFERRER_POLICY`, `X_FRAME_OPTIONS=DENY`.
- Structured `LOGGING` config (console, INFO in production, ERROR for `django.request`).
- All secrets remain env-only; no hardcoding.

**New files**
- `.env.example` — template without secrets.
- `Notes/PRODUCTION_CHECKLIST.md` — deploy smoke checklist.

Local development continues to work with the existing `.env` (Csv defaults include localhost).

## 3. Sync Endpoint — HARDENED (token preserved)

**Changes in `api/views.py`**
- Restricted to GET/POST via `@require_http_methods`.
- Invalid/missing token now logged at WARNING with remote IP.
- Successful and failed syncs logged (INFO / ERROR).
- Still uses `hmac.compare_digest` and the same header token.
- No application-level IP allow-list or rate limit that would risk blocking legitimate cron services (many use rotating egress). Rate control remains the external scheduler’s job.

## 4. Large Views — DEFERRED (by rule)

`accounts/views.py` (788) and `main/views.py` (560) are large but already delegate substantial logic to modules (`standings`, `leaderboard`, `achievements`, `challenges`, `path_to_playoffs`, etc.). Full extraction is not required for reliability and risks behaviour change. Will only extract if a specific bug or duplication is found later.

## 5. Incomplete Features — INITIAL VERIFICATION

### Dynamic Playoff Qualification
- Pure algorithm (`playoff_qualification.py`) includes:
  - Capacity formula
  - Season Score with shrinkage (default k=250)
  - **Minimum graded picks** = k/2 → 125 (blocks pure-record late joiners)
  - **Min completion rate** 80% from first-pick week through week 18
  - Active-competitor definition (min weeks played + recent activity)
- Django adapter + `shadow_playoffs` (shadow by default; `--write` to lock) present.
- `manage_playoffs` (open / cut / status) present and uses `PlayoffEntry` + `PlayoffSettings`.
- Sample DB: **0** PlayoffSettings rows, **0** PlayoffEntry rows (settings auto-created on first use via `get_or_create`).
- Newer system is the one wired; older logic was not restored.

### Relay Wars
- Own app, mounted at `/relay-wars/`, linked from account menu in `base.html`.
- Uses existing `User` and `api.models.Game`.
- Models: teams, members, queue, match, draft turns, picks, abilities/votes.
- Services implement invite teams, random queue (4 players), draft, jinx/protection voting, scoring.
- Views are login-required; match detail enforces team membership.
- Templates: home, join, match.
- Tests file exists (`relaywars/tests.py`).
- Appears structurally complete for core loops; needs live/end-to-end verification under real schedule data (cannot fully exercise API-dependent draft lock without games).

### Other features (status snapshot)
| Feature | Models | Views/URLs | Business logic | Notes |
|---------|--------|------------|----------------|-------|
| Achievements | Yes | Yes | Yes | Implemented; graded milestones |
| Challenges | Yes | Yes | Yes (`challenges.py`) | Present |
| Crossfire | Yes | Yes | Yes | Present |
| Confidence | — | via views | Yes | Points / board |
| Quests | — | via dashboard | Yes | Weekly quests |
| Path to Playoffs | — | dashboard | Yes | Present |
| Live reactions | Yes | Yes | Yes | Game + performance reactions |
| Squares | Yes | Yes + cmd | Yes | Super Bowl squares |

Deeper end-to-end tracing of each feature continues in Stage 2.

## 6–10. Remaining items

Still to verify/implement in subsequent stages:
- Email verification / password reset behaviour under allauth defaults
- Empty/loading states consistency
- Query patterns / indexes
- Expanded tests for late joiners, ties, score corrections
- Full management-command audit
- Documentation consolidation

## Files changed in Stage 1

| File | Change |
|------|--------|
| `api/admin.py` | Removed legacy NFLWeek/Score admin registration |
| `accounts/admin.py` | Removed UserStatistics admin registration; minor PickAdmin improvement |
| `GDP/settings.py` | Env-driven hosts/origins, stronger prod security, logging |
| `api/views.py` | Method restriction + structured sync logging |
| `.env.example` | New |
| `Notes/PRODUCTION_CHECKLIST.md` | New |
| `Notes/AUDIT_STAGE1_REPORT.md` | This report |

## Tests

- Static verification of imports/references for legacy models completed via full-project grep.
- Full Django test suite could not be re-run in this environment due to package install constraints; pure `api.test_rules` previously passed.
- **Action for you:** after pulling these changes, run locally:

```bash
python manage.py check
python manage.py migrate   # should be no-ops
python manage.py test
```

## Risk note

No models dropped, no data deleted, no URL or template behaviour intentionally changed. Settings changes are additive and env-driven; existing `.env` without the new optional keys continues to work.
