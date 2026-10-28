"""
Pure rules for the Super Bowl squares board. No Django in here on purpose, so
the rules can be tested on their own and read in one place.

The board is 10 x 10. Columns run along the top and belong to the AWAY team;
rows run down the side and belong to the HOME team. The digits 0-9 are shuffled
onto each axis once, AFTER the squares have been handed out.

A quarter's winning square is found from the last digit of each score:
28 (away) to 21 (home) -> column with 8, row with 1.
"""

BOARD_SIZE = 10
TOTAL_SQUARES = BOARD_SIZE * BOARD_SIZE


def split_squares(player_ids, rng, total=TOTAL_SQUARES):
    """Owner id for each of `total` squares, dealt evenly and shuffled.

    50 players get 2 each. If the players don't divide 100 evenly, everybody
    gets the same base number and the leftover squares go to randomly chosen
    players (3 players -> 33, 33 and 34).
    """
    ids = sorted(player_ids)
    if not ids:
        raise ValueError('There are no players to give squares to.')
    if len(ids) > total:
        raise ValueError(f'{len(ids)} players is more than the {total} squares on the board.')
    base, extra = divmod(total, len(ids))
    owners = ids * base + rng.sample(ids, extra)
    rng.shuffle(owners)
    return owners


def draw_digits(rng):
    """The digits 0-9 in a random order, as a 10-character string."""
    digits = list(range(BOARD_SIZE))
    rng.shuffle(digits)
    return ''.join(str(d) for d in digits)


def winning_cell(home_digits, away_digits, home_score, away_score):
    """(row, col) of the square that wins at these scores."""
    row = home_digits.index(str(home_score % 10))
    col = away_digits.index(str(away_score % 10))
    return row, col
