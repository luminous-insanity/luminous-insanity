"""
Pure rules for the weekly playoff cuts. No Django in here on purpose, so the
rules can be tested on their own and read in one place.

Format: every playoff entrant starts 0-0. After each of the first rounds the
players with the worst playoff records are cut, stepping the field down to
exactly the Super Bowl size (50 by default).
"""
import hashlib


def cut_targets(start, target, cuts=3):
    """Field size left after each cut, ending on exactly `target`.

    The field shrinks by the same ratio each round, e.g. 200 -> 126 -> 79 -> 50.
    If the field is already at or under the target nobody is cut.
    """
    if cuts < 1:
        return []
    if start <= target:
        return [start] * cuts
    targets = []
    previous = start
    for step in range(1, cuts + 1):
        if step == cuts:
            size = target
        else:
            size = round(start * (target / start) ** (step / cuts))
            size = max(target, min(previous, size))
        targets.append(size)
        previous = size
    return targets


def tiebreak_draw(season, user_id):
    """A fixed pseudo-random number for one player in one season.

    Same inputs always give the same number, and it is stored when the field
    opens, so the last-resort tiebreak can't be re-rolled.
    """
    digest = hashlib.sha256(f'{season}:{user_id}:playoff-draw'.encode()).hexdigest()
    return int(digest[:15], 16)


def survival_key(wins, losses, ties, regular_win_pct, head_to_head_wins, draw):
    """Sort key, best player first.

    1. Playoff record so far (most wins, fewest losses, most ties).
    2. Regular-season pick percentage.
    3. Head-to-head challenge wins.
    4. The stored draw.
    """
    return (-wins, losses, -ties, -(regular_win_pct or 0), -head_to_head_wins, draw)


def split_field(entries, keep, key):
    """(survivors, cut) with exactly `keep` survivors, best first."""
    ordered = sorted(entries, key=key)
    return ordered[:keep], ordered[keep:]
