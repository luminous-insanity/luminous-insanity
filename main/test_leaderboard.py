# Tests for the Weekly/Season leaderboard, filters, banners, champion reveal,
# inactive accounts and the side-by-side pick comparison.
#
#   python manage.py test main.test_leaderboard
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.leaderboard import default_week, season_is_finalized
from accounts.models import ChampionRevealSeen, FriendRequest, Pick, UserActivity
from accounts.signals import touch_activity
from api.helpers_for_tests import make_final, make_game


def make_user(name):
    return User.objects.create_user(name, f"{name}@example.com", "pw-12345-xyz")


def ago(hours):
    return timezone.now() - timedelta(hours=hours)


def pick(user, game, side):
    return Pick.objects.create(user=user, game=game, team_picked=side)


def rows(response):
    return [(s.user.username, s.rank, s.wins, s.losses, s.ties)
            for s in response.context["user_stats"]]


def make_inactive(user, days=90):
    old = timezone.now() - timedelta(days=days)
    UserActivity.objects.update_or_create(user=user, defaults={"last_active": old})
    User.objects.filter(pk=user.pk).update(date_joined=old, last_login=None)


def befriend(a, b):
    FriendRequest.objects.create(sender=a, receiver=b, status=FriendRequest.ACCEPTED)


URL = reverse("leaderboard")


@override_settings(NFL_SEASON=2026)
class TabsAndDefaultsTests(TestCase):
    def test_weekly_is_the_default_tab_and_opens_on_the_latest_completed_week(self):
        make_final(make_game(week=1), 10, 3)
        make_final(make_game(week=2), 10, 3)
        make_game(week=3)
        response = self.client.get(URL)
        self.assertEqual(response.context["tab"], "weekly")
        self.assertEqual(response.context["selected_week"], 2)
        self.assertEqual(response.context["weeks"], [1, 2, 3])

    def test_week_navigation_is_disabled_at_the_edges(self):
        make_final(make_game(week=1), 10, 3)
        make_game(week=2)
        first = self.client.get(URL, {"week": 1})
        self.assertEqual(first.context["prev_url"], "")
        self.assertTrue(first.context["next_url"])
        last = self.client.get(URL, {"week": 2})
        self.assertTrue(last.context["prev_url"])
        self.assertEqual(last.context["next_url"], "")

    def test_season_tab_is_available_and_old_links_still_work(self):
        make_final(make_game(week=1), 10, 3)
        self.assertEqual(self.client.get(URL, {"tab": "season"}).context["tab"], "season")
        self.assertEqual(self.client.get(URL, {"week": "season"}).context["tab"], "season")
        self.assertEqual(self.client.get(URL, {"week": "1"}).context["selected_week"], 1)

    def test_offseason_with_no_final_games_still_loads(self):
        self.assertEqual(self.client.get(URL).status_code, 200)
        self.assertEqual(default_week(2026), 1)


