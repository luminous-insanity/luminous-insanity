from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from api.models import Game
from accounts.crossfire import (
    CrossfireError,
    grade_crossfire,
    place_crossfire,
    tokens_left,
    week_board,
)
from accounts.models import Crossfire, Pick


SETTINGS = {
    "NFL_SEASON": 2026,
}


def later(hours=12):
    return timezone.now() + timedelta(hours=hours)


def ago(hours=3):
    return timezone.now() - timedelta(hours=hours)


@override_settings(**SETTINGS)
class CrossfireRulesTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user("hunter", "h@example.com", "pass")
        self.b = User.objects.create_user("prey", "p@example.com", "pass")
        self.c = User.objects.create_user("ally", "a@example.com", "pass")
        self.game = Game.objects.create(
            season=2026, week=4, game_id="CF-1",
            home_team="KC", away_team="BUF",
            game_date=timezone.localdate(),
            kickoff=later(24),
            status=Game.SCHEDULED,
        )
        Pick.objects.create(user=self.a, game=self.game, team_picked="home")
        Pick.objects.create(user=self.b, game=self.game, team_picked="away")
        Pick.objects.create(user=self.c, game=self.game, team_picked="home")

    def test_place_opposite_sides(self):
        cf = place_crossfire(self.a, self.b, self.game)
        self.assertEqual(cf.attacker_side, "home")
        self.assertEqual(cf.target_side, "away")
        self.assertEqual(tokens_left(self.a, 2026, 4), 2)

    def test_cannot_fire_same_side(self):
        with self.assertRaises(CrossfireError):
            place_crossfire(self.a, self.c, self.game)

    def test_cannot_fire_self(self):
        with self.assertRaises(CrossfireError):
            place_crossfire(self.a, self.a, self.game)

    def test_token_cap(self):
        for i in range(3):
            g = Game.objects.create(
                season=2026, week=4, game_id=f"CF-T{i}",
                home_team="X", away_team="Y",
                game_date=timezone.localdate(), kickoff=later(30),
                status=Game.SCHEDULED,
            )
            Pick.objects.create(user=self.a, game=g, team_picked="home")
            Pick.objects.create(user=self.b, game=g, team_picked="away")
            place_crossfire(self.a, self.b, g)
        with self.assertRaises(CrossfireError):
            place_crossfire(self.a, self.b, self.game)

    def test_hit_and_miss_grading(self):
        cf = place_crossfire(self.a, self.b, self.game)
        self.game.status = Game.FINAL
        self.game.home_score = 27
        self.game.away_score = 20
        self.game.save()
        self.assertEqual(grade_crossfire(cf).result, "hit")

        self.game.home_score = 10
        self.game.away_score = 30
        self.game.save()
        self.assertEqual(grade_crossfire(cf).result, "miss")

    def test_does_not_change_when_picks_change_later(self):
        cf = place_crossfire(self.a, self.b, self.game)
        Pick.objects.filter(user=self.a, game=self.game).update(team_picked="away")
        self.game.status = Game.FINAL
        self.game.home_score = 27
        self.game.away_score = 10
        self.game.save()
        # Snapshot said attacker home — still a hit against original target away
        self.assertEqual(grade_crossfire(cf).result, "hit")

    def test_board_counts_most_wanted(self):
        place_crossfire(self.a, self.b, self.game)
        board = week_board(2026, 4, viewer=self.a)
        self.assertEqual(board["total_crossfires"], 1)
        self.assertEqual(board["most_wanted"][0]["count"], 1)
        self.assertEqual(board["tokens"]["left"], 2)


@override_settings(**SETTINGS)
class CrossfireViewTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user("hunter2", "h2@example.com", "pass")
        self.b = User.objects.create_user("prey2", "p2@example.com", "pass")
        self.game = Game.objects.create(
            season=2026, week=5, game_id="CF-V1",
            home_team="DAL", away_team="PHI",
            game_date=timezone.localdate(), kickoff=later(20),
            status=Game.SCHEDULED,
        )
        Pick.objects.create(user=self.a, game=self.game, team_picked="home")
        Pick.objects.create(user=self.b, game=self.game, team_picked="away")

    def test_board_requires_login(self):
        r = self.client.get(reverse("crossfire"))
        self.assertEqual(r.status_code, 302)

    def test_fire_flow(self):
        self.client.login(username="hunter2", password="pass")
        r = self.client.post(
            reverse("crossfire_fire", args=[self.game.game_id, self.b.id])
        )
        self.assertEqual(r.status_code, 302)
        self.assertTrue(
            Crossfire.objects.filter(attacker=self.a, target=self.b, game=self.game).exists()
        )
        board = self.client.get(reverse("crossfire") + "?week=5")
        self.assertContains(board, "prey2")
        self.assertContains(board, "Crossfire")


@override_settings(**SETTINGS)
class CrossfireMissionTests(TestCase):
    def setUp(self):
        self.a = User.objects.create_user("mission_hunter", password="pass")
        self.b = User.objects.create_user("mission_target", password="pass")
        self.games = [
            Game.objects.create(
                season=2026, week=6, game_id=f"CF-MISSION-{i}",
                home_team="KC", away_team="BUF",
                game_date=timezone.localdate(), kickoff=later(24 + i),
                status=Game.SCHEDULED,
            )
            for i in range(3)
        ]

    def test_three_shot_crossfire_mission_tracks_weekly_fires(self):
        from accounts.quests import build_weekly_quests

        def mission():
            quests = build_weekly_quests(self.a, season=2026, week=6)["quests"]
            return next(q for q in quests if q["key"] == "crossfire_three_shots")

        self.assertEqual(mission()["current"], 0)
        self.assertFalse(mission()["complete"])

        for game in self.games[:2]:
            Crossfire.objects.create(
                season=2026, week=6, attacker=self.a, target=self.b,
                game=game, attacker_side=Pick.HOME, target_side=Pick.AWAY,
            )

        self.assertEqual(mission()["current"], 2)
        self.assertFalse(mission()["complete"])

        game = self.games[2]
        Crossfire.objects.create(
            season=2026, week=6, attacker=self.a, target=self.b,
            game=game, attacker_side=Pick.HOME, target_side=Pick.AWAY,
        )
        self.assertEqual(mission()["current"], 3)
        self.assertTrue(mission()["complete"])
