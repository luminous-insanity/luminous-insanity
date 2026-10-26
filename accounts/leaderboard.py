"""
Leaderboard building blocks.

Everything here sits ON TOP of accounts/standings.py. Wins, losses and ties are
still worked out by compute_standings() / _tally() / _final_picks() from picks
and final scores, so there are still no running totals to get out of sync.
"""
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Max, Q
from django.utils import timezone

from api.models import Game
from api.rules import grade_pick
from api.services import MAX_WEEK, current_week

from .models import ChampionRevealSeen, FriendRequest, Pick, UserActivity
from .ranking import assign_ranks, format_pct, movement, record_gap
from .standings import compute_standings, standing_for

FILTER_ALL = "all"
FILTER_FRIENDS = "friends"
FILTERS = (FILTER_ALL, FILTER_FRIENDS)


def inactive_days():
    return getattr(settings, "LEADERBOARD_INACTIVE_DAYS", 60)


# ------------------------------------------------------------------ seasons --

def season_weeks(season):
    """Weeks that have games loaded for this season, e.g. [1, 2, 3, 4, 5]."""
    return sorted(
        Game.objects.filter(season=season)
        .order_by().values_list("week", flat=True).distinct()
    )


def latest_completed_week(season):
    """Latest week with at least one final game; None if nothing has finished."""
    return Game.objects.filter(
        season=season, status=Game.FINAL,
    ).aggregate(latest=Max("week"))["latest"]


def default_week(season):
    """Weekly tab opens here: the latest week with completed games."""
    week = latest_completed_week(season)
    if week is not None:
        return week
    weeks = season_weeks(season)
    return weeks[0] if weeks else 1


def week_is_complete(season, week):
    games = Game.objects.filter(season=season, week=week)
    return (
        games.exists()
        and not games.exclude(
            status=Game.FINAL,
            home_score__isnull=False,
            away_score__isnull=False,
        ).exists()
    )


def season_is_finalized(season):
    """A season is final only when all 18 regular-season weeks are loaded,
    every week has at least one game, and every game has a final score.

    Requiring the full schedule prevents a partial historical import from
    accidentally crowning a champion.
    """
    games = Game.objects.filter(season=season)
    if not games.exists():
        return False
    if games.exclude(
        status=Game.FINAL,
        home_score__isnull=False,
        away_score__isnull=False,
    ).exists():
        return False
    loaded_weeks = set(games.order_by().values_list('week', flat=True).distinct())
    return set(range(1, MAX_WEEK + 1)).issubset(loaded_weeks)


# ------------------------------------------------------ who is on the board --

def last_active_map():
    """{user_id: last meaningful activity}, falling back to last login / sign-up."""
    recorded = dict(UserActivity.objects.values_list("user_id", "last_active"))
    result = {}
    for user_id, last_login, joined in User.objects.values_list(
            "id", "last_login", "date_joined"):
        candidates = [d for d in (recorded.get(user_id), last_login, joined) if d]
        result[user_id] = max(candidates)
    return result


def participant_ids(season, week=None):
    """Players who made at least one pick in this season (or week)."""
    picks = Pick.objects.filter(game__season=season)
    if week is not None:
        picks = picks.filter(game__week=week)
    return set(picks.order_by().values_list("user_id", flat=True).distinct())


def _is_live(season, week=None):
    """Is this the board for the season/week that's being played right now?"""
    if season != settings.NFL_SEASON or season_is_finalized(season):
        return False
    return week is None or week >= current_week()


def eligible_users(season, week=None, now=None):
    """
    Players who belong on this board.

    * Live Season board: everyone active in the last 60 days. Inactive accounts
      drop off, and come straight back the moment they log in or pick again.
    * Live Weekly board: active players, plus anyone who picked that week.
    * Anything historical (old seasons, finished weeks, finalized seasons):
      the players who actually took part. Their records are never touched.
    """
    now = now or timezone.now()
    users = User.objects.filter(is_superuser=False)
    participants = participant_ids(season, week)

    if not _is_live(season, week):
        return list(users.filter(id__in=participants))

    cutoff = now - timedelta(days=inactive_days())
    active = {uid for uid, when in last_active_map().items() if when >= cutoff}
    wanted = active | participants if week is not None else active
    return list(users.filter(id__in=wanted))


def friend_users(user):
    """Accepted friends of `user` (not including `user`)."""
    if user is None or not user.is_authenticated:
        return []
    accepted = FriendRequest.objects.filter(
        status=FriendRequest.ACCEPTED,
    ).filter(Q(sender=user) | Q(receiver=user)).select_related("sender", "receiver")
    return [
        fr.receiver if fr.sender_id == user.id else fr.sender
        for fr in accepted
    ]


# ------------------------------------------------------------- the boards --

def _stats_for(rows, season):
    """{user_id: season Standing} so each player menu can show extra stats."""
    return {
        s.user.id: s
        for s in compute_standings(
            season=season, users=[r.user for r in rows])
    }


def previous_week_ranks(users, season, week):
    """{user_id: rank} from the previous week's final standings, among `users`."""
    if week is None or week <= 1:
        return {}
    rows = [r for r in compute_standings(week=week - 1, season=season, users=users)
            if r.completed > 0]
    assign_ranks(rows)
    return {r.user.id: r.rank for r in rows}


def winners_of(rows):
    """Everyone tied for first place, if first place has actually won something."""
    top = [r for r in rows if r.rank == 1]
    if top and all(r.wins > 0 for r in top):
        return top
    return []


