"""
Head-to-head challenges.

A challenge is one player daring another on either a SINGLE GAME or a WHOLE
WEEK. The opponent has to accept. After that nothing is stored about the
result: it is worked out from both players' picks and the final scores, the
same way the leaderboard is.

Scoring
  Single game: a correct pick scores 1, a tied game 0.5, and an incorrect or
               missing pick 0. Higher score wins. Same pick = a tie.
  Whole week:  compares each player's record for the week, ranked like the
               leaderboard (most wins, then fewest losses, then most ties).
               It is decided once every game that week is final.
"""
from collections import defaultdict
from dataclasses import dataclass

from django.conf import settings
from django.db.models import Q

from api.models import Game
from api.rules import grade_pick

from .models import Challenge, Pick

OPEN_STATES = (Challenge.PENDING, Challenge.ACCEPTED)


class ChallengeError(ValueError):
    """A problem worth showing to the player, in plain words."""


@dataclass
class Result:
    state: str                 # pending | open | final | declined | cancelled | expired
    winner_id: int = None
    tie: bool = False
    challenger_score: str = ""
    opponent_score: str = ""

    def outcome_for(self, challenge, user_id):
        """'won', 'lost' or 'tied' for a finished challenge, else None."""
        if self.state != "final":
            return None
        if self.tie:
            return "tied"
        return "won" if self.winner_id == user_id else "lost"


# ----------------------------------------------------------------- creating --

def open_weeks(season):
    """Weeks that have games and aren't completely finished yet."""
    result = []
    for week in sorted(Game.objects.filter(season=season).order_by()
                       .values_list("week", flat=True).distinct()):
        games = Game.objects.filter(season=season, week=week)
        if games.exclude(status=Game.FINAL).exists():
            result.append(week)
    return result


def open_games(season):
    """Games nobody has started yet, so a challenge on them is still fair."""
    games = Game.objects.filter(season=season).exclude(status=Game.FINAL)
    return [g for g in games.order_by("week", "game_date", "kickoff", "id")
            if not g.has_started]


def create_challenge(challenger, opponent, scope, *, game=None, week=None):
    if opponent is None or opponent.is_superuser:
        raise ChallengeError("That player couldn't be found.")
    if opponent.id == challenger.id:
        raise ChallengeError("You can't challenge yourself.")

    season = settings.NFL_SEASON
    if scope == Challenge.GAME:
        if game is None or game.season != season:
            raise ChallengeError("Please choose a game from this season.")
        if game.is_final or game.has_started:
            raise ChallengeError("That game has already started. Pick one that hasn't kicked off yet.")
        week = game.week
    elif scope == Challenge.WEEK:
        if week not in open_weeks(season):
            raise ChallengeError("That week is already over or has no games yet.")
        game = None
    else:
        raise ChallengeError("Please choose a game or a whole week.")

    clash = Challenge.objects.filter(
        scope=scope, season=season, week=week, game=game,
        status__in=OPEN_STATES,
    ).filter(
        challenger__in=[challenger, opponent],
        opponent__in=[challenger, opponent],
    )
    if clash.exists():
        raise ChallengeError("There is already a challenge between you two for that.")

    return Challenge.objects.create(
        challenger=challenger, opponent=opponent,
        scope=scope, season=season, week=week, game=game,
    )


# ---------------------------------------------------------------- evaluating --

def _points(result):
    return {"win": 1, "tie": 0.5}.get(result, 0)


def _game_label(game, side):
    if side is None:
        return "No pick"
    if not game.is_final:
        return "Pending"
    return {"win": "Correct", "loss": "Incorrect", "tie": "Tie"}.get(
        grade_pick(side, game.home_score, game.away_score), "Pending")