@override_settings(NFL_SEASON=2026)
class WeeklyStandingsTests(TestCase):
    def setUp(self):
        self.a, self.b, self.c = make_user("alice"), make_user("bob"), make_user("carol")
        self.g1 = make_final(make_game(week=1), 27, 20)    # home wins
        self.g2 = make_final(make_game(week=1), 27, 20)

    def test_tied_players_share_a_rank_and_the_next_is_skipped(self):
        for user in (self.a, self.b):
            pick(user, self.g1, "home"); pick(user, self.g2, "home")
        pick(self.c, self.g1, "home"); pick(self.c, self.g2, "away")
        got = rows(self.client.get(URL, {"week": 1}))
        self.assertEqual(got, [("alice", 1, 2, 0, 0), ("bob", 1, 2, 0, 0), ("carol", 3, 1, 1, 0)])

    def test_pending_picks_are_not_losses_and_a_player_can_be_0_0_0(self):
        pending = make_game(week=1)                       # not played yet
        pick(self.a, self.g1, "home")
        pick(self.b, pending, "away")
        response = self.client.get(URL, {"week": 1})
        got = {r[0]: r[2:] for r in rows(response)}
        self.assertEqual(got["alice"], (1, 0, 0))
        self.assertEqual(got["bob"], (0, 0, 0))           # pending only: no loss
        bob = [s for s in response.context["user_stats"] if s.user == self.b][0]
        self.assertEqual(bob.pending, 1)
        self.assertContains(response, "1 pending")

    def test_missing_picks_are_not_losses(self):
        pick(self.a, self.g1, "home")                     # alice skipped g2
        got = {r[0]: r[2:] for r in rows(self.client.get(URL, {"week": 1}))}
        self.assertEqual(got["alice"], (1, 0, 0))

    def test_rank_movement(self):
        g3 = make_final(make_game(week=2), 27, 20)
        g4 = make_final(make_game(week=2), 27, 20)
        dave = make_user("dave")
        # Week 1: alice 2-0, bob 1-1, carol 0-2.
        pick(self.a, self.g1, "home"); pick(self.a, self.g2, "home")
        pick(self.b, self.g1, "home"); pick(self.b, self.g2, "away")
        pick(self.c, self.g1, "away"); pick(self.c, self.g2, "away")
        # Week 2: bob 2-0, dave 1-0, carol 1-1, alice 0-2.
        pick(self.b, g3, "home"); pick(self.b, g4, "home")
        pick(dave, g3, "home")
        pick(self.c, g3, "home"); pick(self.c, g4, "away")
        pick(self.a, g3, "away"); pick(self.a, g4, "away")
        response = self.client.get(URL, {"week": 2})
        moves = {s.user.username: s.movement_label for s in response.context["user_stats"]}
        self.assertEqual(moves, {"bob": "↑1", "dave": "New", "carol": "—0", "alice": "↓3"})

    def test_week_one_shows_a_dash_instead_of_movement(self):
        pick(self.a, self.g1, "home")
        response = self.client.get(URL, {"week": 1})
        self.assertEqual({s.movement_label for s in response.context["user_stats"]}, {"—"})

    def test_winner_banner_crowns_everyone_tied_for_first(self):
        for user in (self.a, self.b):
            pick(user, self.g1, "home")
        pick(self.c, self.g1, "away")
        response = self.client.get(URL, {"week": 1})
        self.assertEqual({w.user.username for w in response.context["winners"]}, {"alice", "bob"})
        self.assertContains(response, "Week 1 winners (tied)")
        self.assertContains(response, "👑")

    def test_banner_says_leader_while_the_week_is_still_in_progress(self):
        make_game(week=1)
        pick(self.a, self.g1, "home")
        self.assertContains(self.client.get(URL, {"week": 1}), "Week 1 leader")

    def test_no_banner_when_nobody_has_won_anything(self):
        pick(self.a, self.g1, "away")
        self.assertEqual(self.client.get(URL, {"week": 1}).context["winners"], [])


@override_settings(NFL_SEASON=2026)
class SeasonStandingsTests(TestCase):
    def test_percentage_ranking_and_ties(self):
        a, b = make_user("alice"), make_user("bob")
        wins = [make_final(make_game(week=w), 27, 20) for w in (1, 2, 3)]
        tie = make_final(make_game(week=4), 20, 20)
        loss = make_final(make_game(week=5), 27, 20)
        for g in wins:
            pick(a, g, "home")
        pick(a, tie, "home")                      # alice 3-0-1
        pick(b, wins[0], "home"); pick(b, wins[1], "home")
        pick(b, loss, "away")                     # bob 2-1-0
        response = self.client.get(URL, {"tab": "season"})
        self.assertEqual(rows(response), [("alice", 1, 3, 0, 1), ("bob", 2, 2, 1, 0)])
        alice = response.context["user_stats"][0]
        self.assertAlmostEqual(alice.win_pct, 87.5)       # (3 + 0.5) / 4
        self.assertContains(response, "87.5%")
        self.assertContains(response, "66.7%")

    def test_no_percentage_without_completed_games(self):
        player = make_user("newbie")
        pick(player, make_game(week=1), "home")
        response = self.client.get(URL, {"tab": "season"})
        self.assertIsNone(response.context["user_stats"][0].win_pct)
        self.assertContains(response, "—")


