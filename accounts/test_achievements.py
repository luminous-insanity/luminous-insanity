from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from accounts.achievements import refresh_achievement_unlocks
from accounts.views import _selected_season
from accounts.models import AchievementUnlock, Pick
from accounts.leaderboard import season_is_finalized
from api.helpers_for_tests import make_final, make_game
from api.models import Game


@override_settings(NFL_SEASON=2026)
class AchievementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('picker', password='test-pass-123')

    def test_pick_maker_counts_only_graded_picks(self):
        finished = make_final(make_game(), 21, 14)
        upcoming = make_game(week=2, game_id='UPCOMING-ACHIEVEMENT')
        Pick.objects.create(user=self.user, game=finished, team_picked=Pick.HOME)
        Pick.objects.create(user=self.user, game=upcoming, team_picked=Pick.HOME)

        cards = {card['key']: card for card in refresh_achievement_unlocks(self.user)}
        self.assertEqual(cards['pick_maker']['value'], 1)
        self.assertTrue(cards['pick_maker']['milestones'][0]['unlocked'])
        self.assertFalse(cards['pick_maker']['milestones'][1]['unlocked'])
        self.assertEqual(
            AchievementUnlock.objects.filter(
                user=self.user,
                achievement_key="pick_maker",
            ).count(),
            1,
        )

    def test_unlocked_milestone_is_persisted(self):
        game = make_final(make_game(), 21, 14)
        Pick.objects.create(user=self.user, game=game, team_picked=Pick.HOME)
        refresh_achievement_unlocks(self.user)
        unlock = AchievementUnlock.objects.get(user=self.user, achievement_key='pick_maker', level=1)

        # The record of the achievement is retained after current data changes.
        Pick.objects.filter(user=self.user, game=game).delete()
        cards = {card['key']: card for card in refresh_achievement_unlocks(self.user)}
        self.assertTrue(cards['pick_maker']['milestones'][0]['unlocked'])
        self.assertEqual(AchievementUnlock.objects.get(pk=unlock.pk).pk, unlock.pk)

    def test_achievements_page_requires_login(self):
        response = self.client.get(reverse('achievements'))
        self.assertEqual(response.status_code, 302)

    def test_season_requires_all_eighteen_weeks_and_final_scores(self):
        for week in range(1, 19):
            make_final(make_game(season=2025, week=week, game_id=f'SEASON-{week}'), 21, 14)
        self.assertTrue(season_is_finalized(2025))
        make_game(season=2025, week=18, game_id='SEASON-18-UNFINISHED')
        self.assertFalse(season_is_finalized(2025))

    @override_settings(NFL_SEASON=2027)
    def test_offseason_default_uses_latest_completed_season_when_next_season_has_no_schedule(self):
        for week in range(1, 19):
            make_final(make_game(season=2025, week=week, game_id=f'OFFSEASON-{week}'), 21, 14)
        selected, seasons = _selected_season(type('Request', (), {'GET': {}})())
        self.assertEqual(selected, 2025)
