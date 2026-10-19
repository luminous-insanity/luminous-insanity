# main/tests.py
#
# Run everything with:   python manage.py test
# Run only this file:    python manage.py test main
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.models import Pick
from api.helpers_for_tests import make_final, make_game


def make_user(name, superuser=False):
    if superuser:
        return User.objects.create_superuser(name, f"{name}@example.com", "pw-12345-xyz")
    return User.objects.create_user(name, f"{name}@example.com", "pw-12345-xyz")


def ago(hours):
    return timezone.now() - timedelta(hours=hours)


# ---------------------------------------------------------------- home page --

@override_settings(NFL_SEASON=2026)
class HomePageTests(TestCase):
    def test_loads_for_visitors(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "EVERY GAME")
        self.assertContains(response, "JOIN THE GAME")
        self.assertNotContains(response, "MAKE YOUR PICKS")

    def test_logged_in_players_get_pick_links_and_a_welcome(self):
        self.client.force_login(make_user("alice"))
        response = self.client.get(reverse("home"))
        self.assertContains(response, "MAKE YOUR PICKS")
        self.assertContains(response, "READY TO MAKE YOUR PICKS, ALICE?")
        self.assertNotContains(response, "JOIN THE GAME")

    def test_previews_only_the_current_weeks_games(self):
        make_game(week=1, home_team="KC", away_team="BAL")
        make_game(week=2, home_team="NYG", away_team="DAL")
        response = self.client.get(reverse("home"))
        self.assertEqual(response.context["current_week"], 1)
        self.assertContains(response, "WEEK 1 PREVIEW")
        self.assertEqual([g.home_team for g in response.context["featured_games"]], ["KC"])
        self.assertNotContains(response, "NYG")

    def test_shows_at_most_six_games(self):
        for _ in range(8):
            make_game()
        self.assertEqual(len(self.client.get(reverse("home")).context["featured_games"]), 6)

    def test_upcoming_game_label(self):
        make_game()
        self.assertContains(self.client.get(reverse("home")), "UPCOMING")

    def test_started_game_label_and_no_score_yet(self):
        make_game(kickoff=ago(1))
        response = self.client.get(reverse("home"))
        self.assertContains(response, "IN PROGRESS")
        self.assertNotContains(response, 'class="team-score"')

    def test_final_game_shows_both_scores(self):
        make_final(make_game(), 27, 20)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "FINAL")
        self.assertContains(response, '<span class="team-score">27</span>')
        self.assertContains(response, '<span class="team-score">20</span>')

    def test_message_when_no_games_are_loaded(self):
        self.assertContains(self.client.get(reverse("home")), "The schedule isn't available yet")

    def test_top_three_players_are_shown_in_order(self):
        alice, bob, carol, dave = (make_user(n) for n in ("alice", "bob", "carol", "dave"))
        games = [make_final(make_game(), 10, 3) for _ in range(3)]       # home team wins each
        for user, how_many in ((alice, 3), (bob, 2), (carol, 1)):
            for game in games[:how_many]:
                Pick.objects.create(user=user, game=game, team_picked="home")
        response = self.client.get(reverse("home"))
        self.assertEqual([s.user.username for s in response.context["top_standings"]],
                         ["alice", "bob", "carol"])
        self.assertNotContains(response, "dave")

    def test_admin_accounts_are_not_ranked(self):
        make_user("boss", superuser=True)
        make_user("friend")
        standings = self.client.get(reverse("home")).context["top_standings"]
        self.assertEqual([s.user.username for s in standings], ["friend"])

    def test_message_when_nobody_has_signed_up(self):
        self.assertContains(self.client.get(reverse("home")), "The leaderboard will appear here")


# ---------------------------------------------------------- leaderboard page --

