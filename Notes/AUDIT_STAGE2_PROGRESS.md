# Audit Stage 2 Progress — Feature Verification & Indexes

## Dynamic Playoff Qualification — CONFIRMED SOUND

Verified against source:

1. **Late joiners blocked by volume, not just percentage**
   - `min_graded_picks(k)` with default k=250 → **125 graded picks minimum**
   - `MIN_COMPLETION = 0.80` (must complete ≥80% of available games from first pick week through Week 18)
   - Merit floor: Season Score must be ≥ median of the candidate pool
   - Active competitor definition also requires min weeks played + recent activity

   A player with a perfect 5–0 record from joining late does **not** qualify.

2. **Capacity-aware field size** — pure function `playoff_field_size(N)`.

3. **Adapter + shadow command** — shadow by default; `--write` only when locking.

4. **Runtime path** — `manage_playoffs open/cut` uses `PlayoffEntry` / `PlayoffSettings` / `playoff_rounds`. Newer qualification is the intended path for field selection; older simplistic logic was not restored.

5. Sample DB has no playoff rows yet (expected for a partial season / test data).

**No code change required** for correctness of the algorithm itself. Recommend running `shadow_playoffs` against a full graded season when data exists before first live `open`.

## Relay Wars — INTEGRATED CORE FEATURE

Verified:

- Mounted at `/relay-wars/`, linked from account menu in `base.html`.
- Uses existing `AUTH_USER_MODEL` and `api.models.Game` (schedule, kickoff, scores).
- Does not alter normal picks / standings / playoffs.
- Team size 4; invite + random queue; draft alternating; jinx/protection with majority vote; chain scoring.
- Views are `@login_required`; match access restricted to team members.
- Services use transactions and clear error type (`RelayWarsError`).
- Own tests module present.

Remaining verification (cannot fully exercise without live schedule + multiple users in this environment):

- End-to-end draft lock at first kickoff
- Ability vote expiry at game kickoff
- Score refresh after finals

Treat as production-capable for the implemented loops; monitor first live week closely.

## Database Performance

**Finding confirmed:** only single-column index on `Game.season`. Common filters are `(season, week)` and `(season, week, status)`.

**Change made:**
- Added `Meta.indexes` on `Game` for those two composites.
- Added migration `api/migrations/0015_game_season_week_status_idx.py`.

Safe, additive, no data change. Run `python manage.py migrate` on deploy.

## Auth / Email

- allauth is installed and URLs included under `accounts/`.
- Login methods: username + email.
- Password reset and email confirmation use allauth defaults (no custom templates found).
- SMTP configured via env.

**No code change yet.** Optional later: explicit `ACCOUNT_EMAIL_VERIFICATION = 'optional'` (or `'mandatory'`) in settings if you want a deliberate policy.

## Large views

Confirmed they already delegate heavy logic to dedicated modules. No structural split performed (avoids behaviour risk).

## Files changed in Stage 2

| File | Change |
|------|--------|
| `api/models.py` | Composite indexes on Game |
| `api/migrations/0015_game_season_week_status_idx.py` | New migration |
| `Notes/AUDIT_STAGE2_PROGRESS.md` | This note |

## Still open for later stages

- Expanded automated tests (late joiners, ties, score corrections, season finalization)
- Management command audit (seed_demo, squares, etc.)
- Documentation consolidation (many overlapping Notes/)
- Empty/loading state consistency pass
- Optional allauth email-verification policy
