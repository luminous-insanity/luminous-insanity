# accounts/tests.py
#
# Run everything with:   python manage.py test
# Run only this file:    python manage.py test accounts

from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.forms import USERNAME_MAX_LENGTH, USERNAME_MIN_LENGTH, SignUpForm
from accounts.models import Pick
from accounts.standings import compute_standings, standing_for
from accounts.views import get_kickoff_label
from api.helpers_for_tests import make_final, make_game
from api.models import Game
from unittest.mock import patch

SETTINGS = dict(NFL_SEASON=2026)


def ago(hours):
    return timezone.now() - timedelta(hours=hours)


def make_user(name, superuser=False):
    if superuser:
        return User.objects.create_superuser(name, f"{name}@example.com", "pw-12345-xyz")
    return User.objects.create_user(name, f"{name}@example.com", "pw-12345-xyz")


def record(standing):
    return (standing.user.username, standing.wins, standing.losses, standing.ties)


# --------------------------------------------------------------- standings --

@override_settings(**SETTINGS)
class StandingsTests(TestCase):
    def test_wins_losses_and_ties_are_counted(self):
        alice, bob = make_user("alice"), make_user("bob")
        home_win = make_final(make_game(), 27, 20)
        away_win = make_final(make_game(), 3, 24)
        tie = make_final(make_game(), 20, 20)
        upcoming = make_game()
        for user, game, side in [
            (alice, home_win, "home"),    # win
            (alice, away_win, "home"),    # loss
            (alice, tie, "away"),         # tie
            (alice, upcoming, "home"),    # not played yet: ignored
            (bob, home_win, "away"),      # loss
            (bob, away_win, "away"),      # win
        ]:
            Pick.objects.create(user=user, game=game, team_picked=side)
        got = [record(s) for s in compute_standings()]
        self.assertEqual(got, [("alice", 1, 1, 1), ("bob", 1, 1, 0)])

    def test_ranking_is_wins_then_fewer_losses_then_name(self):
        alice, bob, carol, dave = (make_user(n) for n in ("alice", "bob", "carol", "dave"))
        games = [make_final(make_game(), 10, 3) for _ in range(3)]   # home team wins each
        Pick.objects.create(user=alice, game=games[0], team_picked="home")
        Pick.objects.create(user=alice, game=games[1], team_picked="home")   # alice 2-0
        Pick.objects.create(user=bob, game=games[0], team_picked="home")     # bob 1-0
        Pick.objects.create(user=carol, game=games[0], team_picked="home")
        Pick.objects.create(user=carol, game=games[1], team_picked="away")
        Pick.objects.create(user=carol, game=games[2], team_picked="away")   # carol 1-2
        order = [s.user.username for s in compute_standings()]
        self.assertEqual(order, ["alice", "bob", "carol", "dave"])

    def test_everyone_appears_even_with_no_picks(self):
        make_user("newbie")
        self.assertEqual([record(s) for s in compute_standings()], [("newbie", 0, 0, 0)])

    def test_admin_accounts_are_left_off_the_leaderboard(self):
        make_user("boss", superuser=True)
        make_user("friend")
        self.assertEqual([s.user.username for s in compute_standings()], ["friend"])

    def test_standing_for_works_for_any_account(self):
        boss = make_user("boss", superuser=True)
        game = make_final(make_game(), 27, 20)
        Pick.objects.create(user=boss, game=game, team_picked="home")
        self.assertEqual(record(standing_for(boss)), ("boss", 1, 0, 0))

    def test_calculating_twice_gives_the_same_answer(self):
        """The old running total double counted when the update ran twice."""
        alice = make_user("alice")
        Pick.objects.create(user=alice, game=make_final(make_game(), 27, 20), team_picked="home")
        first = [record(s) for s in compute_standings()]
        second = [record(s) for s in compute_standings()]
        self.assertEqual(first, second)
        self.assertEqual(first, [("alice", 1, 0, 0)])

    def test_a_pick_added_after_the_score_still_counts(self):
        """The old code only counted a game when its score arrived."""
        alice = make_user("alice")
        game = make_final(make_game(), 27, 20)
        self.assertEqual(record(compute_standings()[0]), ("alice", 0, 0, 0))
        Pick.objects.create(user=alice, game=game, team_picked="home")
        self.assertEqual(record(compute_standings()[0]), ("alice", 1, 0, 0))

    def test_a_corrected_score_fixes_the_record(self):
        alice = make_user("alice")
        game = make_final(make_game(), 20, 27)    # entered wrong: away wins
        Pick.objects.create(user=alice, game=game, team_picked="home")
        self.assertEqual(record(compute_standings()[0]), ("alice", 0, 1, 0))
        make_final(game, 27, 20)                  # fixed
        self.assertEqual(record(compute_standings()[0]), ("alice", 1, 0, 0))

    def test_other_seasons_do_not_count(self):
        alice = make_user("alice")
        old = make_final(make_game(season=2025), 27, 20)
        Pick.objects.create(user=alice, game=old, team_picked="home")
        self.assertEqual(record(compute_standings()[0]), ("alice", 0, 0, 0))


