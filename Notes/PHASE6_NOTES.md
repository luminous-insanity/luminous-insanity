# Phase 6 — The Playoff Race

## Added
- Division season standings now mark the playoff qualification positions and visually mark the last qualifying rank.
- The configured number of qualifiers is stored per NFL season in `PlayoffSettings`.
- Default format is four qualifiers per division when no setting exists.
- Site staff can add/edit the season's qualifier count in Django Admin under **Playoff settings**.
- Players outside the qualifying positions see how many ranks they are outside and a short list of players ahead of them.
- Pending picks are displayed separately and are not counted as losses.
- Qualification is labeled provisional until all games in the configured season have final scores. Players tied at the cutoff rank remain in contention.
- Weekly Division Wars view continues using the existing weekly standings calculation.

## Migration
Run:

```bash
python manage.py migrate
```

Then open Django Admin → Playoff settings and create a row for the current NFL season if you want to change the default of four qualifiers per division.

## Validation performed
- Python source files passed `compileall` syntax compilation.
- Django checks and automated tests could not be run in this build environment because Django is not installed here. Run `python manage.py check` and `python manage.py test` in the project's virtual environment before deploying.

## Scope
This phase adds qualification tracking only. It does not yet create elimination-bracket games or a Super Bowl championship field; those should consume the final qualification results in a later phase.
