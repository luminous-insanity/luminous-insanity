"""The Score is Right: closest to the combined score without going over."""
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from api.models import Game
from accounts import tiebreaker
from accounts.models import Pick, TiebreakerGame, TiebreakerPick
from accounts.standings import compute_standings
from accounts.tiebreaker_rules import describe, order_group, tiebreak_key


class TiebreakerRulesTests(SimpleTestCase):
    def test_under_beats_over_even_when_over_is_closer(self):
        # Real total 44: a guess of 45 is only 1 away but went over.
        self.assertLess(tiebreak_key(40, 44), tiebreak_key(45, 44))

    def test_closest_under_wins_and_exact_is_best(self):
        self.assertLess(tiebreak_key(44, 44), tiebreak_key(43, 44))
        self.assertLess(tiebreak_key(43, 44), tiebreak_key(40, 44))

    def test_all_over_falls_back_to_closest_over(self):
        self.assertLess(tiebreak_key(45, 44), tiebreak_key(60, 44))

    def test_no_guess_is_last(self):
        self.assertLess(tiebreak_key(200, 44), tiebreak_key(None, 44))

    def test_equal_guesses_share_a_rank_offset(self):
        ordered = order_group([('a', 43), ('b', 43), ('c', 40)], 44)
        self.assertEqual([(n, off) for n, _g, off in ordered], [('a', 0), ('b', 0), ('c', 2)])

    def test_describe(self):
        self.assertIn('exactly right', describe(44, 44))
        self.assertIn('1 under', describe(43, 44))
        self.assertIn('over by 6', describe(50, 44))
        self.assertEqual(describe(None, 44), 'No guess')

    def test_parse_guess(self):
        self.assertEqual(tiebreaker.parse_guess(' 47 '), 47)
        for bad in ('', 'abc', '-3', '4.5', '201', None, True):
            with self.assertRaises(tiebreaker.TiebreakerError):
                tiebreaker.parse_guess(bad)


@override_settings(NFL_SEASON=2026)
class TiebreakerBoardTests(TestCase):
    def setUp(self):
        now = timezone.now()
        self.game1 = Game.objects.create(
            season=2026, week=1, game_id='tb-1', home_team='KC', away_team='BUF',
            game_date=timezone.localdate(), kickoff=now - timedelta(days=3),
            status=Game.FINAL, home_score=20, away_score=10)
        # The last game of the week is the tiebreaker by default. Final total = 44.
        self.game2 = Game.objects.create(
            season=2026, week=1, game_id='tb-2', home_team='DAL', away_team='NYG',
            game_date=timezone.localdate(), kickoff=now - timedelta(days=1),
            status=Game.FINAL, home_score=24, away_score=20)
        self.users = {n: User.objects.create_user(n, f'{n}@example.com', 'pw')
                      for n in ('alice', 'bob', 'cara', 'dave')}
        for user in self.users.values():           # everyone is 1-0-0 on game 1
            Pick.objects.create(user=user, game=self.game1, team_picked=Pick.HOME)

    def board(self):
        rows = compute_standings(week=1, season=2026, users=list(self.users.values()))
        rows = tiebreaker.apply_weekly_tiebreaker(rows, 2026, 1)
        return [(r.user.username, r.rank) for r in rows]

    def guess(self, name, value):
        TiebreakerPick.objects.create(user=self.users[name], game=self.game2, total_points=value)

    def test_default_game_is_last_of_week(self):
        self.assertEqual(tiebreaker.tiebreaker_game(2026, 1).pk, self.game2.pk)

    def test_staff_override_wins(self):
        TiebreakerGame.objects.create(season=2026, week=1, game=self.game1)
        self.assertEqual(tiebreaker.tiebreaker_game(2026, 1).pk, self.game1.pk)

    def test_nobody_guessed_means_shared_rank_as_before(self):
        self.assertEqual({rank for _n, rank in self.board()}, {1})

    def test_order_closest_without_going_over(self):
        self.guess('alice', 40)
        self.guess('bob', 43)
        self.guess('cara', 50)        # over
        # dave: no guess
        self.assertEqual(self.board(), [('bob', 1), ('alice', 2), ('cara', 3), ('dave', 4)])

    def test_equal_guesses_stay_tied(self):
        self.guess('alice', 43)
        self.guess('bob', 43)
        self.guess('cara', 30)
        self.assertEqual(self.board(), [('alice', 1), ('bob', 1), ('cara', 3), ('dave', 4)])

    def test_tiebreaker_never_beats_a_better_record(self):
        Pick.objects.create(user=self.users['dave'], game=self.game2, team_picked=Pick.HOME)  # dave 2-0
        self.guess('alice', 44)
        self.assertEqual(self.board()[0], ('dave', 1))

    def test_not_applied_until_tiebreaker_game_is_final(self):
        Game.objects.filter(pk=self.game2.pk).update(status=Game.LIVE)
        self.guess('alice', 44)
        self.assertEqual({rank for _n, rank in self.board()}, {1})

    def test_save_guess_locks_when_game_starts(self):
        user = self.users['alice']
        with self.assertRaises(tiebreaker.TiebreakerError) as ctx:
            tiebreaker.save_guess(user, self.game2, 45)      # already started and final
        self.assertEqual(ctx.exception.status, 403)

    def test_save_and_change_guess_before_lock(self):
        future = Game.objects.create(
            season=2026, week=2, game_id='tb-f', home_team='KC', away_team='BUF',
            game_date=timezone.localdate(), kickoff=timezone.now() + timedelta(days=2))
        user = self.users['alice']
        tiebreaker.save_guess(user, future, 41)
        tiebreaker.save_guess(user, future, 47)
        self.assertEqual(TiebreakerPick.objects.get(user=user, game=future).total_points, 47)

    def test_weekly_card(self):
        self.guess('alice', 43)
        card = tiebreaker.weekly_card(self.users['alice'], 2026, 1)
        self.assertEqual((card['guess'], card['actual'], card['locked']), (43, 44, True))
        self.assertIn('1 under', card['result'])
        self.assertIsNone(tiebreaker.weekly_card(self.users['alice'], 2026, 9))


@override_settings(NFL_SEASON=2026)
class TiebreakerViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('alice', 'a@example.com', 'pw')
        self.client.force_login(self.user)
        self.game = Game.objects.create(
            season=2026, week=3, game_id='tb-v', home_team='KC', away_team='BUF',
            game_date=timezone.localdate(), kickoff=timezone.now() + timedelta(days=2))

    def test_post_saves_guess(self):
        response = self.client.post(reverse('tiebreaker_save', args=['tb-v']), {'total_points': '48'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TiebreakerPick.objects.get(user=self.user).total_points, 48)

    def test_bad_input_is_rejected(self):
        self.client.post(reverse('tiebreaker_save', args=['tb-v']), {'total_points': 'abc'})
        self.assertFalse(TiebreakerPick.objects.exists())

    def test_picks_page_shows_card(self):
        with patch('accounts.views.get_team_records', return_value={}):
            response = self.client.get(reverse('picks') + '?season=2026&week=3')
        self.assertContains(response, 'The Score is Right')
