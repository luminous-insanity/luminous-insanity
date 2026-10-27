# Head-to-head challenges, career stats, and the expanded dashboard.
#   python manage.py test accounts.test_challenges
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts import challenges as ch
from accounts.careerstats import career_stats
from accounts.models import Challenge, FriendRequest, Pick
from api.helpers_for_tests import make_final, make_game


def make_user(name):
    return User.objects.create_user(name, f"{name}@example.com", "pw-12345-xyz")


def pick(user, game, side):
    return Pick.objects.create(user=user, game=game, team_picked=side)


def ago(hours):
    return timezone.now() - timedelta(hours=hours)


def accepted(a, b, scope, game=None, week=1, season=2026):
    return Challenge.objects.create(
        challenger=a, opponent=b, scope=scope, game=game, week=week,
        season=season, status=Challenge.ACCEPTED)


@override_settings(NFL_SEASON=2026)
class CreatingChallengesTests(TestCase):
    def setUp(self):
        self.a, self.b = make_user("alice"), make_user("bob")
        self.game = make_game(week=1)                       # kicks off tomorrow

    def test_can_challenge_on_a_game_or_a_week(self):
        game_challenge = ch.create_challenge(self.a, self.b, "game", game=self.game)
        week_challenge = ch.create_challenge(self.a, self.b, "week", week=1)
        self.assertEqual(game_challenge.status, Challenge.PENDING)
        self.assertEqual(game_challenge.week, 1)
        self.assertEqual(week_challenge.scope, "week")

    def test_cannot_challenge_yourself(self):
        with self.assertRaises(ch.ChallengeError):
            ch.create_challenge(self.a, self.a, "week", week=1)

    def test_cannot_challenge_on_a_game_that_has_started(self):
        started = make_game(week=1, kickoff=ago(1))
        with self.assertRaises(ch.ChallengeError):
            ch.create_challenge(self.a, self.b, "game", game=started)

    def test_cannot_challenge_on_a_finished_week(self):
        make_final(make_game(week=2), 10, 3)
        with self.assertRaises(ch.ChallengeError):
            ch.create_challenge(self.a, self.b, "week", week=2)

    def test_no_duplicates_in_either_direction(self):
        ch.create_challenge(self.a, self.b, "week", week=1)
        with self.assertRaises(ch.ChallengeError):
            ch.create_challenge(self.a, self.b, "week", week=1)
        with self.assertRaises(ch.ChallengeError):
            ch.create_challenge(self.b, self.a, "week", week=1)

    def test_form_creates_a_challenge(self):
        self.client.force_login(self.a)
        response = self.client.post(
            reverse("challenge_new", args=[self.b.id]), {"scope": "week", "week": "1"})
        self.assertRedirects(response, reverse("challenges"))
        self.assertTrue(Challenge.objects.filter(challenger=self.a, opponent=self.b).exists())

    def test_form_shows_a_friendly_error(self):
        self.client.force_login(self.a)
        response = self.client.post(
            reverse("challenge_new", args=[self.b.id]), {"scope": "week", "week": "9"})
        self.assertContains(response, "already over or has no games")

    def test_login_required(self):
        response = self.client.get(reverse("challenge_new", args=[self.b.id]))
        self.assertEqual(response.status_code, 302)


@override_settings(NFL_SEASON=2026)
class RespondingTests(TestCase):
    def setUp(self):
        self.a, self.b, self.c = make_user("alice"), make_user("bob"), make_user("carol")
        make_game(week=1)
        self.challenge = ch.create_challenge(self.a, self.b, "week", week=1)

    def respond(self, user, action):
        self.client.force_login(user)
        self.client.post(reverse("challenge_respond", args=[self.challenge.id, action]))
        self.challenge.refresh_from_db()

    def test_opponent_can_accept(self):
        self.respond(self.b, "accept")
        self.assertEqual(self.challenge.status, Challenge.ACCEPTED)

    def test_opponent_can_decline(self):
        self.respond(self.b, "decline")
        self.assertEqual(self.challenge.status, Challenge.DECLINED)

    def test_challenger_cannot_accept_their_own_challenge(self):
        self.respond(self.a, "accept")
        self.assertEqual(self.challenge.status, Challenge.PENDING)

    def test_someone_else_cannot_respond(self):
        self.respond(self.c, "accept")
        self.assertEqual(self.challenge.status, Challenge.PENDING)

    def test_challenger_can_cancel_while_pending(self):
        self.respond(self.a, "cancel")
        self.assertEqual(self.challenge.status, Challenge.CANCELLED)

    def test_get_requests_do_nothing(self):
        self.client.force_login(self.b)
        self.client.get(reverse("challenge_respond", args=[self.challenge.id, "accept"]))
        self.challenge.refresh_from_db()
        self.assertEqual(self.challenge.status, Challenge.PENDING)

    def test_a_game_challenge_expires_once_the_game_starts(self):
        game = make_game(week=1)
        pending = ch.create_challenge(self.a, self.b, "game", game=game)
        type(game).objects.filter(pk=game.pk).update(kickoff=ago(1))
        self.assertEqual(ch.evaluate_many([pending])[pending.id].state, "expired")
        self.client.force_login(self.b)
        self.client.post(reverse("challenge_respond", args=[pending.id, "accept"]))
        pending.refresh_from_db()
        self.assertEqual(pending.status, Challenge.PENDING)