def build_board(*, tab, season, week, mode, viewer):
    """
    Returns a dict:
      rows          ranked Standings (with .pending and, on Weekly, movement)
      season_stats  {user_id: season Standing} for the player menu
      winners       players tied for first (Weekly banner)
      friends_empty True when Friends is chosen but there are no friends yet
      needs_login   True when Friends is chosen by a visitor who isn't logged in
    """
    weekly = tab == "weekly"
    users = eligible_users(season, week if weekly else None)

    friends_empty = needs_login = False
    if mode == FILTER_FRIENDS:
        if viewer is None or not viewer.is_authenticated:
            needs_login = True
            users = []
        else:
            friends = friend_users(viewer)
            if not friends:
                friends_empty = True
                users = []
            else:
                keep = {f.id for f in friends} | {viewer.id}
                # You are always part of your own competition.
                users = [u for u in users if u.id in keep]

    rows = compute_standings(
        week=week if weekly else None, season=season,
        users=users, with_pending=True)

    if weekly:
        previous = previous_week_ranks(users, season, week)
        for row in rows:
            row.movement_kind, row.movement_label = movement(
                row.rank, previous.get(row.user.id), week)

    return {
        "rows": rows,
        "season_stats": _stats_for(rows, season) if weekly else {r.user.id: r for r in rows},
        "winners": winners_of(rows) if weekly else [],
        "friends_empty": friends_empty,
        "needs_login": needs_login,
    }


# ---------------------------------------------------------------- champion --

def season_champions(season):
    """Co-champions (usually one). Empty until the season is finalized."""
    if not season_is_finalized(season):
        return []
    rows = [r for r in compute_standings(
                season=season, users=eligible_users(season))
            if r.completed > 0]
    assign_ranks(rows)
    return [r for r in rows if r.rank == 1]


def champion_payload(season):
    champions = season_champions(season)
    if not champions:
        return None
    return {
        "season": season,
        "champions": [
            {
                "username": c.user.username,
                "record": f"{c.wins}–{c.losses}–{c.ties}",
                "pct": format_pct(c.win_pct),
            }
            for c in champions
        ],
        "co_champions": len(champions) > 1,
    }


def should_auto_reveal(user, season, champion):
    """True exactly once per user per season; records that they've now seen it."""
    if champion is None or user is None or not user.is_authenticated:
        return False
    _, created = ChampionRevealSeen.objects.get_or_create(user=user, season=season)
    return created


# -------------------------------------------------------------- comparison --

RESULT_LABELS = {"win": "Correct", "loss": "Incorrect", "tie": "Tie"}


def _result(game, side):
    """('none'|'pending'|'win'|'loss'|'tie', label) for one pick on one game."""
    if side is None:
        return ("none", "No pick yet")
    if not game.is_final:
        return ("pending", "Pending")
    outcome = grade_pick(side, game.home_score, game.away_score)
    if outcome is None:
        return ("pending", "Pending")
    return (outcome, RESULT_LABELS[outcome])


def _team(game, side):
    if side == Pick.HOME:
        return game.home_team
    if side == Pick.AWAY:
        return game.away_team
    return None


def build_comparison(me, other, season, week):
    """
    Side-by-side picks for one week.

    Visibility rule: friends can always see each other's picks, even before
    kickoff (that's part of the strategy). Anyone who is NOT your friend is
    only revealed once that game's picks lock, and until then shows as hidden
    and is NOT counted as a difference.
    Missing picks are counted separately and are never disagreements.
    """
    are_friends = other.id in {f.id for f in friend_users(me)}
    games = list(
        Game.objects.filter(season=season, week=week)
        .order_by("game_date", "kickoff", "id"))
    by_user = {me.id: {}, other.id: {}}
    for pick in Pick.objects.filter(user__in=[me, other], game__in=games):
        by_user[pick.user_id][pick.game_id] = pick.team_picked

    rows = []
    differ = hidden = my_missing = their_missing = 0
    for game in games:
        mine = by_user[me.id].get(game.id)
        theirs = by_user[other.id].get(game.id)
        reveal = are_friends or game.has_started or game.is_final
        theirs_hidden = theirs is not None and not reveal

        if mine is None:
            my_missing += 1
        if theirs is None:
            their_missing += 1
        if theirs_hidden:
            hidden += 1

        differs = (mine is not None and theirs is not None
                   and reveal and mine != theirs)
        differ += differs

        their_state, their_label = (
            ("hidden", "Hidden until kickoff") if theirs_hidden
            else _result(game, theirs))
        my_state, my_label = _result(game, mine)
        rows.append({
            "game": game,
            "my_team": _team(game, mine),
            "my_state": my_state,
            "my_label": my_label,
            "their_team": None if theirs_hidden else _team(game, theirs),
            "their_state": their_state,
            "their_label": their_label,
            "differs": differs,
        })

    my_week = standing_for(me, week=week, season=season)
    their_week = standing_for(other, week=week, season=season)
    my_season = standing_for(me, season=season)
    their_season = standing_for(other, season=season)
    gap_who, gap_text = record_gap(my_season.record, their_season.record)

    return {
        "rows": rows,
        "are_friends": are_friends,
        "differ": differ,
        "hidden": hidden,
        "my_missing": my_missing,
        "their_missing": their_missing,
        "my_week": my_week,
        "their_week": their_week,
        "my_season": my_season,
        "their_season": their_season,
        "gap_who": gap_who,
        "gap_text": gap_text,
    }
