# Next Features — Confidence, Narratives, Titles, Share Moments

## Confidence picks
- Optional Lean / Solid / Lock (1–3) on each pick before kickoff.
- Stored on `Pick.confidence`. Does **not** change W-L-T standings.
- Correct picks award Confidence Points equal to the level.
- Correct **Lock** on an underdog (worse win% than opponent from team records) earns +1 bonus.
- UI: chips under each open game on the picks page; underdog pills in match meta.

## Season narrative arcs
- `accounts/narrative.py` builds short storylines from real data:
  - Hot streaks (3+ / 5+ consecutive correct)
  - Playoff proximity ("N wins from a playoff spot", bubble, qualified)
  - Elite form / comeback framing
  - Active rivalries count
- Shown as a narrative rail on the Command Center dashboard.

## Unlockable titles
- Titles unlock from achievement levels (e.g. Perfectionist, On Fire, Season Champion).
- Equip one via Profile → Title. Stored on `PlayerIdentity.active_title`.
- Cosmetic only — no scoring impact.

## Share moments
- `/accounts/share/perfect/<user_id>/<season>/<week>/` — perfect week card
- `/accounts/share/challenge/<id>/` — rivalry card
- `/accounts/share/` — hub listing your perfect weeks and challenges
- Copy-link button; designed for screenshots and sharing.

## Migration
- `accounts/migrations/0015_pick_confidence_and_title.py`
  - `Pick.confidence` (nullable 1–3)
  - `PlayerIdentity.active_title`

```bash
python manage.py migrate
python manage.py collectstatic
```

## Tests to run locally
```bash
python manage.py test accounts
python manage.py check
```
Walk: make a pick with Lock confidence → dashboard narratives → unlock/equip title → open a share card.
