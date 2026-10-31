# Phase 8: playoff entries, weekly cuts, demo data

## What was added
- `PlayoffEntry` model + `PlayoffSettings` fields (migration `0013_playoff_entries_and_cuts.py`):
  `qualifier_percent` (0 = fixed number per division), `field_target` (50),
  `first_playoff_week` (19), `rounds_cut` (managed by the cut command).
- `accounts/playoff_cuts.py`: pure rules (cut sizes, tiebreak order). No Django.
- `accounts/playoff_rounds.py`: `open_playoffs()`, `run_cut()`, `field_standings()`.
- `manage.py manage_playoffs status|open|cut [--force] [--season N]`.
- `manage.py seed_demo --yes [--players N] [--clear]`: fake players/picks/challenges
  and fake playoff games. Run it on a COPY of your database.
- Division wildcard now uses win % x sqrt(picks / season picks).
- Standings accept `through_week`, and qualification only looks at weeks 1-18,
  so playoff games can't leak into regular-season records.

## Format
Entrants start 0-0. Cuts after Wild Card, Divisional and Conference step the field
down by an equal ratio to exactly `field_target` (e.g. 200 -> 126 -> 79 -> 50).
Cut order: playoff record (cumulative; unpicked games count as losses), regular-season
win %, head-to-head wins, then a draw stored when the field opened.

## Not done yet
- Score sync only loads regular-season games (`seasonType: "reg"`, MAX_WEEK 18), so real
  playoff games will not appear until the sync handles the postseason.
- The /playoffs/ page still shows the old single-elimination preview.
- Head-to-head wildcard spots are still a fixed number.
- The Super Bowl squares board.

## Verify locally
    python manage.py migrate
    python manage.py test
    python manage.py check
