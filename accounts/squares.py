"""Super Bowl squares: build the board and work out each quarter's winner.

Nothing about winners is stored. Like the leaderboard, they are worked out
from the board and the scores every time, so a score correction fixes the
result automatically.

Quarter scores 1-3 come from api.QuarterScore (end of Q1, halftime, end of
Q3). The "Final" square uses the game's own final score, overtime included.
"""
import random

from django.conf import settings
from django.db import transaction

from api.models import Game, QuarterScore

from .models import BoardSquare, PlayoffEntry, SquaresBoard
from .playoff_rounds import CUTS, PlayoffError, get_config, round_week
from .squares_rules import BOARD_SIZE, draw_digits, split_squares, winning_cell

QUARTER_LABELS = {1: 'End of Q1', 2: 'Halftime', 3: 'End of Q3', 4: 'Final'}


def find_super_bowl_game(season, config=None):
    config = config or get_config(season)
    return (Game.objects.filter(season=season, week=round_week(config, 4))
            .order_by('id').first())


@transaction.atomic
def build_board(season=None, rebuild=False, force=False, rng=None):
    """Deal the squares to the active playoff players, then draw the digits.

    Only the players left after the final cut get squares. The digits are
    drawn after the deal and then stored, so they can't be re-rolled by
    accident: an existing board is refused unless rebuild=True.
    """
    season = season or settings.NFL_SEASON
    config = get_config(season)
    if config.rounds_cut < CUTS and not force:
        raise PlayoffError(
            f'Only {config.rounds_cut} of {CUTS} cuts are done. Finish the cuts first, '
            f'or use --force to build the board with the current players.')

    existing = SquaresBoard.objects.filter(season=season).first()
    if existing and not rebuild:
        raise PlayoffError(
            f'The {season} board already exists. Use --rebuild to redraw it '
            f'(this changes everyone\'s squares).')

    player_ids = list(PlayoffEntry.objects.filter(
        season=season, status=PlayoffEntry.ACTIVE).values_list('user_id', flat=True))
    if not player_ids:
        raise PlayoffError('There are no active playoff players to give squares to.')
    try:
        # SystemRandom: nobody can work the result out in advance.
        rng = rng or random.SystemRandom()
        owners = split_squares(player_ids, rng)
    except ValueError as exc:
        raise PlayoffError(str(exc))
    home_digits, away_digits = draw_digits(rng), draw_digits(rng)

    if existing:
        existing.squares.all().delete()
        board = existing
        board.home_digits, board.away_digits = home_digits, away_digits
        board.game = board.game or find_super_bowl_game(season, config)
        board.save()
    else:
        board = SquaresBoard.objects.create(
            season=season, game=find_super_bowl_game(season, config),
            home_digits=home_digits, away_digits=away_digits)

    BoardSquare.objects.bulk_create([
        BoardSquare(board=board, row=index // BOARD_SIZE, col=index % BOARD_SIZE, owner_id=owner_id)
        for index, owner_id in enumerate(owners)
    ])
    return board


def set_super_bowl_game(season, home_team, away_team, game_date):
    """Create (or update) a hand-entered Super Bowl game and link the board to it.

    The score sync doesn't load the postseason yet, so this lets you enter
    quarter scores by hand. When the sync is extended, point the board at the
    synced game in admin and delete this one.
    """
    config = get_config(season)
    game, _ = Game.objects.update_or_create(
        game_id=f'manual-{season}-superbowl',
        defaults={'season': season, 'week': round_week(config, 4),
                  'home_team': home_team, 'away_team': away_team,
                  'game_date': game_date})
    SquaresBoard.objects.filter(season=season).update(game=game)
    return game


def save_quarter_score(game, quarter, home_score, away_score):
    """Quarters 1-3 go in QuarterScore. Quarter 4 is the game's final score."""
    if quarter in (1, 2, 3):
        return QuarterScore.objects.update_or_create(
            game=game, quarter=quarter,
            defaults={'home_score': home_score, 'away_score': away_score,
                      'source': QuarterScore.MANUAL})[0]
    if quarter == 4:
        game.home_score, game.away_score, game.status = home_score, away_score, Game.FINAL
        game.save(update_fields=['home_score', 'away_score', 'status'])
        return game
    raise ValueError('Quarter must be 1, 2, 3 or 4 (4 = final score).')


def quarter_results(board):
    """One dict per quarter: scores, winning square and owner (when scored)."""
    game = board.game or find_super_bowl_game(board.season)
    scores = {}
    if game:
        for q in QuarterScore.objects.filter(game=game):
            scores[q.quarter] = (q.home_score, q.away_score)
        if game.is_final:
            scores[4] = (game.home_score, game.away_score)
    owners = {(s.row, s.col): s.owner for s in board.squares.select_related('owner')}

    results = []
    for quarter in (1, 2, 3, 4):
        item = {'quarter': quarter, 'label': QUARTER_LABELS[quarter], 'scored': quarter in scores,
                'home_score': None, 'away_score': None, 'home_digit': None, 'away_digit': None,
                'row': None, 'col': None, 'owner': None}
        if quarter in scores and board.home_digits and board.away_digits:
            home, away = scores[quarter]
            row, col = winning_cell(board.home_digits, board.away_digits, home, away)
            item.update(home_score=home, away_score=away, home_digit=home % 10,
                        away_digit=away % 10, row=row, col=col, owner=owners.get((row, col)))
        results.append(item)
    return results


def board_grid(board, user=None):
    """Everything the squares page needs, ready for the template."""
    game = board.game or find_super_bowl_game(board.season)
    results = quarter_results(board)
    wins = {}
    for r in results:
        if r['row'] is not None:
            wins.setdefault((r['row'], r['col']), []).append(r['label'])
    by_cell = {(s.row, s.col): s.owner for s in board.squares.select_related('owner')}
    my_id = user.id if user is not None and user.is_authenticated else None

    rows = []
    for row in range(BOARD_SIZE):
        cells = []
        for col in range(BOARD_SIZE):
            owner = by_cell.get((row, col))
            cells.append({
                'owner': owner.username if owner else '',
                'mine': bool(owner and owner.id == my_id),
                'wins': wins.get((row, col), []),
            })
        rows.append({'digit': board.home_digits[row] if board.home_digits else '?', 'cells': cells})
    return {
        'board': board, 'game': game, 'results': results, 'rows': rows,
        'away_digits': list(board.away_digits) if board.away_digits else ['?'] * BOARD_SIZE,
        'home_team': game.home_team if game else 'Home',
        'away_team': game.away_team if game else 'Away',
        'my_count': sum(1 for r in rows for c in r['cells'] if c['mine']),
        'player_count': len({o for o in by_cell.values() if o}),
    }