@override_settings(NFL_SEASON=2026)
class LeaderboardPageTests(TestCase):
    def test_is_public(self):
        response = self.client.get(reverse("leaderboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Leaderboard")

    def test_message_when_nobody_has_signed_up(self):
        self.assertContains(
            self.client.get(reverse("leaderboard")),
            "No standings are available for this selection yet.",
        )

    def test_ranks_friends_and_hides_admin_accounts(self):
        alice, bob = make_user("alice"), make_user("bob")
        make_user("theadmin", superuser=True)
        game_one, game_two = make_final(make_game(), 27, 20), make_final(make_game(), 27, 20)
        Pick.objects.create(user=bob, game=game_one, team_picked="home")     # bob wins
        Pick.objects.create(user=bob, game=game_two, team_picked="home")     # bob wins again: 2-0
        Pick.objects.create(user=alice, game=game_one, team_picked="away")   # alice loses: 0-1
        response = self.client.get(reverse("leaderboard"))
        standings = response.context["user_stats"]
        self.assertEqual([(s.user.username, s.wins, s.losses) for s in standings],
                         [("bob", 2, 0), ("alice", 0, 1)])
        self.assertContains(response, "01")
        self.assertNotContains(response, "theadmin")

    def test_unplayed_games_do_not_count(self):
        alice = make_user("alice")
        Pick.objects.create(user=alice, game=make_game(), team_picked="home")
        standings = self.client.get(reverse("leaderboard")).context["user_stats"]
        self.assertEqual([(s.wins, s.losses, s.ties) for s in standings], [(0, 0, 0)])


# ------------------------------------------------------------- profile page --

class ProfileTests(TestCase):
    def test_login_is_required(self):
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_shows_your_own_details(self):
        user = make_user("alice")
        self.client.force_login(user)
        response = self.client.get(reverse("profile"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "alice@example.com")
        self.assertContains(response, timezone.localtime(user.date_joined).strftime("%B %Y"))

    def test_missing_email_says_not_provided(self):
        self.client.force_login(User.objects.create_user("noemail", password="pw-12345-xyz"))
        self.assertContains(self.client.get(reverse("profile")), "Not provided")

    def test_never_shows_another_players_details(self):
        make_user("bob")
        self.client.force_login(make_user("alice"))
        self.assertNotContains(self.client.get(reverse("profile")), "bob@example.com")


# -------------------------------------------------- header, footer and links --

class NavigationTests(TestCase):
    def test_every_page_renders_for_visitors(self):
        """A template that links to a page name that doesn't exist would crash here."""
        for name in ("home", "leaderboard", "login", "signup"):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_every_page_renders_when_logged_in(self):
        self.client.force_login(make_user("alice"))
        for name in ("home", "leaderboard", "dashboard", "history", "profile"):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_visitors_see_sign_up_and_login(self):
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Sign Up")
        self.assertContains(response, "Login")
        self.assertNotContains(response, "Logged in as")

    def test_logged_in_players_see_who_they_are_with_a_profile_link(self):
        self.client.force_login(make_user("alice"))
        response = self.client.get(reverse("home"))
        self.assertContains(response, "alice")
        self.assertContains(response, f'href="{reverse("profile")}"')
        self.assertContains(response, "Logout")
        self.assertNotContains(response, "Sign Up")


@override_settings(NFL_SEASON=2026)
class HistoryTests(TestCase):
    def setUp(self):
        self.user = make_user("alice")
        self.client.force_login(self.user)
        self.url = reverse("history")

    def test_login_is_required(self):
        self.client.logout()
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_results_are_worked_out_correctly(self):
        """The old history page marked every pick as a Loss."""
        won = make_final(make_game(), 27, 20)
        lost = make_final(make_game(), 27, 20)
        tied = make_final(make_game(), 20, 20)
        pending = make_game()
        unpicked = make_game()
        Pick.objects.create(user=self.user, game=won, team_picked="home")
        Pick.objects.create(user=self.user, game=lost, team_picked="away")
        Pick.objects.create(user=self.user, game=tied, team_picked="home")
        Pick.objects.create(user=self.user, game=pending, team_picked="home")
        response = self.client.get(self.url)
        results = {item["game"].game_id: item["result"] for item in response.context["game_data"]}
        self.assertEqual(results, {
            won.game_id: "Win",
            lost.game_id: "Loss",
            tied.game_id: "Draw",
            pending.game_id: "Pending",
            unpicked.game_id: "Not Picked",
        })

    def test_only_shows_your_own_picks(self):
        game = make_game()
        Pick.objects.create(user=make_user("bob"), game=game, team_picked="home")
        response = self.client.get(self.url)
        self.assertEqual(response.context["game_data"][0]["user_pick"], "Not Picked")

    def test_only_this_seasons_games(self):
        make_game(season=2026)
        make_game(season=2025)
        response = self.client.get(self.url)
        self.assertEqual(len(response.context["game_data"]), 1)

    def test_empty_history_message(self):
        self.assertContains(self.client.get(self.url), "No pick history available")