@override_settings(NFL_SEASON=2026)
class ScoringTests(TestCase):
    def setUp(self):
        self.a, self.b = make_user("alice"), make_user("bob")

    def result(self, challenge):
        return ch.evaluate_many([challenge])[challenge.id]

    def test_game_correct_pick_beats_incorrect(self):
        g = make_final(make_game(week=1), 27, 20)           # home wins
        pick(self.a, g, "home"); pick(self.b, g, "away")
        c = accepted(self.a, self.b, "game", game=g)
        result = self.result(c)
        self.assertEqual(result.state, "final")
        self.assertEqual(result.winner_id, self.a.id)
        self.assertEqual(result.outcome_for(c, self.b.id), "lost")

    def test_same_pick_is_a_tie(self):
        g = make_final(make_game(week=1), 27, 20)
        pick(self.a, g, "home"); pick(self.b, g, "home")
        result = self.result(accepted(self.a, self.b, "game", game=g))
        self.assertTrue(result.tie)

    def test_a_missing_pick_loses_to_a_correct_one(self):
        g = make_final(make_game(week=1), 27, 20)
        pick(self.b, g, "home")
        result = self.result(accepted(self.a, self.b, "game", game=g))
        self.assertEqual(result.winner_id, self.b.id)

    def test_game_not_final_is_still_open(self):
        g = make_game(week=1)
        pick(self.a, g, "home")
        result = self.result(accepted(self.a, self.b, "game", game=g))
        self.assertEqual(result.state, "open")
        self.assertIsNone(result.winner_id)

    def test_week_goes_to_the_better_record(self):
        g1 = make_final(make_game(week=1), 27, 20)
        g2 = make_final(make_game(week=1), 27, 20)
        pick(self.a, g1, "home"); pick(self.a, g2, "home")
        pick(self.b, g1, "home"); pick(self.b, g2, "away")
        c = accepted(self.a, self.b, "week")
        result = self.result(c)
        self.assertEqual((result.state, result.winner_id), ("final", self.a.id))
        self.assertEqual((result.challenger_score, result.opponent_score), ("2–0–0", "1–1–0"))

    def test_week_is_open_until_every_game_is_final(self):
        g1 = make_final(make_game(week=1), 27, 20)
        make_game(week=1)
        pick(self.a, g1, "home")
        result = self.result(accepted(self.a, self.b, "week"))
        self.assertEqual(result.state, "open")
        self.assertEqual(result.challenger_score, "1–0–0")

    def test_equal_weeks_tie(self):
        g = make_final(make_game(week=1), 27, 20)
        pick(self.a, g, "home"); pick(self.b, g, "home")
        self.assertTrue(self.result(accepted(self.a, self.b, "week")).tie)

    def test_records_and_record_between(self):
        g1 = make_final(make_game(week=1), 27, 20)
        g2 = make_final(make_game(week=2), 27, 20)
        pick(self.a, g1, "home"); pick(self.b, g1, "away")   # alice wins
        pick(self.a, g2, "away"); pick(self.b, g2, "home")   # bob wins
        accepted(self.a, self.b, "game", game=g1, week=1)
        accepted(self.b, self.a, "game", game=g2, week=2)
        accepted(self.a, self.b, "game", game=g1, week=1)    # alice wins again
        table = ch.records([self.a.id])
        self.assertEqual(table[self.a.id], [2, 1, 0])
        self.assertEqual(ch.record_between(self.a, self.b), [2, 1, 0])
        self.assertEqual(ch.record_between(self.b, self.a), [1, 2, 0])


