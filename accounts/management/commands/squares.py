"""
Run the Super Bowl squares board from the command line.

    python manage.py squares build              # deal squares + draw digits (after the 3rd cut)
    python manage.py squares build --rebuild    # redo it (changes everyone's squares!)
    python manage.py squares game --home KC --away PHI --date 2027-02-14
    python manage.py squares score --quarter 1 --home 7 --away 3
    python manage.py squares status

`game` is only needed until the score sync loads the postseason.
Quarters 1-3 are the running score at that point; quarter 4 is the FINAL score
(overtime included) and marks the game final.
"""
from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from accounts.models import SquaresBoard
from accounts.playoff_rounds import PlayoffError
from accounts.squares import (
    build_board, find_super_bowl_game, quarter_results, save_quarter_score, set_super_bowl_game,
)


class Command(BaseCommand):
    help = 'Build the squares board, enter quarter scores, or show the winners.'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['build', 'game', 'score', 'status'])
        parser.add_argument('--season', type=int, default=settings.NFL_SEASON)
        parser.add_argument('--rebuild', action='store_true')
        parser.add_argument('--force', action='store_true')
        parser.add_argument('--home', help='game: home team code. score: home score.')
        parser.add_argument('--away', help='game: away team code. score: away score.')
        parser.add_argument('--date', help='game: YYYY-MM-DD')
        parser.add_argument('--quarter', type=int, help='1, 2, 3, or 4 (4 = final score)')

    def handle(self, *args, **opts):
        season, action = opts['season'], opts['action']
        try:
            if action == 'build':
                board = build_board(season, rebuild=opts['rebuild'], force=opts['force'])
                self.stdout.write(self.style.SUCCESS(
                    f'Built the {season} board: 100 squares dealt to '
                    f'{board.squares.order_by().values("owner").distinct().count()} players.'))
            elif action == 'game':
                if not (opts['home'] and opts['away'] and opts['date']):
                    raise CommandError('game needs --home, --away and --date.')
                game = set_super_bowl_game(season, opts['home'].upper(), opts['away'].upper(),
                                           date.fromisoformat(opts['date']))
                self.stdout.write(self.style.SUCCESS(f'Super Bowl game set: {game}'))
            elif action == 'score':
                self.enter_score(season, opts)
            self.print_status(season)
        except (PlayoffError, ValueError) as exc:
            raise CommandError(str(exc))

    def enter_score(self, season, opts):
        board = SquaresBoard.objects.filter(season=season).first()
        game = (board.game if board else None) or find_super_bowl_game(season)
        if game is None:
            raise CommandError('No Super Bowl game yet. Run: squares game --home XX --away YY --date YYYY-MM-DD')
        try:
            home, away = int(opts['home']), int(opts['away'])
        except (TypeError, ValueError):
            raise CommandError('score needs whole numbers for --home and --away.')
        if opts['quarter'] not in (1, 2, 3, 4):
            raise CommandError('score needs --quarter 1, 2, 3 or 4.')
        save_quarter_score(game, opts['quarter'], home, away)
        if board and board.game_id != game.id:
            board.game = game
            board.save(update_fields=['game'])

    def print_status(self, season):
        board = SquaresBoard.objects.filter(season=season).first()
        if not board:
            self.stdout.write(f'{season}: no squares board yet.')
            return
        game = board.game or find_super_bowl_game(season)
        self.stdout.write(f'{season} board  |  columns (away): {board.away_digits}  |  rows (home): {board.home_digits}')
        self.stdout.write(f'Game: {game or "not linked yet"}')
        for r in quarter_results(board):
            if r['scored']:
                who = r['owner'].username if r['owner'] else 'nobody'
                self.stdout.write(f"  {r['label']:<10} {r['away_score']}-{r['home_score']}  "
                                  f"-> square (away {r['away_digit']}, home {r['home_digit']})  owner: {who}")
            else:
                self.stdout.write(f"  {r['label']:<10} not scored yet")