@override_settings(NFL_SEASON=2026)
class FilterTests(TestCase):
    def setUp(self):
        self.a, self.b, self.c = make_user("alice"), make_user("bob"), make_user("carol")
        self.g = make_final(make_game(week=1), 27, 20)
        for user in (self.a, self.b, self.c):
            pick(user, self.g, "home")

    def test_friends_filter_shows_you_and_your_friends_only(self):
        befriend(self.a, self.b)
        self.client.force_login(self.a)
        response = self.client.get(URL, {"filter": "friends"})
        self.assertEqual({r[0] for r in rows(response)}, {"alice", "bob"})

    def test_empty_friends_list_shows_the_invite(self):
        self.client.force_login(self.a)
        response = self.client.get(URL, {"filter": "friends"})
        self.assertContains(response, "Add friends to start your own competition")
        self.assertContains(response, "Find friends")

    def test_each_tab_remembers_its_own_filter(self):
        befriend(self.a, self.b)
        self.client.force_login(self.a)
        self.client.get(URL, {"tab": "weekly", "filter": "friends"})
        self.assertEqual(self.client.get(URL, {"tab": "season"}).context["filter_mode"], "all")
        self.client.get(URL, {"tab": "season", "filter": "all"})
        self.assertEqual(self.client.get(URL, {"tab": "weekly"}).context["filter_mode"], "friends")

    def test_friends_mode_features_the_top_friend(self):
        befriend(self.a, self.b)
        # Carol is not a friend. Make her the overall leader of week 2.
        g2 = make_final(make_game(week=2), 27, 20)
        pick(self.c, g2, "home"); pick(self.b, g2, "away")
        self.client.force_login(self.a)
        response = self.client.get(URL, {"week": 2, "filter": "friends"})
        self.assertEqual([r[0] for r in rows(response)], ["alice", "bob"])
        self.assertNotIn("carol", [w.user.username for w in response.context["winners"]])

    def test_logged_in_players_row_is_highlighted(self):
        self.client.force_login(self.a)
        self.assertContains(self.client.get(URL), "lb-item is-me")


@override_settings(NFL_SEASON=2026)
class InactiveAccountTests(TestCase):
    def setUp(self):
        self.a, self.b = make_user("alice"), make_user("bob")
        self.g1 = make_final(make_game(week=1), 27, 20)
        pick(self.a, self.g1, "home"); pick(self.b, self.g1, "home")
        self.g2 = make_game(week=2)                      # week 2 is the live week
        pick(self.a, self.g2, "home")
        make_inactive(self.b)

    def names(self, **params):
        return [r[0] for r in rows(self.client.get(URL, params))]

    def test_inactive_accounts_leave_the_current_standings(self):
        self.assertEqual(self.names(tab="season"), ["alice"])
        self.assertEqual(self.names(week=2), ["alice"])

    def test_history_is_preserved(self):
        self.assertEqual(set(self.names(week=1)), {"alice", "bob"})
        self.assertEqual(Pick.objects.filter(user=self.b).count(), 1)

    def test_they_come_back_when_active_again(self):
        touch_activity(self.b)
        self.assertEqual(set(self.names(tab="season")), {"alice", "bob"})

    def test_picking_counts_as_activity(self):
        make_inactive(self.b)
        pick(self.b, self.g2, "away")
        self.assertGreater(UserActivity.objects.get(user=self.b).last_active,
                           timezone.now() - timedelta(minutes=1))

    def test_logging_in_counts_as_activity(self):
        make_inactive(self.b)
        self.client.force_login(self.b)
        self.assertGreater(UserActivity.objects.get(user=self.b).last_active,
                           timezone.now() - timedelta(minutes=1))


