# accounts/tests.py
#
# Run everything with:   python manage.py test
# Run only this file:    python manage.py test accounts
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Pick
from accounts.standings import compute_standings, standing_for
from api.helpers_for_tests import make_final, make_game

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
        self.assertRedirects(response, "/accounts/login/?next=/accounts/dashboard/",
                             fetch_redirect_response=False)

    def test_shows_your_existing_pick_and_lets_you_change_it(self):
        """The old dashboard looked picks up by the wrong id and never showed them."""
        game = make_game()
        Pick.objects.create(user=self.user, game=game, team_picked="home")
        response = self.client.get(self.url)
        self.assertContains(response, "Your Pick:</strong> KC")
        self.assertContains(response, 'name="team_picked"')              # buttons stay until kickoff
        self.assertContains(response, "pick-button selected", count=1)   # your pick is highlighted

    def test_locked_game_shows_your_pick_without_buttons(self):
        game = make_game(kickoff=ago(1))
        Pick.objects.create(user=self.user, game=game, team_picked="away")
        response = self.client.get(self.url)
        self.assertContains(response, "Your Pick:</strong> BAL")
        self.assertNotContains(response, 'name="team_picked"')

    def test_open_unpicked_game_offers_pick_buttons(self):
        make_game()
        response = self.client.get(self.url)
        self.assertContains(response, 'name="team_picked"')
        self.assertContains(response, "Pick BAL")
        self.assertContains(response, "Pick KC")

    def test_started_unpicked_game_is_locked(self):
        make_game(kickoff=ago(1))
        response = self.client.get(self.url)
        self.assertContains(response, "Picks Unavailable (Game Started)")
        self.assertNotContains(response, 'name="team_picked"')

    def test_kickoff_time_is_shown(self):
        make_game()
        self.assertContains(self.client.get(self.url), "Kickoff (picks lock):")

    def test_unplayed_game_shows_na(self):
        make_game()
        response = self.client.get(self.url)
        self.assertContains(response, "Away Score:</strong> N/A")
        self.assertContains(response, "Winner:</strong> N/A")

    def test_a_score_of_zero_is_shown_as_zero(self):
        """The old page printed N/A for a shutout."""
        make_final(make_game(), 17, 0)
        response = self.client.get(self.url)
        self.assertContains(response, "Away Score:</strong> 0")
        self.assertContains(response, "Home Score:</strong> 17")
        self.assertContains(response, "Winner:</strong> KC")

    def test_your_record_is_shown(self):
        game = make_final(make_game(), 27, 20)
        Pick.objects.create(user=self.user, game=game, team_picked="home")
        response = self.client.get(self.url)
        self.assertContains(response, "Wins: 1")
        self.assertContains(response, "Losses: 0")

    def test_no_games_message(self):
        self.assertContains(self.client.get(self.url), "No games available for this week.")

    def test_defaults_to_the_current_week_and_can_browse_others(self):
        make_game(week=1, home_team="KC", away_team="BAL")
        make_game(week=2, home_team="NYG", away_team="DAL")
        response = self.client.get(self.url)
        self.assertEqual(response.context["selected_week"], 1)
        self.assertContains(response, "Week 1")
        self.assertNotContains(response, "Previous week")      # nothing before week 1
        self.assertContains(response, "Next week")
        response = self.client.get(self.url + "?week=2")
        self.assertEqual(response.context["selected_week"], 2)
        self.assertContains(response, "NYG")
        self.assertNotContains(response, "Pick KC")             # week 1's game isn't on this page
        self.assertContains(response, "This week")             # link back to the current week

    def test_nonsense_week_falls_back_to_the_current_week(self):
        make_game(week=1)
        for bad in ("?week=99", "?week=0", "?week=abc", "?week="):
            response = self.client.get(self.url + bad)
            self.assertEqual(response.context["selected_week"], 1, bad)

    def test_only_this_seasons_games_show(self):
        make_game(season=2026, home_team="KC", away_team="BAL")
        make_game(season=2025, home_team="SEA", away_team="MIA")
        response = self.client.get(self.url)
        self.assertContains(response, "Pick KC")
        self.assertNotContains(response, "Pick SEA")


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
        self.assertRedirects(response, f"{reverse('dashboard')}?week=1", fetch_redirect_response=False)
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
