"""The Score is Right tiebreaker: games, guesses and weekly ranking.

Rules live in tiebreaker_rules.py. This file connects them to the database.

Which game is the tiebreaker? Staff can pick one per week in admin
(TiebreakerGame). Otherwise it is the last game of the week, normally
Monday night. Guesses are open until that game locks, the same moment its
picks lock. The tiebreaker only ever separates players who are LEVEL on
wins, losses and ties; it never changes anyone's record.
"""
from api.models import Game

from .models import TiebreakerGame, TiebreakerPick
from .ranking import rank_key
from .tiebreaker_rules import MAX_GUESS, describe, order_group


class TiebreakerError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def tiebreaker_game(season, week):
    """The game used to break ties for this week, or None if the week is empty."""
    override = TiebreakerGame.objects.filter(
        season=season, week=week).select_related('game').first()
    if override is not None:
        return override.game
    return (Game.objects.filter(season=season, week=week)
            .order_by('game_date', 'kickoff', 'id').last())


def actual_total(game):
    """Combined final score, or None until the game is final."""
    if game is not None and game.is_final:
        return game.home_score + game.away_score
    return None


def parse_guess(raw):
    """Turn form/JSON input into a valid whole number or raise TiebreakerError."""
    if isinstance(raw, bool):
        raise TiebreakerError('Enter the combined score as a whole number.')
    try:
        text = str(raw).strip()
        if not text.lstrip('-').isdigit():
            raise ValueError
        value = int(text)
    except (TypeError, ValueError):
        raise TiebreakerError('Enter the combined score as a whole number.')
    if value < 0 or value > MAX_GUESS:
        raise TiebreakerError(f'Enter a total between 0 and {MAX_GUESS}.')
    return value


def save_guess(user, game, raw_value):
    """Save or change a player's guess. Enforced on the server, like picks."""
    value = parse_guess(raw_value)
    if game.has_started:
        raise TiebreakerError('The tiebreaker game has started. Guesses are locked.', status=403)
    pick, _created = TiebreakerPick.objects.update_or_create(
        user=user, game=game, defaults={'total_points': value})
    return pick


def weekly_card(user, season, week):
    """Everything the picks page and API need for one week's tiebreaker.

    Returns None when the week has no games.
    """
    game = tiebreaker_game(season, week)
    if game is None:
        return None
    guess = None
    if user is not None and user.is_authenticated:
        guess = TiebreakerPick.objects.filter(user=user, game=game).values_list(
            'total_points', flat=True).first()
    actual = actual_total(game)
    return {
        'game': game,
        'game_id': game.game_id,
        'label': f'{game.away_team} @ {game.home_team}',
        'locked': game.has_started,
        'guess': guess,
        'actual': actual,
        'result': describe(guess, actual) if actual is not None else '',
    }


def apply_weekly_tiebreaker(rows, season, week):
    """Break ties on a WEEKLY board.

    rows: standings already sorted best-first with ranks assigned from
    wins/losses/ties. Returns the rows (re-ordered inside tied groups, ranks
    updated) once the tiebreaker game is final and at least one tied player
    guessed. Otherwise returns the rows unchanged, so a week nobody guessed
    behaves exactly as before: tied players share a rank.
    """
    if season is None or week is None or not rows:
        return rows
    game = tiebreaker_game(season, week)
    actual = actual_total(game)
    if actual is None:
        return rows
    guesses = dict(TiebreakerPick.objects.filter(
        game=game, user_id__in=[row.user.id for row in rows],
    ).values_list('user_id', 'total_points'))
    if not guesses:
        return rows

    result = []
    start = 0
    total = len(rows)
    while start < total:
        end = start
        key = rank_key(rows[start])
        while end < total and rank_key(rows[end]) == key:
            end += 1
        group = rows[start:end]
        tied_and_playing = len(group) > 1 and group[0].completed > 0
        if tied_and_playing and any(row.user.id in guesses for row in group):
            # Usernames are unique, so they identify rows inside the group.
            by_name = {row.user.username: row for row in group}
            ordered = order_group(
                [(row.user.username, guesses.get(row.user.id)) for row in group], actual)
            for name, guess, offset in ordered:
                row = by_name[name]
                row.rank = start + offset + 1
                row.tiebreak_guess = guess
                row.tiebreak_label = describe(guess, actual)
                result.append(row)
        else:
            result.extend(group)
        start = end
    return result
