# GameDayPicks Phase 4 — Favorite Team Identity

## Implemented
- Added `PlayerIdentity`, a one-to-one extension for a user's favorite NFL team and season-locked division snapshot.
- Added all 32 NFL teams, their division assignments, and primary/secondary color palettes.
- Added a favorite-team selector and preview to the existing Profile page.
- Added a global template context processor so a saved favorite team's palette is applied across pages through CSS variables.
- Favorite team can change at any time. Division is assigned on the first selection and remains locked for the configured season. At the next season, the division refreshes from the then-current favorite team.
- Added migration `accounts.0010_playeridentity` and profile tests for saving, theme application, same-season division lock, and next-season refresh.
- Existing scoring and standings are unchanged; this is the identity foundation for the later division/playoff system.

## Apply locally
1. Back up the project.
2. Copy the updated project files into the working project.
3. Run `python manage.py migrate` to create the new `PlayerIdentity` table.
4. Run `python manage.py check` and `python manage.py test`.
5. Test Profile on desktop and mobile, save a favorite team, then visit Dashboard, Picks, and Leaderboard to confirm the team accent follows the selection.

## Deploy
After local tests pass, push to GitHub and pull on PythonAnywhere. Run `python manage.py migrate`, then `python manage.py collectstatic`, then reload the web app.

## Verification limitation
Python syntax compilation and static team/division consistency checks pass in the build environment. Django is not installed in that environment, so Django checks and the test suite could not be run here. The migration and tests should be verified in the project's existing virtual environment before deployment.
