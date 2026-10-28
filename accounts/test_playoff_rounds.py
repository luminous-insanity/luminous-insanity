from datetime import date

from django.conf import settings
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from api.models import Game

from .models import PlayerIdentity, PlayoffEntry, PlayoffSettings, Pick
from .playoff_cuts import cut_targets, split_field, survival_key, tiebreak_draw
from .playoff_rounds import PlayoffError, get_config, open_playoffs, run_cut
from .playoffs import DIVISIONS, division_playoff_race, wildcard_score
from .standings import compute_standings


class CutRulesTests(SimpleTestCase):
    def test_field_always_lands_on_the_target(self):
        for start in range(51, 1500, 7):
            targets = cut_targets(start, 50)
            self.assertEqual(targets[-1], 50)
            self.assertEqual(targets, sorted(targets, reverse=True))

    def test_small_field_is_never_cut(self):
        self.assertEqual(cut_targets(3, 50), [3, 3, 3])
        self.assertEqual(cut_targets(50, 50), [50, 50, 50])

    def test_known_step_down(self):
        self.assertEqual(cut_targets(200, 50), [126, 79, 50])

    def test_tiebreak_order(self):
        rows = [('a', 3, 1, 0, 60, 0, 5), ('b', 3, 1, 0, 70, 0, 9),
                ('c', 3, 1, 0, 70, 2, 9), ('d', 4, 0, 0, 10, 0, 1)]
        keep, out = split_field(rows, 2, lambda r: survival_key(*r[1:]))
        self.assertEqual([r[0] for r in keep], ['d', 'c'])
        self.assertEqual([r[0] for r in out], ['b', 'a'])

    def test_draw_is_fixed_per_player_and_season(self):
        self.assertEqual(tiebreak_draw(2026, 7), tiebreak_draw(2026, 7))
        self.assertNotEqual(tiebreak_draw(2026, 7), tiebreak_draw(2026, 8))

    def test_wildcard_score_rewards_participation(self):
        lucky = wildcard_score(1, 0, 0, 60)
        established = wildcard_score(42, 12, 0, 60)
        late_strong = wildcard_score(20, 2, 0, 60)
        self.assertLess(lucky, late_strong)
        self.assertLess(late_strong, established)


class PlayoffFlowTests(TestCase):
    def setUp(self):
        self.season = settings.NFL_SEASON
        self.users = {}
        for i in range(1, 13):
            user = User.objects.create_user(username=f'p{i:02d}')
            PlayerIdentity.objects.create(
                user=user, division=DIVISIONS[i % 8], division_season=self.season)
            self.users[i] = user
        PlayoffSettings.objects.create(season=self.season, field_target=4)
        self.regular = self.game(1, 'reg', final=True)

    def game(self, week, tag, final=True, home=24, away=10):
        return Game.objects.create(
            season=self.season, week=week, game_id=f'test-{week}-{tag}',
            home_team='AAA', away_team='BBB', game_date=date(2026, 9, 7),
            status=Game.FINAL if final else Game.SCHEDULED,
            home_score=home if final else None, away_score=away if final else None)

    def pick(self, i, game, side):
        Pick.objects.create(user=self.users[i], game=game, team_picked=side)

    def names_eliminated(self):
        return set(PlayoffEntry.objects.filter(
            season=self.season, status=PlayoffEntry.ELIMINATED
        ).values_list('user__username', flat=True))

    def test_playoff_games_do_not_change_regular_season_records(self):
        self.pick(1, self.regular, 'home')
        playoff = self.game(19, 'wc')
        self.pick(1, playoff, 'home')
        rows = compute_standings(season=self.season, through_week=18)
        mine = [r for r in rows if r.user.id == self.users[1].id][0]
        self.assertEqual(mine.wins, 1)

    def test_percentage_mode_takes_a_share_of_each_division(self):
        PlayoffSettings.objects.filter(season=self.season).update(qualifier_percent=50)
        for n in range(4):
            user = User.objects.create_user(username=f'east{n}')
            PlayerIdentity.objects.create(user=user, division='AFC East', division_season=self.season)
            Pick.objects.create(
                user=user, game=self.regular, team_picked='home' if n < 2 else 'away')
        race = division_playoff_race('AFC East', self.season)
        # AFC East has 5 players (4 new + p08): half of 5 rounds up to 3.
        self.assertEqual(len(race['standings']), 5)
        self.assertEqual(race['qualifiers_per_division'], 3)

    def test_cannot_open_twice(self):
        open_playoffs(self.season, force=True)
        with self.assertRaises(PlayoffError):
            open_playoffs(self.season, force=True)

    def test_three_cuts_step_down_to_the_target(self):
        for i in range(1, 13):
            self.pick(i, self.regular, 'home')
        self.assertEqual(open_playoffs(self.season), 12)
        self.assertEqual(get_config(self.season).rounds_cut, 0)

        # Round 1 (Wild Card): two games, home team wins both.
        wc1, wc2 = self.game(19, 'a'), self.game(19, 'b')
        for i in (1, 2, 3, 4):          # 2-0
            self.pick(i, wc1, 'home'); self.pick(i, wc2, 'home')
        for i in (5, 6, 7, 8):          # 1-1
            self.pick(i, wc1, 'home'); self.pick(i, wc2, 'away')
        for i in (9, 10, 11):           # 0-2
            self.pick(i, wc1, 'away'); self.pick(i, wc2, 'away')
        # player 12 makes no picks: unpicked games count as losses
        result = run_cut(self.season)
        self.assertEqual((result['before'], result['after']), (12, 8))
        self.assertEqual(self.names_eliminated(), {'p09', 'p10', 'p11', 'p12'})

        # Round 2 (Divisional): one game, home team wins.
        div = self.game(20, 'a')
        for i in (1, 2):
            self.pick(i, div, 'away')    # 2-1
        for i in (3, 4, 5, 6):
            self.pick(i, div, 'home')    # 3-0 and 2-1
        for i in (7, 8):
            self.pick(i, div, 'away')    # 1-2
        run_cut(self.season)
        self.assertEqual(self.names_eliminated() - {'p09', 'p10', 'p11', 'p12'}, {'p07', 'p08'})

        # Round 3 (Conference): one game, home team wins.
        conf = self.game(21, 'a')
        for i in (1, 2, 3, 4):
            self.pick(i, conf, 'home')
        for i in (5, 6):
            self.pick(i, conf, 'away')
        result = run_cut(self.season)
        self.assertEqual(result['after'], 4)
        self.assertEqual(PlayoffEntry.objects.filter(
            season=self.season, status=PlayoffEntry.ACTIVE).count(), 4)
        with self.assertRaises(PlayoffError):
            run_cut(self.season)

    def test_cut_waits_for_the_games_to_finish(self):
        open_playoffs(self.season, force=True)
        self.game(19, 'live', final=False)
        with self.assertRaises(PlayoffError):
            run_cut(self.season)