# --------------------------------------------------------------- dashboard --


@override_settings(**SETTINGS)
class DashboardTests(TestCase):
    def setUp(self):
        self.user = make_user("alice")
        self.client.force_login(self.user)
        self.url = reverse("dashboard")

    def test_login_is_required(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertRedirects(
            response,
            "/accounts/login/?next=/accounts/dashboard/",
            fetch_redirect_response=False,
        )

    def test_your_record_is_shown(self):
        game = make_final(make_game(), 27, 20)
        Pick.objects.create(
            user=self.user,
            game=game,
            team_picked="home",
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["user_stats"].wins, 1)
        self.assertEqual(response.context["user_stats"].losses, 0)
        self.assertContains(response, "score-cell")
        self.assertContains(response, "Wins")
        self.assertContains(response, "Losses")

    def test_dashboard_does_not_contain_pick_forms(self):
        make_game()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="team_picked"')


# ------------------------------------------------------------ kickoff label --

NOW = datetime(2026, 10, 11, 10, 0, tzinfo=ZoneInfo("America/New_York"))   # Sunday 10:00 AM Eastern


def kick(days=0, hour=13, minute=0):
    return (NOW + timedelta(days=days)).replace(hour=hour, minute=minute)


@override_settings(TIME_ZONE="America/New_York")
class KickoffLabelTests(TestCase):
    """The text in the top bar of each game card."""

    def label(self, **overrides):
        game = make_game(**overrides)
        with patch("django.utils.timezone.now", return_value=NOW):
            return get_kickoff_label(game)

    def test_later_today(self):
        self.assertEqual(self.label(kickoff=kick(0, 13)), "TODAY · 1:00 PM")

    def test_just_before_midnight_is_still_today(self):
        self.assertEqual(self.label(kickoff=kick(0, 23, 30)), "TODAY · 11:30 PM")

    def test_tomorrow(self):
        self.assertEqual(self.label(kickoff=kick(1, 13)), "TOMORROW · 1:00 PM")

    def test_later_this_week(self):
        self.assertEqual(self.label(kickoff=kick(3, 20, 15)), "Wed, Oct 14 · 8:15 PM")

    def test_single_digit_day_has_no_leading_zero(self):
        kickoff = datetime(2026, 11, 5, 13, 0, tzinfo=ZoneInfo("America/New_York"))
        self.assertEqual(self.label(kickoff=kickoff), "Thu, Nov 5 · 1:00 PM")

    def test_started_but_not_final_says_in_progress(self):
        self.assertEqual(self.label(kickoff=kick(0, 9)), "IN PROGRESS")

    def test_live_status_says_in_progress(self):
        self.assertEqual(self.label(status=Game.LIVE, kickoff=kick(0, 9)), "IN PROGRESS")

    def test_final(self):
        label = self.label(status=Game.FINAL, home_score=27, away_score=20, kickoff=kick(-1, 13))
        self.assertEqual(label, "FINAL")

    def test_no_kickoff_time(self):
        self.assertEqual(self.label(kickoff=None), "TIME TBD")


# --------------------------------------------------------------- make_pick --

@override_settings(**SETTINGS)
class MakePickTests(TestCase):
    def setUp(self):
        self.user = make_user("alice")
        self.client.force_login(self.user)

    def pick_url(self, game):
        return reverse("make_pick", args=[game.game_id])

    def test_saves_a_pick_for_the_logged_in_user(self):
        game = make_game()
        response = self.client.post(self.pick_url(game), {"team_picked": "home"})
        self.assertRedirects(
            response,
            f"{reverse('picks')}?season=2026&week=1",
            fetch_redirect_response=False,
        )
        pick = Pick.objects.get()
        self.assertEqual((pick.user, pick.game, pick.team_picked), (self.user, game, "home"))

    def test_confirmation_message_is_shown(self):
        game = make_game()
        response = self.client.post(self.pick_url(game), {"team_picked": "away"}, follow=True)
        self.assertContains(response, "Pick saved for")

    def test_only_post_is_allowed(self):
        game = make_game()
        self.assertEqual(self.client.get(self.pick_url(game)).status_code, 405)
        self.assertEqual(Pick.objects.count(), 0)

    def test_rejects_a_made_up_team_value(self):
        game = make_game()
        for bad in ("", "Not Picked", "KC", "both"):
            response = self.client.post(self.pick_url(game), {"team_picked": bad}, follow=True)
            self.assertContains(response, "Please choose the home or away team.")
        self.assertEqual(Pick.objects.count(), 0)

    def test_rejects_a_pick_after_kickoff(self):
        """Enforced on the server, not just by hiding the button."""
        game = make_game(kickoff=ago(1))
        response = self.client.post(self.pick_url(game), {"team_picked": "home"}, follow=True)
        self.assertContains(response, "locked")
        self.assertEqual(Pick.objects.count(), 0)

    def test_a_pick_can_be_changed_before_kickoff(self):
        game = make_game()
        self.client.post(self.pick_url(game), {"team_picked": "home"})
        response = self.client.post(self.pick_url(game), {"team_picked": "away"}, follow=True)
        self.assertContains(response, "Pick changed for")
        self.assertEqual(Pick.objects.count(), 1)
        self.assertEqual(Pick.objects.get().team_picked, "away")

    def test_a_pick_cannot_be_changed_after_kickoff(self):
        game = make_game()
        self.client.post(self.pick_url(game), {"team_picked": "home"})
        game.kickoff = ago(1)
        game.save()
        response = self.client.post(self.pick_url(game), {"team_picked": "away"}, follow=True)
        self.assertContains(response, "locked")
        self.assertEqual(Pick.objects.get().team_picked, "home")

    def test_unknown_game_is_a_404(self):
        response = self.client.post(reverse("make_pick", args=["NOPE_XXX@YYY"]), {"team_picked": "home"})
        self.assertEqual(response.status_code, 404)

    def test_login_is_required(self):
        game = make_game()
        self.client.logout()
        response = self.client.post(self.pick_url(game), {"team_picked": "home"})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])
        self.assertEqual(Pick.objects.count(), 0)

    def test_two_people_can_pick_the_same_game(self):
        game = make_game()
        self.client.post(self.pick_url(game), {"team_picked": "home"})
        self.client.force_login(make_user("bob"))
        self.client.post(self.pick_url(game), {"team_picked": "away"})
        self.assertEqual(Pick.objects.count(), 2)


