"""Vegas odds and injury reports: labels, importing and the picks page."""
import io
import json
import tempfile
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from api import matchups
from api.models import Game, GameOdds, InjuryReport


def make_game(game_id='mu-1', week=1, home='KC', away='BUF'):
    return Game.objects.create(
        season=2026, week=week, game_id=game_id, home_team=home, away_team=away,
        game_date=timezone.localdate(), kickoff=timezone.now() + timedelta(days=2))


class OddsLabelTests(TestCase):
    def test_labels_and_favorite(self):
        game = make_game()
        odds = matchups.upsert_odds(game, spread_home=-3.5, total_points=47.0,
                                    moneyline_home=-170, moneyline_away=145)
        self.assertEqual(odds.spread_label, 'KC -3.5')
        self.assertEqual(odds.total_label, 'O/U 47')
        self.assertEqual((odds.favorite_side, odds.favorite_team), ('home', 'KC'))

        odds = matchups.upsert_odds(game, spread_home=2.5)
        self.assertEqual(odds.spread_label, 'BUF -2.5')
        self.assertEqual(odds.favorite_side, 'away')

        odds = matchups.upsert_odds(game, spread_home=0)
        self.assertEqual(odds.spread_label, "PICK'EM")
        self.assertEqual(odds.favorite_side, 'pickem')
        self.assertEqual(GameOdds.objects.filter(game=game).count(), 1)

    def test_moneyline_only_favorite(self):
        odds = matchups.upsert_odds(make_game('mu-2'), moneyline_home=130, moneyline_away=-150)
        self.assertEqual(odds.favorite_side, 'away')
        self.assertEqual(odds.spread_label, '')

    def test_bad_numbers_are_rejected(self):
        with self.assertRaises(ValueError):
            matchups.upsert_odds(make_game('mu-3'), spread_home='abc')


class InjuryTests(TestCase):
    def test_upsert_sort_and_status_aliases(self):
        matchups.upsert_injury(2026, 1, 'kc', 'Backup Guy', 'questionable')
        matchups.upsert_injury(2026, 1, 'KC', 'Star QB', 'Out', position='QB', is_key_player=True)
        matchups.upsert_injury(2026, 1, 'KC', 'Other', 'Injured Reserve')
        matchups.upsert_injury(2026, 1, 'KC', 'Star QB', 'doubtful', position='QB', is_key_player=True)
        self.assertEqual(InjuryReport.objects.count(), 3)
        names = [r.player_name for r in matchups.injuries_by_team(2026, 1)['KC']]
        self.assertEqual(names, ['Star QB', 'Other', 'Backup Guy'])     # key player first, then severity
        with self.assertRaises(ValueError):
            matchups.upsert_injury(2026, 1, 'KC', 'X', 'sore')


class ImportCommandTests(TestCase):
    def run_import(self, data, *args):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'm.json'
            path.write_text(json.dumps(data))
            call_command('import_matchups', str(path), *args,
                         stdout=io.StringIO(), stderr=io.StringIO())

    def test_imports_by_id_and_by_teams(self):
        by_id = make_game('mu-a')
        make_game('mu-b', week=2, home='DAL', away='NYG')
        self.run_import({
            'odds': [{'game_id': 'mu-a', 'spread_home': -3, 'total_points': 45.5},
                     {'season': 2026, 'week': 2, 'home': 'dal', 'away': 'nyg', 'spread_home': 1},
                     {'game_id': 'missing', 'spread_home': 1}],
            'injuries': [{'season': 2026, 'week': 1, 'team': 'KC', 'player_name': 'A', 'status': 'out'},
                         {'season': 2026, 'week': 1, 'team': 'KC', 'player_name': 'B', 'status': 'nonsense'}],
        })
        self.assertEqual(GameOdds.objects.count(), 2)
        self.assertEqual(GameOdds.objects.get(game=by_id).spread_home, Decimal('-3.0'))
        self.assertEqual(InjuryReport.objects.count(), 1)

    def test_replace_keeps_manual_rows(self):
        matchups.upsert_injury(2026, 1, 'KC', 'Imported', 'out', source='import')
        matchups.upsert_injury(2026, 1, 'KC', 'ByHand', 'out', source='manual')
        self.run_import({'injuries': [{'season': 2026, 'week': 1, 'team': 'KC',
                                       'player_name': 'Fresh', 'status': 'doubtful'}]},
                        '--replace-injuries')
        self.assertEqual(sorted(InjuryReport.objects.values_list('player_name', flat=True)),
                         ['ByHand', 'Fresh'])


@override_settings(NFL_SEASON=2026)
class PicksPageTests(TestCase):
    def test_line_and_injuries_show_on_picks_page(self):
        game = make_game('mu-p')
        matchups.upsert_odds(game, spread_home=-3.5, total_points=47.5)
        matchups.upsert_injury(2026, 1, 'KC', 'Patrick Example', 'out', position='QB')
        user = User.objects.create_user('alice', 'a@example.com', 'pw')
        self.client.force_login(user)
        with patch('accounts.views.get_team_records', return_value={}):
            response = self.client.get(reverse('picks') + '?season=2026&week=1')
        self.assertContains(response, 'KC -3.5')
        self.assertContains(response, 'O/U 47.5')
        self.assertContains(response, 'Patrick Example')

    def test_page_works_with_no_odds_or_injuries(self):
        make_game('mu-q')
        user = User.objects.create_user('alice', 'a@example.com', 'pw')
        self.client.force_login(user)
        with patch('accounts.views.get_team_records', return_value={}):
            response = self.client.get(reverse('picks') + '?season=2026&week=1')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'Injury report')
