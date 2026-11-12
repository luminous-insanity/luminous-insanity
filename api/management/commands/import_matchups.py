"""Load Vegas odds and injury reports from a JSON file.

    python manage.py import_matchups matchups.json
    python manage.py import_matchups matchups.json --replace-injuries

File shape (both keys are optional):

{
  "odds": [
    {"game_id": "abc123", "spread_home": -3.5, "total_points": 47.5,
     "moneyline_home": -170, "moneyline_away": 145, "sportsbook": "DraftKings"},
    {"season": 2026, "week": 10, "home": "KC", "away": "BUF", "spread_home": -2.5}
  ],
  "injuries": [
    {"season": 2026, "week": 10, "team": "KC", "player_name": "Jane Doe",
     "position": "WR", "status": "questionable", "detail": "Knee", "is_key_player": true}
  ]
}

--replace-injuries first deletes previously imported injury rows for each
(season, week) found in the file, so players who were cleared drop off.
Rows typed by hand in admin (source "manual") are never deleted.
"""
import json

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from api import matchups
from api.models import InjuryReport


class Command(BaseCommand):
    help = 'Import Vegas odds and injury reports from a JSON file.'

    def add_arguments(self, parser):
        parser.add_argument('path', help='Path to the JSON file.')
        parser.add_argument(
            '--replace-injuries', action='store_true',
            help='Remove earlier imported injuries for the weeks in this file first.',
        )
        parser.add_argument('--source', default='import', help='Label stored on each row.')

    def handle(self, *args, **options):
        try:
            with open(options['path'], encoding='utf-8') as handle:
                data = json.load(handle)
        except (OSError, ValueError) as exc:
            raise CommandError(f'Could not read {options["path"]}: {exc}')
        if not isinstance(data, dict):
            raise CommandError('The file must contain a JSON object with "odds" and/or "injuries".')

        source = options['source']
        odds_done = odds_skipped = injuries_done = injuries_skipped = 0

        with transaction.atomic():
            for row in data.get('odds') or []:
                game = matchups.find_game(
                    season=row.get('season'), week=row.get('week'),
                    game_id=row.get('game_id'), home=row.get('home'), away=row.get('away'),
                )
                if game is None:
                    odds_skipped += 1
                    self.stderr.write(f'No matching game for odds row: {row}')
                    continue
                try:
                    matchups.upsert_odds(
                        game,
                        spread_home=row.get('spread_home'),
                        total_points=row.get('total_points'),
                        moneyline_home=row.get('moneyline_home'),
                        moneyline_away=row.get('moneyline_away'),
                        sportsbook=row.get('sportsbook', ''),
                        source=source,
                    )
                except ValueError as exc:
                    odds_skipped += 1
                    self.stderr.write(f'Bad odds row {row}: {exc}')
                    continue
                odds_done += 1

            injuries = data.get('injuries') or []
            if options['replace_injuries']:
                weeks = {(int(r['season']), int(r['week'])) for r in injuries
                         if r.get('season') is not None and r.get('week') is not None}
                for season, week in weeks:
                    InjuryReport.objects.filter(
                        season=season, week=week,
                    ).exclude(source='manual').delete()

            for row in injuries:
                try:
                    matchups.upsert_injury(
                        season=row['season'], week=row['week'], team=row['team'],
                        player_name=row['player_name'], status=row.get('status', ''),
                        position=row.get('position', ''), detail=row.get('detail', ''),
                        is_key_player=row.get('is_key_player', False), source=source,
                    )
                except (KeyError, ValueError) as exc:
                    injuries_skipped += 1
                    self.stderr.write(f'Bad injury row {row}: {exc}')
                    continue
                injuries_done += 1

        self.stdout.write(self.style.SUCCESS(
            f'Odds: {odds_done} saved, {odds_skipped} skipped. '
            f'Injuries: {injuries_done} saved, {injuries_skipped} skipped.'
        ))
