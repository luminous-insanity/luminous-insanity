"""Pure helpers for "My insights" (no Django, easy to test)."""

MIN_SAMPLE = 3   # picks needed before a team/trend is called best or worst


def pct(wins, losses, ties):
    """Win percentage with ties as half a win; None with no graded picks."""
    games = wins + losses + ties
    if not games:
        return None
    return round((wins + 0.5 * ties) / games * 100, 1)


class Bucket:
    """A running win/loss/tie tally."""
    __slots__ = ('wins', 'losses', 'ties')

    def __init__(self):
        self.wins = self.losses = self.ties = 0

    def add(self, result):
        if result == 'win':
            self.wins += 1
        elif result == 'loss':
            self.losses += 1
        elif result == 'tie':
            self.ties += 1

    @property
    def games(self):
        return self.wins + self.losses + self.ties

    def as_dict(self):
        return {
            'wins': self.wins, 'losses': self.losses, 'ties': self.ties,
            'games': self.games, 'pct': pct(self.wins, self.losses, self.ties),
        }


def records_before_weeks(games):
    """Each team's (wins, losses, ties) going INTO each week.

    games: iterable of (week, home, away, home_score, away_score) for final games.
    Returns {week: {team: (w, l, t)}} covering every week that has a game, so a
    pick can be judged by what was known when it was made, not by today's record.
    """
    by_week = {}
    for week, home, away, home_score, away_score in games:
        by_week.setdefault(week, []).append((home, away, home_score, away_score))
    running = {}
    snapshots = {}
    for week in sorted(by_week):
        snapshots[week] = {team: tuple(rec) for team, rec in running.items()}
        for home, away, home_score, away_score in by_week[week]:
            for team, mine, theirs in ((home, home_score, away_score),
                                       (away, away_score, home_score)):
                rec = running.setdefault(team, [0, 0, 0])
                if mine > theirs:
                    rec[0] += 1
                elif mine < theirs:
                    rec[1] += 1
                else:
                    rec[2] += 1
    return snapshots


def favorite_from_records(home_record, away_record):
    """'home' / 'away' by better record so far, or None if unknown or level."""
    if not home_record or not away_record:
        return None
    home_pct = pct(*home_record)
    away_pct = pct(*away_record)
    if home_pct is None or away_pct is None or home_pct == away_pct:
        return None
    return 'home' if home_pct > away_pct else 'away'


def crowd_side(home_picks, away_picks, minimum=3):
    """'home' / 'away' for the majority of players, None if too few or split."""
    if home_picks + away_picks < minimum or home_picks == away_picks:
        return None
    return 'home' if home_picks > away_picks else 'away'


def best_and_worst(table, minimum=MIN_SAMPLE):
    """From {name: Bucket} pick the highest and lowest win% with enough picks.

    Returns (best, worst) as (name, dict) or None. Equal best/worst (only one
    team qualifies) returns that team as best and None for worst.
    """
    rated = [(name, bucket.as_dict()) for name, bucket in table.items()
             if bucket.games >= minimum]
    if not rated:
        return None, None
    rated.sort(key=lambda item: (-item[1]['pct'], -item[1]['games'], item[0]))
    best, worst = rated[0], rated[-1]
    if best[0] == worst[0] or best[1]['pct'] == worst[1]['pct']:
        return best, None
    return best, worst
