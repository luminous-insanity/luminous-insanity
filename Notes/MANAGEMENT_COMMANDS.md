# Management Commands Audit

## `api` — `sync_nfl`
- Uses current `run_sync` / `sync_schedule` / `sync_scores`
- Idempotent; safe to re-run
- Validates week range 1–MAX_WEEK
- **Keep**

## `accounts` — `shadow_playoffs`
- Calls current qualification adapter
- Default is shadow (no write); `--write` locks field
- **Keep** (primary way to preview/lock qualification)

## `accounts` — `manage_playoffs`
- `status` / `open` / `cut` against current `PlayoffEntry` + `PlayoffSettings`
- Refuses `open` if field already open; refuses unsafe cuts unless `--force`
- The normal `/api/sync/` workflow now automatically calls the same `open_playoffs()` and `run_cut()` functions once the complete regular season / playoff round is final.
- Automatic opening waits for all 18 regular-season weeks to be loaded and final; automatic cuts wait for all 6 Wild Card, 4 Divisional, or 2 Conference games to be loaded and final.
- Manual commands remain available for staff overrides and status checks.
- **Keep**

## `accounts` — `squares`
- Build board, set Super Bowl game, enter quarter scores
- Maximum 50 participants. Everyone active gets in at 50 or fewer; if more are active, the existing playoff survival ranking selects the top 50 for Squares only and does not eliminate anyone from the playoffs.
- Board dealing remains a deliberate staff command; the board is read-only to players.
- **Keep**

## `accounts` — `seed_demo`
- Creates `demo_*` users and `demo-` games only
- Requires `--yes`; supports `--clear`
- Documented as test-DB only
- **Keep** as recovery/demo tool; never run on production without a copy

No obsolete commands found that should be deleted.
