# api/management/commands/sync_nfl.py
"""
Run the sync by hand:

    python manage.py sync_nfl                 # same thing the scheduler does
    python manage.py sync_nfl --through 4     # load schedule + scores for weeks 1-4
    python manage.py sync_nfl --week 3        # reload just one week

Use --through once when you start mid-season to catch up in one go
(2 API calls per week). After that the scheduler takes over.
"""
from django.core.management.base import BaseCommand, CommandError

from api.services import ApiError, MAX_WEEK, run_sync, sync_schedule, sync_scores


class Command(BaseCommand):
    help = "Sync the NFL schedule and scores."

    def add_arguments(self, parser):
        parser.add_argument("--week", type=int, help="Load schedule and scores for one week.")
        parser.add_argument("--through", type=int, help="Load schedule and scores for weeks 1..N.")

    def handle(self, *args, **options):
        week, through = options["week"], options["through"]
        if week is None and through is None:
            report = run_sync()
            self.stdout.write(str(report))
            if report["errors"]:
                raise CommandError("Finished with errors (see above).")
            return

        weeks = [week] if week is not None else list(range(1, through + 1))
        for w in weeks:
            if not 1 <= w <= MAX_WEEK:
                raise CommandError(f"Week must be 1-{MAX_WEEK}, got {w}.")
        for w in weeks:
            try:
                seen, with_kickoff = sync_schedule(w)
                finals = sync_scores(w)
            except ApiError as exc:
                raise CommandError(str(exc))
            self.stdout.write(
                f"Week {w}: {seen} games, {with_kickoff} with kickoff times, {finals} final"
            )
            if seen and with_kickoff == 0:
                self.stdout.write(self.style.WARNING(
                    "  No kickoff times came back. Picks will lock at 9:00 AM ET on game day instead."
                ))
