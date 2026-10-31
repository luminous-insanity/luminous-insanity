# GameDayPicks Phase 7 — Road to Super Bowl 50

## What's new
- Added `/playoffs/` Championship Playoffs page and links in the account menu and mobile tab bar.
- Builds a live championship field from the existing Division Wars qualification cutoffs, capped at 50 players.
- Shows a player's current championship seed when they are in the field.
- Displays a first-round bracket preview and bye positions. For a full 50-player field, the top 14 seeds receive byes and seeds 15–50 play 18 opening-round matchups.
- Qualification remains provisional until all scheduled regular-season games are final.
- Does not invent winners, eliminate players, or declare a champion. Persisted round results and postseason scoring/tie-break rules remain a separate next implementation step.
- Preserves the existing pick records and standings calculation; no new database model or migration is required.

## Verification
- Python syntax compilation passed for project Python modules.
- Django `check` and tests could not run in the build environment because Django is not installed. Run locally in the existing project virtual environment:

```powershell
python manage.py check
python manage.py test
```

No migration is expected for this phase. Run `collectstatic` on PythonAnywhere if your deployment setup requires it.
