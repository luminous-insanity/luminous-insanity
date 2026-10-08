# main/tests.py
#
# Run everything with:   python manage.py test
# Run only this file:    python manage.py test main
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.models import Pick
from api.helpers_for_tests import make_final, make_game


def make_user(name, superuser=False):
    if superuser:
        return User.objects.create_superuser(name, f"{name}@example.com", "pw-12345-xyz")
    return User.objects.create_user(name, f"{name}@example.com", "pw-12345-xyz")


@override_settings(NFL_SEASON=2026)
class HomeLeaderboardTests(TestCase):
    def test_page_loads_without_logging_in(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Leaderboard")

    def test_message_when_nobody_has_signed_up(self):
        self.assertContains(self.client.get(reverse("home")), "No user statistics available")

    def test_ranks_friends_and_hides_admin_accounts(self):
        alice, bob = make_user("alice"), make_user("bob")
        make_user("theadmin", superuser=True)
        game_one, game_two = make_final(make_game(), 27, 20), make_final(make_game(), 27, 20)
        Pick.objects.create(user=bob, game=game_one, team_picked="home")     # bob wins
        Pick.objects.create(user=bob, game=game_two, team_picked="home")     # bob wins again: 2-0
        Pick.objects.create(user=alice, game=game_one, team_picked="away")   # alice loses: 0-1
        response = self.client.get(reverse("home"))
        standings = response.context["user_stats"]
        self.assertEqual([(s.user.username, s.wins, s.losses) for s in standings],
                         [("bob", 2, 0), ("alice", 0, 1)])
        self.assertNotContains(response, "theadmin")

    def test_unplayed_games_do_not_count(self):
        alice = make_user("alice")
        Pick.objects.create(user=alice, game=make_game(), team_picked="home")
        standings = self.client.get(reverse("home")).context["user_stats"]
        self.assertEqual([(s.wins, s.losses, s.ties) for s in standings], [(0, 0, 0)])


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
