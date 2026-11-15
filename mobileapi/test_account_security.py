"""Account deletion and Google-linking tests (Django; not executed by the author)."""
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from accounts.models import Pick
from api.models import Game


class AccountDeletionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user('leaver', 'leaver@example.com', 'StrongPass123!')
        self.other = User.objects.create_user('stayer', 'stayer@example.com', 'StrongPass123!')
        self.game = Game.objects.create(
            season=2026, week=1, game_id='del-1', home_team='BUF', away_team='MIA',
            game_date=timezone.localdate(), kickoff=timezone.now() - timedelta(hours=5),
            status=Game.FINAL, home_score=20, away_score=10)
        Pick.objects.create(user=self.user, game=self.game, team_picked=Pick.HOME)
        Pick.objects.create(user=self.other, game=self.game, team_picked=Pick.AWAY)
        login = self.client.post('/api/v1/auth/login/', {'identifier': 'leaver', 'password': 'StrongPass123!'}, format='json')
        self.refresh = login.data['refresh']
        self.client.credentials(HTTP_AUTHORIZATION='Bearer ' + login.data['access'])

    def test_requires_confirm_and_password(self):
        self.assertEqual(self.client.post('/api/v1/me/delete/', {}, format='json').status_code, 400)
        r = self.client.post('/api/v1/me/delete/', {'confirm': 'DELETE', 'password': 'nope'}, format='json')
        self.assertEqual(r.status_code, 403)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_delete_anonymizes_and_keeps_other_players_records(self):
        r = self.client.post('/api/v1/me/delete/', {'confirm': 'delete', 'password': 'StrongPass123!'}, format='json')
        self.assertEqual(r.status_code, 204)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)
        self.assertEqual(self.user.email, '')
        self.assertTrue(self.user.username.startswith('deleted-'))
        # Picks (and therefore everyone's standings) are untouched.
        self.assertEqual(Pick.objects.count(), 2)
        self.assertTrue(Pick.objects.filter(user=self.other).exists())
        # The old session can no longer be used.
        anon = APIClient()
        self.assertEqual(anon.post('/api/v1/auth/refresh/', {'refresh': self.refresh}, format='json').status_code, 401)
        self.assertEqual(anon.post('/api/v1/auth/login/', {'identifier': 'leaver', 'password': 'StrongPass123!'}, format='json').status_code, 401)


CLAIMS = {'email': 'victim@example.com', 'sub': 'g-123', 'email_verified': True}


@override_settings(GOOGLE_CLIENT_ID='test-client')
class GoogleLinkingTests(TestCase):
    def _login(self):
        with patch('google.oauth2.id_token.verify_oauth2_token', return_value=dict(CLAIMS)):
            return APIClient().post('/api/v1/auth/google/', {'id_token': 'x'}, format='json')

    def test_unverified_password_account_is_not_taken_over(self):
        User.objects.create_user('squatter', 'victim@example.com', 'StrongPass123!')
        self.assertEqual(self._login().status_code, 409)

    def test_new_google_user_is_created(self):
        r = self._login()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(User.objects.filter(email='victim@example.com').exists())

    def test_google_only_account_signs_in_again(self):
        self.assertEqual(self._login().status_code, 200)
        self.assertEqual(self._login().status_code, 200)
        self.assertEqual(User.objects.filter(email='victim@example.com').count(), 1)