# --------------------------------------------------- signup / login / logout --

class AuthFlowTests(TestCase):
    PASSWORD = "purple-Tiger-91-lamp"

    def test_signup_creates_the_account_and_logs_you_in(self):
        response = self.client.post(reverse("signup"), {
            "username": "newfriend", "email": "friend@example.com",
            "password1": self.PASSWORD, "password2": self.PASSWORD,
        })
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(username="newfriend").exists())
        self.assertIn("_auth_user_id", self.client.session)

    def test_signup_with_mismatched_passwords_creates_nothing(self):
        response = self.client.post(reverse("signup"), {
            "username": "newfriend", "email": "friend@example.com",
            "password1": self.PASSWORD, "password2": "something-else-123",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username="newfriend").exists())

    def test_new_signups_are_regular_users_not_admins(self):
        self.client.post(reverse("signup"), {
            "username": "newfriend", "email": "friend@example.com",
            "password1": self.PASSWORD, "password2": self.PASSWORD,
        })
        user = User.objects.get(username="newfriend")
        self.assertFalse(user.is_superuser)
        self.assertFalse(user.is_staff)

    def test_login_with_the_right_password(self):
        User.objects.create_user("sam", password=self.PASSWORD)
        response = self.client.post(reverse("login"), {"username": "sam", "password": self.PASSWORD})
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_login_with_the_wrong_password_fails(self):
        User.objects.create_user("sam", password=self.PASSWORD)
        response = self.client.post(reverse("login"), {"username": "sam", "password": "wrong"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_sends_you_to_the_login_page(self):
        self.client.force_login(User.objects.create_user("sam", password=self.PASSWORD))
        response = self.client.get(reverse("logout"))
        self.assertRedirects(response, reverse("login"), fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)


# ----------------------------------------------------------- username rules --

class UsernameRuleTests(TestCase):
    PASSWORD = "purple-Tiger-91-lamp"

    def form(self, username):
        return SignUpForm(data={
            "username": username, "email": "friend@example.com",
            "password1": self.PASSWORD, "password2": self.PASSWORD,
        })

    def test_length_limits_for_new_accounts(self):
        cases = [
            ("a" * (USERNAME_MIN_LENGTH - 1), False),
            ("a" * USERNAME_MIN_LENGTH, True),
            ("a" * USERNAME_MAX_LENGTH, True),
            ("a" * (USERNAME_MAX_LENGTH + 1), False),
            ("a" * 150, False),          # Django's own limit; ours is much lower
        ]
        for name, should_be_valid in cases:
            with self.subTest(length=len(name)):
                self.assertEqual(self.form(name).is_valid(), should_be_valid)

    def test_too_long_error_message_is_clear(self):
        form = self.form("a" * (USERNAME_MAX_LENGTH + 1))
        form.is_valid()
        self.assertIn(f"{USERNAME_MIN_LENGTH} to {USERNAME_MAX_LENGTH} characters", form.errors["username"][0])

    def test_usernames_that_differ_only_by_case_are_duplicates(self):
        User.objects.create_user("Dallas", password=self.PASSWORD)
        form = self.form("dallas")
        self.assertFalse(form.is_valid())
        self.assertIn("taken", form.errors["username"][0])

    def test_help_text_and_input_box_match_the_real_limit(self):
        field = SignUpForm().fields["username"]
        self.assertNotIn("150", field.help_text)
        self.assertIn(str(USERNAME_MAX_LENGTH), field.help_text)
        self.assertEqual(field.widget.attrs["maxlength"], USERNAME_MAX_LENGTH)

    def test_a_long_existing_username_can_still_log_in(self):
        """The login form used to refuse any name over 30 characters."""
        long_name = "x" * 40
        User.objects.create_user(long_name, password=self.PASSWORD)
        response = self.client.post(reverse("login"), {"username": long_name, "password": self.PASSWORD})
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)

    def test_a_password_with_a_trailing_space_can_log_in(self):
        """Signup keeps spaces in passwords, so login must too."""
        User.objects.create_user("sam", password=self.PASSWORD + " ")
        response = self.client.post(reverse("login"), {"username": "sam", "password": self.PASSWORD + " "})
        self.assertRedirects(response, reverse("dashboard"), fetch_redirect_response=False)