def evaluate_many(challenges):
    """{challenge.id: Result}. A handful of queries however many challenges."""
    challenges = list(challenges)
    live = [c for c in challenges if c.status in OPEN_STATES]

    game_ids = {c.game_id for c in live if c.scope == Challenge.GAME}
    week_keys = {(c.season, c.week) for c in live if c.scope == Challenge.WEEK}
    user_ids = {u for c in live for u in (c.challenger_id, c.opponent_id)}

    games = Game.objects.in_bulk(game_ids) if game_ids else {}
    single_picks = {}
    if game_ids:
        for user_id, game_id, side in Pick.objects.filter(
                game_id__in=game_ids, user_id__in=user_ids,
        ).values_list("user_id", "game_id", "team_picked"):
            single_picks[(user_id, game_id)] = side

    week_games = defaultdict(list)
    week_tally = defaultdict(lambda: defaultdict(lambda: [0, 0, 0]))
    if week_keys:
        seasons = {s for s, _ in week_keys}
        weeks = {w for _, w in week_keys}
        for game in Game.objects.filter(season__in=seasons, week__in=weeks):
            if (game.season, game.week) in week_keys:
                week_games[(game.season, game.week)].append(game)
        for user_id, season, week, side, home, away in Pick.objects.filter(
                game__season__in=seasons, game__week__in=weeks,
                user_id__in=user_ids,
                game__status=Game.FINAL,
                game__home_score__isnull=False, game__away_score__isnull=False,
        ).values_list("user_id", "game__season", "game__week",
                      "team_picked", "game__home_score", "game__away_score"):
            if (season, week) not in week_keys:
                continue
            index = {"win": 0, "loss": 1, "tie": 2}.get(
                grade_pick(side, home, away))
            if index is not None:
                week_tally[(season, week)][user_id][index] += 1

    results = {}
    for c in challenges:
        if c.status == Challenge.DECLINED:
            results[c.id] = Result("declined")
            continue
        if c.status == Challenge.CANCELLED:
            results[c.id] = Result("cancelled")
            continue

        if c.scope == Challenge.GAME:
            game = games.get(c.game_id)
            over = game is None or game.is_final
            started = game is None or game.has_started or game.is_final
            mine = single_picks.get((c.challenger_id, c.game_id))
            theirs = single_picks.get((c.opponent_id, c.game_id))
            if c.status == Challenge.PENDING:
                results[c.id] = Result("expired" if started else "pending")
                continue
            c_score, o_score = _game_label(game, mine), _game_label(game, theirs)
            if not over:
                results[c.id] = Result("open", challenger_score=c_score,
                                       opponent_score=o_score)
                continue
            c_key = (-_points(grade_pick(mine, game.home_score, game.away_score) if mine else None),)
            o_key = (-_points(grade_pick(theirs, game.home_score, game.away_score) if theirs else None),)
        else:
            key = (c.season, c.week)
            finished = bool(week_games[key]) and all(g.is_final for g in week_games[key])
            if c.status == Challenge.PENDING:
                results[c.id] = Result("expired" if finished else "pending")
                continue
            c_rec = week_tally[key][c.challenger_id]
            o_rec = week_tally[key][c.opponent_id]
            c_score = "–".join(map(str, c_rec))
            o_score = "–".join(map(str, o_rec))
            if not finished:
                results[c.id] = Result("open", challenger_score=c_score,
                                       opponent_score=o_score)
                continue
            # Most wins, then fewest losses, then most ties (lower key is better).
            c_key = (-c_rec[0], c_rec[1], -c_rec[2])
            o_key = (-o_rec[0], o_rec[1], -o_rec[2])

        if c_key == o_key:
            results[c.id] = Result("final", tie=True,
                                   challenger_score=c_score, opponent_score=o_score)
        else:
            winner = c.challenger_id if c_key < o_key else c.opponent_id
            results[c.id] = Result("final", winner_id=winner,
                                   challenger_score=c_score, opponent_score=o_score)
    return results


def records(user_ids=None, season=None):
    """{user_id: [won, lost, tied]} over finished challenges, optionally by season."""
    accepted = Challenge.objects.filter(status=Challenge.ACCEPTED)
    if season is not None:
        accepted = accepted.filter(season=season)
    if user_ids is not None:
        accepted = accepted.filter(
            Q(challenger_id__in=user_ids) | Q(opponent_id__in=user_ids))
    accepted = list(accepted)
    results = evaluate_many(accepted)

    table = defaultdict(lambda: [0, 0, 0])
    for c in accepted:
        for user_id in (c.challenger_id, c.opponent_id):
            outcome = results[c.id].outcome_for(c, user_id)
            if outcome:
                table[user_id][{"won": 0, "lost": 1, "tied": 2}[outcome]] += 1
    return table


def record_between(a, b):
    """[a_won, a_lost, tied] across finished challenges between two players."""
    both = Challenge.objects.filter(
        status=Challenge.ACCEPTED,
        challenger__in=[a, b], opponent__in=[a, b],
    )
    both = list(both)
    results = evaluate_many(both)
    record = [0, 0, 0]
    for c in both:
        outcome = results[c.id].outcome_for(c, a.id)
        if outcome:
            record[{"won": 0, "lost": 1, "tied": 2}[outcome]] += 1
    return record


def incoming_pending(user):
    """How many live challenges are waiting for `user` to answer."""
    waiting = list(Challenge.objects.filter(
        opponent=user, status=Challenge.PENDING).select_related("game"))
    results = evaluate_many(waiting)
    return sum(1 for c in waiting if results[c.id].state == "pending")