class ChampionTests(TestCase):
    """A champion requires the full 18-week schedule and final scores."""

    def setUp(self):
        self.a, self.b = make_user("alice"), make_user("bob")
        self.g1 = make_final(make_game(season=2025, week=1), 27, 20)
        self.g2 = make_final(make_game(season=2025, week=2), 27, 20)
        for week in range(3, 19):
            make_final(make_game(season=2025, week=week), 24, 17)

    @override_settings(NFL_SEASON=2026)
    def test_no_champion_until_the_season_is_finalized(self):
        make_game(season=2025, week=3)                    # an unfinished game
        pick(self.a, self.g1, "home")
        self.assertFalse(season_is_finalized(2025))
        response = self.client.get(URL, {"season": 2025, "tab": "season"})
        self.assertIsNone(response.context["champion"])
        self.assertNotContains(response, "season champion")

    @override_settings(NFL_SEASON=2026)
    def test_champion_shows_username_record_and_percentage(self):
        pick(self.a, self.g1, "home"); pick(self.a, self.g2, "home")
        pick(self.b, self.g1, "home"); pick(self.b, self.g2, "away")
        response = self.client.get(URL, {"season": 2025, "tab": "season"})
        champion = response.context["champion"]
        self.assertEqual(champion["champions"],
                         [{"username": "alice", "record": "2–0–0", "pct": "100.0%"}])
        self.assertContains(response, "2025 season champion")
        self.assertContains(response, "Season champion")

    @override_settings(NFL_SEASON=2026)
    def test_co_champions_are_both_recognized(self):
        for user in (self.a, self.b):
            pick(user, self.g1, "home"); pick(user, self.g2, "home")
        champion = self.client.get(URL, {"season": 2025}).context["champion"]
        self.assertTrue(champion["co_champions"])
        self.assertEqual({c["username"] for c in champion["champions"]}, {"alice", "bob"})

    @override_settings(NFL_SEASON=2026)
    def test_reveal_opens_automatically_only_once_per_user_per_season(self):
        pick(self.a, self.g1, "home")
        self.client.force_login(self.a)
        first = self.client.get(URL, {"season": 2025})
        second = self.client.get(URL, {"season": 2025})
        self.assertTrue(first.context["auto_reveal"])
        self.assertFalse(second.context["auto_reveal"])
        self.assertTrue(ChampionRevealSeen.objects.filter(user=self.a, season=2025).exists())
        self.assertContains(second, "data-champion-open")      # replay still offered

    @override_settings(NFL_SEASON=2026)
    def test_each_player_gets_their_own_reveal(self):
        pick(self.a, self.g1, "home")
        self.client.force_login(self.a)
        self.client.get(URL, {"season": 2025})
        self.client.force_login(self.b)
        self.assertTrue(self.client.get(URL, {"season": 2025}).context["auto_reveal"])


@override_settings(NFL_SEASON=2026)
class PlayerMenuTests(TestCase):
    def test_rows_open_a_menu_instead_of_linking_to_a_profile(self):
        alice, bob = make_user("alice"), make_user("bob")
        g = make_final(make_game(week=1), 27, 20)
        pick(alice, g, "home"); pick(bob, g, "home")
        self.client.force_login(alice)
        response = self.client.get(URL, {"week": 1})
        self.assertContains(response, "data-menu-trigger")
        self.assertContains(response, "View Profile")
        self.assertContains(response, "View Picks")
        self.assertContains(response, "Challenge to Head-to-Head")
        self.assertContains(response, f'data-profile-url="{reverse("player_profile", args=[bob.id])}')
        self.assertContains(response, f'data-picks-url="{reverse("compare_picks", args=[bob.id])}')

    def test_challenge_option_is_a_real_link(self):
        bob = make_user("bob")
        g = make_final(make_game(week=1), 27, 20)
        pick(bob, g, "home")
        self.client.force_login(make_user("alice"))
        response = self.client.get(URL)
        self.assertContains(response, 'id="pm-challenge"')
        self.assertContains(response, f'data-challenge-url="{reverse("challenge_new", args=[bob.id])}"')

    def test_other_players_profile_page(self):
        bob = make_user("bob")
        self.assertContains(self.client.get(reverse("player_profile", args=[bob.id])), "bob")

    def test_your_own_profile_link_goes_to_your_profile_page(self):
        alice = make_user("alice")
        self.client.force_login(alice)
        response = self.client.get(reverse("player_profile", args=[alice.id]))
        self.assertRedirects(response, reverse("profile"))


