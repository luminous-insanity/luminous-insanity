# Dynamic Playoff Qualification – Implementation Package

Pure-Python implementation of the capacity-aware, Season-Score-based
playoff qualification algorithm designed from the GameDayPicks simulation
analysis (Claude + population simulator).

## What’s in the box

| File | Purpose |
|------|---------|
| `playoff_qualification.py` | **Core pure logic** – capacity, Season Score, seats, cascade, ties. Zero Django. |
| `django_adapter.py` | Glue that turns live `Pick` / `PlayerIdentity` / challenge data into `PlayerRecord`s and optionally writes `PlayoffEntry` rows. |
| `management_command_shadow.py` | Ready-to-drop management command for shadow-mode comparison and final lock. |
| `tests/test_playoff_qualification.py` | Unit tests covering capacity table, shrinkage, Sainte-Laguë, full pipeline, merit floor, late joiners. |

## Quick start (pure logic only)

```bash
cd playoff_qualification
python -m pytest tests/ -q          # or: python tests/test_playoff_qualification.py
```

All tests are self-contained; no database required.

## Capacity formula (the heart of the request)

```python
from playoff_qualification import playoff_field_size

E = playoff_field_size(active_n)          # λ = 1.0
E = playoff_field_size(active_n, 1.05)    # slightly larger field
```

Produces the continuous curve from the design document:

| Active N | E     | % qualify |
|----------|-------|-----------|
| 20       | 7     | 35 %      |
| 100      | 25    | 25 %      |
| 1 000    | 120   | 12 %      |
| 10 000   | 455   | 4.5 %     |
| 216 000  | 2 275 | 1.1 %     |

## Season Score

```python
from playoff_qualification import season_score

S = season_score(wins, losses, ties, available_games, league_mu, k=250)
```

- Skipped games score as coin flips → selective picking is neutralised.
- Shrinkage (`k=250`) makes late joiners competitive without a separate coverage penalty.
- Eligibility requires ≥ 125 graded picks, ≥ 80 % completion, and S ≥ median of the eligible pool.

## Seat split & cascade

- ~60 % division seats (Sainte-Laguë on Week-9 active counts, **no** fixed minimum).
- ~30 % at-large by Season Score.
- ~10 % head-to-head (gated: top-2E, ≥ 6 distinct eligible opponents, prior of 5-in-10).
- Unfilled seats roll down to the next-best by Season Score; seats can **lapse** rather than expand the field.

## Confidence as the improved tie-breaker

The sort key is:

1. Higher Season Score  
2. More graded picks  
3. **Higher confidence points** (already collected by your `confidence.py`)  
4. Sealed draw (`tiebreak_draw` already in `playoff_cuts.py`)

This replaces the original “contrarian picks” proposal with something you already store and that cannot be gamed by simply picking underdogs.

## Integration steps

1. Copy `playoff_qualification.py` into `accounts/` (or a `lib/` package).
2. Copy the contents of `django_adapter.py` into a new module or merge the functions into `accounts/playoffs.py`.
3. Drop `management_command_shadow.py` into `accounts/management/commands/shadow_playoffs.py` (adjust the import path).
4. (Optional) Add the four fields shown at the bottom of `django_adapter.py` to `PlayoffSettings` via a migration.
5. Run Season 1 in **shadow mode**:

   ```bash
   python manage.py shadow_playoffs
   ```

   Compare overlap, route fill rates, and median Season Score before ever setting `write_entries=True`.

6. When ready, freeze N after Week 9, then lock membership after Week 18 + 48 h score-correction window.

## Policy knobs (change only between seasons)

| Knob | Default | Notes |
|------|---------|-------|
| `difficulty_lambda` | 1.00 | Move ±10 % max per season; stay inside [0.8, 1.25] |
| `k_pseudo_picks` | 250 | Re-estimate by split-half prediction every season |
| `snapshot_week` | 9 | Validated on simulated data; confirm on real participation |
| 60 / 30 / 10 split | – | Pure policy; watch H2H fill rate |

Structural constants (`0.5`, `N_h=100`, exponent `0.5`, 1 % floor) should change only with a published rationale and one-season notice.

## What stays untouched

- `playoff_cuts.py` ladder and `cut_targets`
- Frozen `PlayoffEntry` design
- Super Bowl field target of 50
- Existing challenge and confidence data collection

Only the **qualification** step (who gets a `PlayoffEntry`) is replaced.

## Licence / provenance

Algorithm design derived from the simulation analysis you supplied.
Implementation written for GameDayPicks integration, October 2026.
