# GameDayPicks Gameplay Upgrade — Phase 1

## Added: Weekly Mission card

The dashboard now opens with a weekly mission card focused on pick completion.

- Displays the current season's active NFL week (or the selected historical season's latest completed week).
- Shows the user's pick completion progress and a progress bar.
- Offers a direct link to the picks page for that specific week.
- Changes its copy and CTA when the mission is complete.
- Uses a side-quest framing and a lightweight “bragging rights” reward.
- Does not change pick grading, standings, W-L-T, challenges, or existing data.
- Responsive layout supports narrow/mobile screens.

## Why this is Phase 1

The dashboard should become a game hub with clear next actions. This small first slice adds an actionable objective and visible progress without introducing a new database model, migration, external service, or scoring rule. It is intentionally low-risk while establishing the visual language for future game mechanics.

## Verification

- Python source compiled successfully with `python -m compileall -q accounts main api GDP`.
- Django checks and automated tests could not run in this environment because Django is not installed and package installation was unavailable (network/DNS access failed).
- Run locally in the project's activated virtual environment:

  ```powershell
  python manage.py check
  python manage.py test
  ```

- Because CSS changed, run `python manage.py collectstatic` before deployment.

## Added: Weekly Friends Showdown (Phase 2)

The dashboard now includes a compact weekly race among the signed-in player and their accepted friends.

- Displays the current week's W-L-T ranking using the existing standings calculation.
- Highlights the signed-in player and their current position.
- Shows the top five friend-race rows and includes the signed-in player even if outside the top five.
- Pending picks are shown separately and are not treated as losses.
- Provides a direct link to the existing Friends-filtered weekly leaderboard.
- Shows a friend-discovery empty state for players who have not added friends.
- Adds no new models, migrations, stored score totals, or dependencies.
- Does not modify pick grading, canonical leaderboard rules, or challenge scoring.

## Verification

- Python compilation passed with `python -m compileall -q accounts main api GDP`.
- Added dashboard tests for the no-friends state and ranking among accepted friends.
- Django checks and automated tests could not run in this environment because Django is not installed and package installation was unavailable. Run locally in the project's activated virtual environment:


  ```powershell
  python manage.py check
  python manage.py test
  ```

- CSS changed; run `python manage.py collectstatic` before deployment.

## Added: Friend Pulse (Phase 3)

The picks page now reveals a friend-group read for each game after kickoff, if the signed-in player made a pick and at least one accepted friend also picked that game.

- Shows whether the player backed the friend-group majority, went against the group, or is in a split group.
- Uses only accepted friendships; pending requests and unrelated users are excluded.
- Never reveals this friend aggregate before kickoff, preserving the pre-game pick privacy rule.
- Does not alter picks, scoring, standings, or challenge rules.
- Adds no model, migration, API call, or dependency.
- Responsive styling uses the existing theme and honors the site's reduced-motion preference (no animation added).

## Verification

- Python compilation passed with `python -m compileall -q accounts main api GDP`.
- Added tests for post-kickoff reveal and pre-kickoff privacy.
- Django checks and tests could not be run in this build environment because Django is not installed here. Run locally:

  ```powershell
  python manage.py check
  python manage.py test
  ```

- CSS changed; run `collectstatic` on PythonAnywhere when deploying.