class CareerStatsTests(TestCase):
    def setUp(self):
        self.a, self.b = make_user("alice"), make_user("bob")

    @override_settings(NFL_SEASON=2026)
    def test_weeks_won_only_counts_finished_weeks(self):
        g1 = make_final(make_game(week=1), 27, 20)
        pick(self.a, g1, "home"); pick(self.b, g1, "away")
        open_game = make_game(week=2)                         # week 2 unfinished
        done = make_final(make_game(week=2), 27, 20)
        pick(self.b, done, "home")
        stats = career_stats()
        self.assertEqual(stats[self.a.id].weeks_won, 1)
        self.assertEqual(stats[self.b.id].weeks_won, 0)

    @override_settings(NFL_SEASON=2026)
    def test_tied_for_first_both_win_the_week(self):
        g = make_final(make_game(week=1), 27, 20)
        pick(self.a, g, "home"); pick(self.b, g, "home")
        stats = career_stats()
        self.assertEqual((stats[self.a.id].weeks_won, stats[self.b.id].weeks_won), (1, 1))

    @override_settings(NFL_SEASON=2026)
    def test_seasons_won_needs_a_finalized_season(self):
        # Create a complete 18-week season with final scores.
        games = {}
        for week in range(1, 19):
            game = make_game(
                season=2025,
                week=week,
                game_id=f"CAREER-SEASON-{week}",
            )
            games[week] = make_final(game, 27, 20)

        # Alice wins the only game she picked.
        pick(self.a, games[1], "home")
        pick(self.b, games[1], "away")

        # The complete season can award its champion.
        self.assertEqual(career_stats()[self.a.id].seasons_won, 1)

        # An unfinished game means the season is no longer finalized.
        make_game(
            season=2025,
            week=2,
            game_id="CAREER-SEASON-UNFINISHED",
        )
        self.assertEqual(career_stats()[self.a.id].seasons_won, 0)

    @override_settings(NFL_SEASON=2026)
    def test_career_record_and_percentage(self):
        g1 = make_final(make_game(season=2025, week=1), 27, 20)
        g2 = make_final(make_game(week=1), 27, 20)
        pick(self.a, g1, "home"); pick(self.a, g2, "away")
        life = career_stats()[self.a.id]
        self.assertEqual((life.wins, life.losses, life.ties), (1, 1, 0))
        self.assertAlmostEqual(life.win_pct, 50.0)


@override_settings(NFL_SEASON=2026)
class DashboardAndPagesTests(TestCase):
    def setUp(self):
        self.a, self.b = make_user("alice"), make_user("bob")
        FriendRequest.objects.create(sender=self.a, receiver=self.b, status=FriendRequest.ACCEPTED)
        self.game = make_game(week=1)
        self.client.force_login(self.a)

    def test_dashboard_shows_the_expanded_stats(self):
        response = self.client.get(reverse("dashboard"))
        for label in ("Weeks won", "Seasons won", "Career win rate", "Challenges won", "Head-to-head"):
            self.assertContains(response, label)
        self.assertIn("weeks_won", response.context["my_stats"])

    def test_friends_are_tappable_and_open_the_player_menu(self):
        response = self.client.get(reverse("dashboard"))
        self.assertContains(response, "friend-menu-button")
        self.assertContains(response, "data-menu-trigger")
        self.assertContains(response, f'data-challenge-url="{reverse("challenge_new", args=[self.b.id])}"')
        self.assertContains(response, 'id="pm-challenge"')

    def test_dashboard_flags_waiting_challenges(self):
        ch.create_challenge(self.b, self.a, "week", week=1)
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.context["pending_challenges"], 1)
        self.assertContains(response, "waiting for your answer")

    def test_challenges_page_lists_incoming_with_accept_and_decline(self):
        ch.create_challenge(self.b, self.a, "week", week=1)
        response = self.client.get(reverse("challenges"))
        self.assertContains(response, "Waiting for your answer")
        self.assertContains(response, "Accept")
        self.assertContains(response, "Decline")

    def test_only_the_two_players_can_open_a_challenge(self):
        c = ch.create_challenge(self.a, self.b, "week", week=1)
        self.assertEqual(self.client.get(reverse("challenge_detail", args=[c.id])).status_code, 200)
        self.client.force_login(make_user("carol"))
        response = self.client.get(reverse("challenge_detail", args=[c.id]))
        self.assertRedirects(response, reverse("challenges"))

    def test_public_profile_shows_stats_and_a_challenge_button(self):
        response = self.client.get(reverse("player_profile", args=[self.b.id]))
        self.assertContains(response, "Weeks won")
        self.assertContains(response, "Seasons won")
        self.assertContains(response, "Challenges won")
        self.assertContains(response, reverse("challenge_new", args=[self.b.id]))

    def test_own_profile_shows_stats(self):
        response = self.client.get(reverse("profile"))
        self.assertContains(response, "Career win %")
        self.assertContains(response, "Head-to-head record")
