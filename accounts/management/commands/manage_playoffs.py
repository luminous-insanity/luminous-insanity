"""
Run the playoffs from the command line.

    python manage.py manage_playoffs status         # where things stand
    python manage.py manage_playoffs open           # freeze the playoff field
    python manage.py manage_playoffs cut            # apply the next weekly cut
    python manage.py manage_playoffs cut --force    # cut even if games aren't final

Add --season 2026 to work on a different season (default: NFL_SEASON).
`open` and `cut` change data, so run them once the games are final.
"""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import PlayoffEntry
from accounts.playoff_cuts import cut_targets
from accounts.playoff_rounds import (
    CUTS, PlayoffError, ROUND_NAMES, field_standings, get_config, open_playoffs, run_cut,
)


class Command(BaseCommand):
    help = 'Open the playoff field, apply weekly cuts, or show the current status.'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['status', 'open', 'cut'])
        parser.add_argument('--season', type=int, default=settings.NFL_SEASON)
        parser.add_argument('--force', action='store_true',
                            help='Ignore the "season/games not final yet" safety check.')

    def handle(self, *args, **opts):
        season = opts['season']
        try:
            if opts['action'] == 'open':
                count = open_playoffs(season, force=opts['force'])
                self.stdout.write(self.style.SUCCESS(f'Opened the {season} playoffs with {count} players, all 0-0.'))
            elif opts['action'] == 'cut':
                r = run_cut(season, force=opts['force'])
                self.stdout.write(self.style.SUCCESS(
                    f"{r['round_name']} cut: {r['before']} -> {r['after']} players ({r['cut']} eliminated)."))
            self.print_status(season)
        except PlayoffError as exc:
            raise CommandError(str(exc))

    def print_status(self, season):
        config = get_config(season)
        entries = PlayoffEntry.objects.filter(season=season)
        total = entries.count()
        if not total:
            self.stdout.write(f'{season}: playoff field not open yet.')
            return
        active = entries.filter(status=PlayoffEntry.ACTIVE).count()
        targets = cut_targets(total, config.field_target, CUTS)
        self.stdout.write(f'{season}: {total} entered, {active} still active, '
                          f'{config.rounds_cut} of {CUTS} cuts done.')
        self.stdout.write('Planned field after each cut: ' + ', '.join(
            f'{ROUND_NAMES[i]} -> {n}' for i, n in enumerate(targets)))
        for row, (entry, (w, l, t)) in enumerate(field_standings(season)[:15], start=1):
            self.stdout.write(f'  {row:>3}. {entry.user.username:<18} {w}-{l}-{t}  ({entry.route})')
        if active > 15:
            self.stdout.write(f'  ... and {active - 15} more')
