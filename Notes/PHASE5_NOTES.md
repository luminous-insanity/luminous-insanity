# GameDayPicks Phase 5 — Division Wars: Standings Preview

## What's new
- Added `/divisions/` as a first divisional competition page.
- Displays season or weekly records for players whose `PlayerIdentity` division snapshot matches the configured NFL season.
- Includes all eight NFL divisions, a division selector, weekly selector, empty state, and a visual highlight for the signed-in player.
- Added Division Wars links to desktop navigation, the mobile tab bar, and the account menu.
- Standings are calculated from existing picks and finalized game scores through `compute_standings()`; no duplicated record storage, database model, migration, or dependency was added.
- A player's division is sourced from their season-locked identity, not recalculated from their current favorite team midseason.

## Scope intentionally deferred
This is a standings foundation only. It does not yet qualify playoff players, lock non-qualifiers, reset postseason records, eliminate players, or manage the Super Bowl top-50 field. Those mechanics need explicit rules and their own tests before being enabled.

## Local verification
Run in the existing project virtual environment:

```powershell
python manage.py check
python manage.py test
```

No migration is expected for Phase 5. CSS changed, so run `collectstatic` on PythonAnywhere when deploying.

## Build-environment limitation
Python syntax compilation passed. Django is not installed in the build environment, so the Django system check and test suite could not be run here.