@override_settings(NFL_SEASON=2026)
class ComparePicksTests(TestCase):
    def setUp(self):
        self.me, self.them = make_user("alice"), make_user("bob")
        self.final = make_final(make_game(week=1, kickoff=ago(30)), 27, 20)
        self.live = make_game(week=1, kickoff=ago(1))            # started, no score yet
        self.future = make_game(week=1)                          # not locked
        self.unpicked = make_game(week=1, kickoff=ago(1))

        pick(self.me, self.final, "home"); pick(self.them, self.final, "away")      # differ
        pick(self.me, self.live, "home"); pick(self.them, self.live, "home")        # same
        pick(self.me, self.future, "home"); pick(self.them, self.future, "away")    # hidden
        pick(self.them, self.unpicked, "home")                                      # I have none

    def get(self):
        self.client.force_login(self.me)
        return self.client.get(
            reverse("compare_picks", args=[self.them.id]), {"season": 2026, "week": 1})

    def test_login_is_required(self):
        response = self.client.get(reverse("compare_picks", args=[self.them.id]))
        self.assertEqual(response.status_code, 302)

    def test_counts_only_real_differences(self):
        response = self.get()
        self.assertEqual(response.context["differ"], 1)
        self.assertContains(response, "You differ on 1 game this week.")

    def test_missing_picks_are_labelled_and_tracked_separately(self):
        response = self.get()
        self.assertEqual(response.context["my_missing"], 1)
        self.assertContains(response, "No pick yet")

    def test_their_pick_stays_hidden_until_kickoff(self):
        response = self.get()
        self.assertEqual(response.context["hidden"], 1)
        row = [r for r in response.context["rows"] if r["game"] == self.future][0]
        self.assertIsNone(row["their_team"])
        self.assertEqual(row["their_state"], "hidden")
        self.assertFalse(row["differs"])

    def test_friends_see_each_others_picks_before_kickoff(self):
        befriend(self.me, self.them)
        response = self.get()
        self.assertTrue(response.context["are_friends"])
        self.assertEqual(response.context["hidden"], 0)
        row = [r for r in response.context["rows"] if r["game"] == self.future][0]
        self.assertEqual(row["their_team"], "BAL")        # their away pick
        self.assertTrue(row["differs"])
        self.assertEqual(response.context["differ"], 2)   # final + the unlocked game

    def test_pending_and_completed_results(self):
        response = self.get()
        by_game = {r["game"].pk: r for r in response.context["rows"]}
        self.assertEqual(by_game[self.final.pk]["my_label"], "Correct")
        self.assertEqual(by_game[self.final.pk]["their_label"], "Incorrect")
        self.assertEqual(by_game[self.live.pk]["my_label"], "Pending")

    def test_shows_week_records_and_the_season_gap(self):
        response = self.get()
        self.assertEqual(response.context["my_week"].record, (1, 0, 0))
        self.assertEqual(response.context["their_week"].record, (0, 1, 0))
        self.assertEqual(response.context["gap_text"], "You lead by 1 win")

    def test_comparing_with_yourself_goes_to_your_picks(self):
        self.client.force_login(self.me)
        response = self.client.get(reverse("compare_picks", args=[self.me.id]))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("picks"), response["Location"])
