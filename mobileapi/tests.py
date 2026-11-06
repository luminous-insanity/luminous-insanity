from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import Game
from accounts.models import Pick, PlayerIdentity


class MobileApiCoreTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='mobileuser', password='StrongPass123!')
        self.other = User.objects.create_user(username='otheruser', password='StrongPass123!')
        self.client.force_authenticate(self.user)
        self.game = Game.objects.create(
            season=2026, week=1, game_id='mobile-test-1',
            home_team='BUF', away_team='MIA',
            game_date=timezone.localdate() + timedelta(days=1),
            kickoff=timezone.now() + timedelta(days=1),
        )

    def test_community_percentages_stay_hidden_until_player_picks(self):
        Pick.objects.create(user=self.other, game=self.game, team_picked=Pick.AWAY)
        response = self.client.get('/api/v1/games/?season=2026&week=1')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['games'][0]['community_picks'])

        response = self.client.post('/api/v1/picks/', {
            'game_id': self.game.game_id, 'side': Pick.HOME, 'confidence': 2,
        }, format='json')
        self.assertEqual(response.status_code, 201)

        response = self.client.get('/api/v1/games/?season=2026&week=1')
        community = response.data['games'][0]['community_picks']
        self.assertEqual(community['total'], 2)
        self.assertEqual(community['home_percent'], 50)
        self.assertEqual(community['away_percent'], 50)

    def test_pick_endpoint_updates_existing_pick_before_lock(self):
        url = '/api/v1/picks/'
        first = self.client.post(url, {'game_id': self.game.game_id, 'side': 'home'}, format='json')
        second = self.client.post(url, {'game_id': self.game.game_id, 'side': 'away', 'confidence': 3}, format='json')
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(Pick.objects.filter(user=self.user, game=self.game).count(), 1)
        pick = Pick.objects.get(user=self.user, game=self.game)
        self.assertEqual(pick.team_picked, Pick.AWAY)
        self.assertEqual(pick.confidence, 3)

    def test_server_rejects_pick_after_kickoff(self):
        self.game.kickoff = timezone.now() - timedelta(minutes=1)
        self.game.game_date = timezone.localdate() - timedelta(days=1)
        self.game.save(update_fields=['kickoff', 'game_date'])
        response = self.client.post('/api/v1/picks/', {
            'game_id': self.game.game_id, 'side': 'home',
        }, format='json')
        self.assertEqual(response.status_code, 409)
        self.assertFalse(Pick.objects.filter(user=self.user, game=self.game).exists())

    def test_idempotency_key_replays_friend_request_without_duplicate(self):
        headers = {'HTTP_IDEMPOTENCY_KEY': 'friend-request-test-0001'}
        first = self.client.post('/api/v1/friends/requests/', {'user_id': self.other.id}, format='json', **headers)
        second = self.client.post('/api/v1/friends/requests/', {'user_id': self.other.id}, format='json', **headers)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertEqual(first.data['id'], second.data['id'])
        self.assertEqual(self.user.sent_friend_requests.count(), 1)

    def test_password_login_returns_tokens_for_existing_website_account(self):
        anonymous = APIClient()
        response = anonymous.post('/api/v1/auth/login/', {
            'identifier': 'mobileuser', 'password': 'StrongPass123!',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)
        self.assertEqual(response.data['user']['id'], self.user.id)

    def test_favorite_team_update_uses_existing_season_division_lock(self):
        response = self.client.patch('/api/v1/me/', {'favorite_team': 'BUF'}, format='json')
        self.assertEqual(response.status_code, 200)
        identity = PlayerIdentity.objects.get(user=self.user)
        self.assertEqual(identity.favorite_team, 'BUF')
        self.assertEqual(identity.division, 'AFC East')

    def test_mobile_api_requires_authentication(self):
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/v1/me/')
        self.assertEqual(response.status_code, 401)
