"""Mobile API: leagues, tiebreaker, insights, matchups and chat moderation."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from api import matchups
from api.models import Game
from accounts import chat
from accounts.models import LiveChatMessage, Pick, TiebreakerPick
from accounts.test_chat import make_game as make_live_game


@override_settings(NFL_SEASON=2026)
class MobileExtrasTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user('mobileuser', password='StrongPass123!')
        self.other = User.objects.create_user('otheruser', password='StrongPass123!')
        self.client.force_authenticate(self.user)
        self.game = Game.objects.create(
            season=2026, week=1, game_id='mx-1', home_team='BUF', away_team='MIA',
            game_date=timezone.localdate() + timedelta(days=1),
            kickoff=timezone.now() + timedelta(days=1))

    # ---- leagues ------------------------------------------------------------
    def test_league_lifecycle(self):
        created = self.client.post('/api/v1/leagues/', {'name': 'Family'}, format='json')
        self.assertEqual(created.status_code, 201)
        league = created.data['league']
        self.assertTrue(league['is_owner'])

        other = APIClient()
        other.force_authenticate(self.other)
        joined = other.post('/api/v1/leagues/join/', {'code': league['invite_code']}, format='json')
        self.assertEqual(joined.status_code, 200)
        self.assertEqual(joined.data['league']['members'], 2)
        self.assertEqual(other.post('/api/v1/leagues/join/', {'code': league['invite_code']},
                                    format='json').status_code, 409)

        detail = other.get(f"/api/v1/leagues/{league['id']}/?tab=season&season=2026")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(len(detail.data['rows']), 2)

        denied = other.post(f"/api/v1/leagues/{league['id']}/action/",
                            {'action': 'rename', 'name': 'Mine now'}, format='json')
        self.assertEqual(denied.status_code, 403)
        renamed = self.client.post(f"/api/v1/leagues/{league['id']}/action/",
                                   {'action': 'rename', 'name': 'Cousins'}, format='json')
        self.assertEqual(renamed.data['league']['name'], 'Cousins')
        left = other.post(f"/api/v1/leagues/{league['id']}/action/", {'action': 'leave'}, format='json')
        self.assertEqual(left.status_code, 200)
        self.assertEqual(other.get(f"/api/v1/leagues/{league['id']}/").status_code, 404)

        bad = self.client.delete(f"/api/v1/leagues/{league['id']}/", {'confirm': 'nope'}, format='json')
        self.assertEqual(bad.status_code, 400)
        gone = self.client.delete(f"/api/v1/leagues/{league['id']}/", {'confirm': 'cousins'}, format='json')
        self.assertEqual(gone.status_code, 204)

    def test_league_input_validation(self):
        self.assertEqual(self.client.post('/api/v1/leagues/', {'name': 123}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/v1/leagues/', {'name': 'x'}, format='json').status_code, 400)
        self.assertEqual(self.client.post('/api/v1/leagues/join/', {'code': ['x']}, format='json').status_code, 400)

    # ---- tiebreaker -----------------------------------------------------------
    def test_tiebreaker_get_and_save(self):
        response = self.client.get('/api/v1/tiebreaker/?season=2026&week=1')
        self.assertEqual(response.data['tiebreaker']['game_id'], 'mx-1')
        self.assertIsNone(response.data['tiebreaker']['guess'])
        saved = self.client.post('/api/v1/tiebreaker/', {'game_id': 'mx-1', 'total_points': 47}, format='json')
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(TiebreakerPick.objects.get(user=self.user).total_points, 47)
        self.assertEqual(saved.data['tiebreaker']['guess'], 47)
        for bad in ('abc', -1, 500):
            r = self.client.post('/api/v1/tiebreaker/', {'game_id': 'mx-1', 'total_points': bad}, format='json')
            self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.post('/api/v1/tiebreaker/', {'game_id': 'nope', 'total_points': 40},
                                          format='json').status_code, 404)

    def test_tiebreaker_only_for_the_designated_game(self):
        Game.objects.create(
            season=2026, week=1, game_id='mx-late', home_team='KC', away_team='DEN',
            game_date=timezone.localdate() + timedelta(days=2),
            kickoff=timezone.now() + timedelta(days=2))
        r = self.client.post('/api/v1/tiebreaker/', {'game_id': 'mx-1', 'total_points': 40}, format='json')
        self.assertEqual(r.status_code, 400)       # mx-late is last, so it is the tiebreaker

    # ---- insights / matchups ------------------------------------------------------
    def test_insights_endpoint(self):
        r = self.client.get('/api/v1/insights/?season=2026')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['overall']['games'], 0)
        self.assertEqual(self.client.get('/api/v1/insights/?season=x').status_code, 400)

    def test_matchups_and_games_include_odds(self):
        matchups.upsert_odds(self.game, spread_home=-2.5, total_points=44)
        matchups.upsert_injury(2026, 1, 'BUF', 'Josh Example', 'questionable', position='QB')
        r = self.client.get('/api/v1/matchups/?season=2026&week=1')
        entry = r.data['games'][0]
        self.assertEqual(entry['odds']['spread_label'], 'BUF -2.5')
        self.assertEqual(entry['home_injuries'][0]['player'], 'Josh Example')
        one = self.client.get('/api/v1/games/mx-1/matchup/')
        self.assertEqual(one.data['odds']['total_points'], 44.0)
        games = self.client.get('/api/v1/games/?season=2026&week=1')
        self.assertEqual(games.data['games'][0]['odds']['favorite'], 'home')
        self.assertEqual(self.client.get('/api/v1/games/zzz/matchup/').status_code, 404)

    def test_games_without_odds_still_work(self):
        r = self.client.get('/api/v1/games/?season=2026&week=1')
        self.assertIsNone(r.data['games'][0]['odds'])

    # ---- chat moderation ------------------------------------------------------------
    def test_report_and_block(self):
        live = make_live_game('mx-live')
        line = chat.post_message(live, self.other, body='rude words')
        r = self.client.post('/api/v1/chat/report/', {'message_id': line.id, 'reason': 'harassment'}, format='json')
        self.assertEqual(r.status_code, 201)
        again = self.client.post('/api/v1/chat/report/', {'message_id': line.id, 'reason': 'harassment'}, format='json')
        self.assertEqual(again.status_code, 200)
        self.assertEqual(self.client.post('/api/v1/chat/report/', {'message_id': 'x', 'reason': 'spam'},
                                          format='json').status_code, 400)

        r = self.client.post('/api/v1/chat/blocks/', {'username': 'otheruser', 'action': 'block'}, format='json')
        self.assertEqual(r.data['blocks'][0]['kind'], 'block')
        self.assertEqual(self.client.get('/api/v1/chat/blocks/').data['blocks'][0]['username'], 'otheruser')
        poll = self.client.get('/api/v1/chat/games/mx-live/')
        self.assertEqual([m['body'] for m in poll.data['messages']], [])
        self.assertTrue(LiveChatMessage.objects.filter(pk=line.pk).exists())

    def test_filters_apply_to_app_chat(self):
        make_live_game('mx-live2')
        r = self.client.post('/api/v1/chat/games/mx-live2/',
                             {'action': 'send', 'body': 'call 555-123-4567'}, format='json')
        self.assertEqual(r.status_code, 400)
        r = self.client.post('/api/v1/chat/games/mx-live2/',
                             {'action': 'send', 'body': 'what the fuck'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['message']['body'], 'what the f***')
