# Feature wave 4 — Quests, Path to Playoffs, Week Recap, Lock countdown

## Weekly quest board
Dashboard panel with multiple side objectives for the current week:
1. **Lock the slate** — pick every game
2. **Underdog Hunter** — back underdogs
3. **Trust your gut** — mark 3+ picks Solid or Lock
4. **Throw the flag** — challenge a friend this week
5. **Hot hand** (when games are graded) — at least 3 correct

Progress bars + CTAs. Does not affect W-L-T.

## Path to playoffs
Card on the Command Center showing:
- Division rank and record
- Clinched / chasing / bubble / eliminated
- “N wins from a playoff spot” when relevant
- Link to bracket

## Week recap
`/accounts/recap/?week=N&season=YYYY`
- Record, confidence points, underdog locks
- Highlight list (correct picks / lock hits)
- Friends race for that week
- Challenges that week
- Linked from dashboard and account menu

## Lock countdown
On the picks page, games locking within 24 hours show **Locks in Xh**.

## Files
- `accounts/quests.py`
- `accounts/path_to_playoffs.py`
- `accounts/recap.py`
- `accounts/templates/accounts/week_recap.html`
- Dashboard + picks + base menu updates

No new migration.
