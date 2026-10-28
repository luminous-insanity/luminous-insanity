import random
from collections import Counter
from datetime import date

from django.conf import settings
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from api.models import Game, QuarterScore

from .models import BoardSquare, PlayoffEntry, PlayoffSettings, SquaresBoard
from .playoff_rounds import CUTS, PlayoffError
from .squares import board_grid, build_board, quarter_results, save_quarter_score, set_super_bowl_game
from .squares_rules import draw_digits, split_squares, winning_cell


class SquaresRulesTests(SimpleTestCase):
    def test_fifty_players_get_two_squares_each(self):
        counts = Counter(split_squares(range(1, 51), random.Random(1)))
        self.assertEqual(set(counts.values()), {2})

    def test_uneven_split_gives_everyone_the_base_and_hands_out_the_rest(self):
        counts = Counter(split_squares([1, 2, 3], random.Random(1)))
        self.assertEqual(sorted(counts.values()), [33, 33, 34])

    def test_split_is_always_within_one_square(self):
        for n in (1, 2, 7, 33, 49, 51, 99, 100):
            counts = Counter(split_squares(range(n), random.Random(n)))
            self.assertEqual(sum(counts.values()), 100)
            self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)

    def test_more_players_than_squares_is_refused(self):
        with self.assertRaises(ValueError):
            split_squares(range(101), random.Random(1))

    def test_digits_are_a_shuffle_of_zero_to_nine(self):
        self.assertEqual(sorted(draw_digits(random.Random(3))), list('0123456789'))

    def test_winning_square_uses_last_digit_of_each_score(self):
        # 28 (away) to 21 (home): column with 8, row with 1.
        self.assertEqual(winning_cell('0123456789', '0123456789', 21, 28), (1, 8))
        self.assertEqual(winning_cell('9876543210', '0123456789', 21, 28), (8, 8))
        self.assertEqual(winning_cell('0123456789', '0123456789', 10, 0), (0, 0))


class SquaresBoardTests(TestCase):
    def setUp(self):
        self.season = settings.NFL_SEASON
        self.config = PlayoffSettings.objects.create(season=self.season, rounds_cut=CUTS)
        self.users = [User.objects.create_user(username=f'sb{i}') for i in range(3)]
        for user in self.users:
            PlayoffEntry.objects.create(user=user, season=self.season)
        gone = User.objects.create_user(username='cut_early')
        PlayoffEntry.objects.create(user=gone, season=self.season,
                                    status=PlayoffEntry.ELIMINATED, eliminated_round=1)
        self.gone = gone

    def test_build_deals_all_squares_only_to_active_players(self):
        board = build_board(self.season, rng=random.Random(1))
        self.assertEqual(board.squares.count(), 100)
        owners = set(board.squares.values_list('owner__username', flat=True))
        self.assertEqual(owners, {'sb0', 'sb1', 'sb2'})
        self.assertEqual(sorted(board.home_digits), list('0123456789'))
        self.assertEqual(sorted(board.away_digits), list('0123456789'))

    def test_board_cannot_be_redrawn_by_accident(self):
        build_board(self.season, rng=random.Random(1))
        with self.assertRaises(PlayoffError):
            build_board(self.season, rng=random.Random(2))
        board = build_board(self.season, rebuild=True, rng=random.Random(2))
        self.assertEqual(SquaresBoard.objects.count(), 1)
        self.assertEqual(board.squares.count(), 100)

    def test_board_waits_for_the_final_cut(self):
        self.config.rounds_cut = 1
        self.config.save()
        with self.assertRaises(PlayoffError):
            build_board(self.season, rng=random.Random(1))
        self.assertEqual(build_board(self.season, force=True, rng=random.Random(1)).squares.count(), 100)

    def test_quarter_winners_follow_the_scores(self):
        board = build_board(self.season, rng=random.Random(1))
        # Fix the digits so the expected squares are easy to read.
        board.home_digits = board.away_digits = '0123456789'
        board.save()
        game = set_super_bowl_game(self.season, 'KC', 'PHI', date(2027, 2, 14))
        board.refresh_from_db()
        self.assertEqual(board.game_id, game.id)

        save_quarter_score(game, 1, 7, 3)    # home 7, away 3 -> row 7, col 3
        save_quarter_score(game, 2, 14, 10)  # row 4, col 0
        results = quarter_results(board)
        q1 = results[0]
        self.assertTrue(q1['scored'])
        self.assertEqual((q1['row'], q1['col']), (7, 3))
        self.assertEqual(q1['owner'], BoardSquare.objects.get(board=board, row=7, col=3).owner)
        self.assertEqual((results[1]['row'], results[1]['col']), (4, 0))
        self.assertFalse(results[2]['scored'])   # Q3 not entered
        self.assertFalse(results[3]['scored'])   # not final yet

        save_quarter_score(game, 4, 31, 28)      # final, overtime included -> row 1, col 8
        board.refresh_from_db()                  # reload the game with its new final score
        final = quarter_results(board)[3]
        self.assertTrue(final['scored'])
        self.assertEqual((final['row'], final['col']), (1, 8))

    def test_quarter_scores_can_be_corrected(self):
        game = set_super_bowl_game(self.season, 'KC', 'PHI', date(2027, 2, 14))
        save_quarter_score(game, 1, 7, 3)
        save_quarter_score(game, 1, 10, 3)
        self.assertEqual(QuarterScore.objects.filter(game=game, quarter=1).count(), 1)
        self.assertEqual(QuarterScore.objects.get(game=game, quarter=1).home_score, 10)

    def test_grid_highlights_my_squares(self):
        board = build_board(self.season, rng=random.Random(1))
        data = board_grid(board, self.users[0])
        mine = sum(1 for row in data['rows'] for cell in row['cells'] if cell['mine'])
        self.assertEqual(mine, data['my_count'])
        self.assertIn(mine, (33, 34))
        self.assertEqual(data['player_count'], 3)

    def test_squares_page_renders_with_and_without_a_board(self):
        response = self.client.get('/squares/')
        self.assertContains(response, "hasn't been drawn yet")
        build_board(self.season, rng=random.Random(1))
        response = self.client.get('/squares/')
        self.assertContains(response, 'THE BOARD')
