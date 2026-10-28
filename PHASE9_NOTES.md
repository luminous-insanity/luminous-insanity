# Phase 9: Super Bowl squares

## What was added
- Models + migrations: `api.QuarterScore` (0014), `accounts.SquaresBoard` and `BoardSquare` (0014).
- `accounts/squares_rules.py`: pure rules (even deal, digit shuffle, winning square). No Django.
- `accounts/squares.py`: `build_board()`, `quarter_results()`, `board_grid()`.
- `manage.py squares build | game | score | status`.
- Page at `/squares/` (link in the account menu), admin screens, and quarter-score rows
  editable on each Game in admin.
- `seed_demo` now also gives its fake Super Bowl quarter scores.

## Rules
- Only players still active after the 3rd cut get squares. 50 players = 2 squares each.
  Fewer players: everyone gets the same base number (100 // players) and the leftover
  squares go to randomly chosen players (3 players = 33, 33, 34).
- Digits 0-9 are shuffled onto each axis AFTER the squares are dealt, then stored.
  An existing board is refused unless you pass --rebuild.
- Columns (top) = away team, rows (side) = home team.
- Winning square = last digit of each score. Quarters 1-3 use the running score at that
  point; "Final" uses the game's final score, overtime included.

## Automatic score filling later
Quarter scores live in `api.QuarterScore` (one row per game per quarter, with a `source`
column: "manual" or "sync"). A future sync only has to write rows with source="sync"
for the Super Bowl `Game` and set that game's final score; the page needs no changes.
The current sync only loads regular-season games, so until it handles the postseason,
create the game with `squares game` and enter scores by hand.

## Try it with fake players
    python manage.py seed_demo --yes --players 200
    (set qualifier_percent=75 in admin so more than 50 qualify)
    python manage.py manage_playoffs open --force
    python manage.py manage_playoffs cut      # three times
    python manage.py squares build
    python manage.py squares status           # then open /squares/

## Verify locally
    python manage.py migrate
    python manage.py test
    python manage.py check
