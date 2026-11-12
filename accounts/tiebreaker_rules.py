"""The Score is Right: pure tiebreaker rules (no Django, easy to test).

Every player may guess the combined final score of one game each week.
When players finish a week level on wins, losses and ties, the closest guess
WITHOUT GOING OVER ranks higher. Guesses that go over rank below every guess
that did not, and players with no guess rank last. Players whose guesses are
equally good (same side, same distance) stay tied and share a rank.
"""

MAX_GUESS = 200   # highest combined score a player may enter


def tiebreak_key(guess, actual):
    """Sort key where smaller is better.

    (0, n)  guessed n under the real score (or exactly right at n = 0)
    (1, n)  went over by n; only used when it is the best that's left
    (2, 0)  no guess
    """
    if guess is None:
        return (2, 0)
    if guess <= actual:
        return (0, actual - guess)
    return (1, guess - actual)


def describe(guess, actual):
    """Plain-English result of one guess against the real combined score."""
    if guess is None:
        return 'No guess'
    if guess == actual:
        return f'Guessed {guess}: exactly right!'
    if guess < actual:
        gap = actual - guess
        return f'Guessed {guess}: {gap} under'
    gap = guess - actual
    return f'Guessed {guess}: over by {gap}'


def order_group(entries, actual):
    """Order tied players by the rule above.

    entries: list of (name, guess_or_None).
    Returns [(name, guess, shared_offset), ...] best first. shared_offset is
    the 0-based position of the first player with an identical result, so the
    caller can turn it into a rank (1, 1, 3 style).
    """
    keyed = sorted(
        entries,
        key=lambda item: (tiebreak_key(item[1], actual), str(item[0]).lower()),
    )
    out = []
    previous = None
    offset = 0
    for position, (name, guess) in enumerate(keyed):
        key = tiebreak_key(guess, actual)
        if key != previous:
            offset = position
            previous = key
        out.append((name, guess, offset))
    return out
