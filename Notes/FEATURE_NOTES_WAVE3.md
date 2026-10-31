# Feature wave 3 — Live energy, Underdog Hunter, Confidence board, Rivalry timeline

## Live game reactions
- New `GameReaction` model: 🔥 😱 💪 💔 🎉 on a specific game
- Reactions allowed only after kickoff
- Live energy panel on the Command Center dashboard for in-progress / recent games
- POST `/accounts/react/game/<game_id>/`

## Underdog Hunter side-quest
- Weekly objective: pick at least N underdogs (from team win%)
- Tracks dogs taken, locks, and graded underdog wins
- Card on the dashboard next to the weekly mission

## Confidence board
- Leaderboard tab **Confidence** ranks by Confidence Points (correct Lean/Solid/Lock + underdog lock bonus)
- Preview list on the dashboard among friends / self
- Does not change W-L-T standings

## Rivalry timeline
- On challenge detail: season head-to-head week results between the two players
- Series score (A wins – B wins – ties)

## Migration
```bash
python manage.py migrate   # 0016_gamereaction
python manage.py collectstatic
```

## Local smoke test
1. Start a game (or use an in-progress status) → react from dashboard
2. Pick underdogs with Lock → see Underdog Hunter progress
3. Leaderboard → Confidence tab
4. Open a challenge detail → rivalry timeline
