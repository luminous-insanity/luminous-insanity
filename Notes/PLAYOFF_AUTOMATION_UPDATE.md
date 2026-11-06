# Playoff Automation Update

## Playoff rules

The existing capacity-based qualification algorithm and playoff field size are unchanged. The existing `open_playoffs()` and `run_cut()` functions remain the single source of truth for freezing the field, cut timing, cut targets, standings, and tiebreakers.

The existing `/api/sync/` workflow now:

1. Automatically freezes the playoff field after all 18 regular-season weeks have all 16 games loaded and final.
2. Automatically applies the Wild Card cut after all 6 Wild Card games are loaded and final.
3. Automatically applies the Divisional cut after all 4 Divisional games are loaded and final.
4. Automatically applies the Conference cut after both Conference games are loaded and final.
5. Retries safely on later syncs when a schedule or score feed is incomplete. It records completed actions in the sync response under `playoff_actions`.

The same staff commands remain available:

```bash
python manage.py manage_playoffs status
python manage.py manage_playoffs open
python manage.py manage_playoffs cut
```

The `--force` option remains a manual override only; automation never uses it.

## Super Bowl Squares

Super Bowl Squares is a separate competition with a strict maximum of 50 participants. Everyone in the active playoff field participates when 50 or fewer remain. If more than 50 are active when the board is dealt, the existing playoff survival ranking selects the top 50 for Squares only. This does not eliminate anyone from the playoff field or change playoff qualification.

The board is still dealt by the staff `squares build` command. The 100 squares are distributed as evenly as possible among the selected participants.

## Deployment

No database migration or change to the external cron schedule is required. Deploy the updated project files normally. The existing scheduled `/api/sync/` call performs the automatic playoff processing.
