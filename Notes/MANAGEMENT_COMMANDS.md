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
- **Keep**

## `accounts` — `squares`
- Build board, set Super Bowl game, enter quarter scores
- Uses current squares models/rules
- **Keep**

## `accounts` — `seed_demo`
- Creates `demo_*` users and `demo-` games only
- Requires `--yes`; supports `--clear`
- Documented as test-DB only
- **Keep** as recovery/demo tool; never run on production without a copy

No obsolete commands found that should be deleted.
