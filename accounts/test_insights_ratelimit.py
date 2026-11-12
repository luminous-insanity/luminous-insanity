"""My insights, staff analytics and the web-form rate limits."""
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import caches
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from api.models import Game, GameOdds
from accounts.analytics import build_site_analytics
from accounts.insights import build_insights
from accounts.insights_rules import Bucket, best_and_worst, crowd_side, favorite_from_records, pct
from accounts.models import Pick
from accounts.ratelimit import check_rate_limit, client_ip


class InsightsRulesTests(SimpleTestCase):
    def test_pct_counts_ties_as_half(self):
        self.assertEqual(pct(1, 1, 0), 50.0)
        self.assertEqual(pct(1, 0, 2), 66.7)
        self.assertIsNone(pct(0, 0, 0))

    def test_favorite_from_records(self):
        self.assertEqual(favorite_from_records((3, 0, 0), (1, 2, 0)), 'home')
        self.assertEqual(favorite_from_records((1, 2, 0), (3, 0, 0)), 'away')
        self.assertIsNone(favorite_from_records((1, 1, 0), (1, 1, 0)))
        self.assertIsNone(favorite_from_records(None, (1, 1, 0)))

    def test_crowd_side(self):
        self.assertEqual(crowd_side(5, 2), 'home')
        self.assertIsNone(crowd_side(2, 2))
        self.assertIsNone(crowd_side(1, 1))

    def test_best_and_worst_need_enough_picks(self):
        table = {'KC': Bucket(), 'DAL': Bucket()}
        for r in ('win', 'win', 'win'):
            table['KC'].add(r)
        for r in ('loss', 'loss', 'win'):
            table['DAL'].add(r)
        best, worst = best_and_worst(table)
        self.assertEqual((best[0], worst[0]), ('KC', 'DAL'))
        self.assertEqual(best_and_worst({'X': Bucket()}), (None, None))


@override_settings(NFL_SEASON=2026)
class InsightsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('alice', 'a@example.com', 'pw')
        past = timezone.now() - timedelta(days=3)
        self.g1 = Game.objects.create(
            season=2026, week=1, game_id='in-1', home_team='KC', away_team='BUF',
            game_date=timezone.localdate(), kickoff=past, status=Game.FINAL,
            home_score=27, away_score=24)
        self.g2 = Game.objects.create(
            season=2026, week=1, game_id='in-2', home_team='DAL', away_team='NYG',
            game_date=timezone.localdate(), kickoff=past, status=Game.FINAL,
            home_score=10, away_score=17)
        GameOdds.objects.create(game=self.g1, spread_home=-3)         # KC favored

    def test_empty_season(self):
        data = build_insights(self.user, 2026)
        self.assertEqual(data['overall']['games'], 0)

    def test_buckets(self):
        Pick.objects.create(user=self.user, game=self.g1, team_picked=Pick.HOME, confidence=3)   # win, favorite
        Pick.objects.create(user=self.user, game=self.g2, team_picked=Pick.AWAY)                 # win, no line
        data = build_insights(self.user, 2026)
        self.assertEqual((data['overall']['wins'], data['overall']['losses']), (2, 0))
        self.assertEqual(data['home_vs_away']['home']['wins'], 1)
        self.assertEqual(data['home_vs_away']['away']['wins'], 1)
        self.assertEqual(data['favorite_vs_underdog']['favorite']['games'], 1)
        self.assertEqual(data['favorite_vs_underdog']['underdog']['games'], 0)
        lock = next(c for c in data['confidence'] if c['key'] == 3)
        self.assertEqual(lock['wins'], 1)
        self.assertEqual(data['weeks'][0]['week'], 1)
        self.assertTrue(data['takeaways'])               # "make a few more picks" message

    def test_page_renders(self):
        Pick.objects.create(user=self.user, game=self.g1, team_picked=Pick.AWAY)
        self.client.force_login(self.user)
        response = self.client.get(reverse('insights') + '?season=2026')
        self.assertContains(response, 'My insights')
        empty = User.objects.create_user('newbie', 'n@example.com', 'pw')
        self.client.force_login(empty)
        self.assertContains(self.client.get(reverse('insights') + '?season=2026'), 'No graded picks yet')


@override_settings(NFL_SEASON=2026)
class AnalyticsTests(TestCase):
    def test_build_counts(self):
        user = User.objects.create_user('alice', 'a@example.com', 'pw')
        User.objects.create_user('lurker', 'l@example.com', 'pw')
        game = Game.objects.create(
            season=2026, week=1, game_id='an-1', home_team='KC', away_team='BUF',
            game_date=timezone.localdate(), kickoff=timezone.now() + timedelta(days=1))
        Pick.objects.create(user=user, game=game, team_picked=Pick.HOME)
        data = build_site_analytics()
        self.assertEqual(data['totals']['players'], 2)
        self.assertEqual(data['funnel'][1]['count'], 1)
        self.assertEqual(data['weekly'][0]['players'], 1)
        self.assertEqual(len(data['signups']), 12)

    def test_staff_only(self):
        User.objects.create_user('alice', 'a@example.com', 'pw')
        self.client.login(username='alice', password='pw')
        self.assertEqual(self.client.get(reverse('site_analytics')).status_code, 302)
        User.objects.create_user('boss', 'b@example.com', 'pw', is_staff=True)
        self.client.login(username='boss', password='pw')
        self.assertContains(self.client.get(reverse('site_analytics')), 'Site analytics')


@override_settings(RATELIMIT_ENABLED=True)
class RateLimitTests(TestCase):
    def setUp(self):
        caches['ratelimit'].clear()
        self.factory = RequestFactory()

    def request(self, ip='10.0.0.1', **meta):
        return self.factory.post('/x/', REMOTE_ADDR=ip, **meta)

    def test_blocks_after_limit_and_is_per_ip(self):
        results = [check_rate_limit(self.request(), 't', 3, 60)[0] for _ in range(5)]
        self.assertEqual(results, [True, True, True, False, False])
        self.assertTrue(check_rate_limit(self.request('10.0.0.2'), 't', 3, 60)[0])

    def test_forwarded_header_uses_last_entry(self):
        request = self.request(HTTP_X_FORWARDED_FOR='6.6.6.6, 203.0.113.9')
        self.assertEqual(client_ip(request), '203.0.113.9')

    @override_settings(RATELIMIT_ENABLED=False)
    def test_can_be_switched_off(self):
        self.assertTrue(all(check_rate_limit(self.request(), 'off', 1, 60)[0] for _ in range(5)))

    def test_signup_is_limited_per_ip(self):
        statuses = [self.client.post(reverse('signup'), {}, REMOTE_ADDR='10.1.1.1').status_code
                    for _ in range(11)]
        self.assertEqual(set(statuses[:10]), {200})     # invalid form re-renders
        self.assertEqual(statuses[10], 302)             # then refused with a message

    def test_login_is_limited_per_account_even_when_ip_changes(self):
        statuses = []
        for i in range(9):
            response = self.client.post(
                reverse('login'), {'username': 'victim', 'password': 'wrong'},
                REMOTE_ADDR=f'10.2.2.{i}')
            statuses.append(response.status_code)
        self.assertEqual(set(statuses[:8]), {200})
        self.assertEqual(statuses[8], 302)

    def test_json_callers_get_429(self):
        User.objects.create_user('alice', 'a@example.com', 'pw')
        self.client.login(username='alice', password='pw')
        url = reverse('chat_report')
        last = None
        for _ in range(12):
            last = self.client.post(url, {'message_id': '1', 'reason': 'spam'})
        self.assertEqual(last.status_code, 429)
        self.assertIn('Retry-After', last)
