# Relay Wars — integrated into this GameDayPicks project

This package is integrated with the uploaded `GDP - Copy(6).zip` project.

## Changes made

- Added `relaywars` to `INSTALLED_APPS` in `GDP/settings.py`.
- Mounted `relaywars.urls` at `/relay-wars/` in `GDP/urls.py`.
- Added a Relay Wars link to the existing account dropdown in `main/templates/main/base.html`.
- Added the `relaywars` Django app and its initial migration.
- Uses the project's existing `api.models.Game` schedule, kickoff, and final-score fields.
- Uses the existing Django auth user model; does not alter normal picks, standings, playoffs, or scoring.

## Local setup

From the project directory, with its virtual environment activated:

```powershell
python manage.py migrate
python manage.py check
python manage.py test relaywars
```

## Important behavior

- Teams contain four players. Invite teams fill through invite links; random matchmaking groups four queued players. Full teams are paired when another full team is ready.
- Both sides receive the same number of draft turns: half the week's games, rounded down. The teams alternate turns. Player allocations are spread as evenly as possible; the extra turns rotate by week/team side.
- For an odd number of NFL games, one game is left undrafted so the teams still have equal selections.
- Picks are public immediately and a game can only be drafted once per matchup.
- The draft closes at the first kickoff of the week.
- Each team starts with two shared ability tokens. Each approved ability costs one token. A Jinx is limited to one per selected game. A successful Jinx (the opponent's prediction does not win) awards +1 chain point and one token. There is no artificial token cap.
- Protection pauses the chain on a loss; the next win continues it. A tie also pauses the chain because it is neither a win nor a loss.
- Ability proposals require a strict majority of currently active teammates. Voting closes at the target game's kickoff. A proposal that does not reach approval before kickoff expires without spending a token.
- A departed player's submitted picks remain attached to the team. Active teammates can continue voting and submitting missed draft turns.

## Notes

This is an additive integration. Existing project files and database were not included in this distribution archive; your local database and `.env` remain untouched when you copy these files into your working project.
