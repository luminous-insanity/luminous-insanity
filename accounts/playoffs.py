"""Division and league-wide playoff qualification from finalized season results."""
from django.conf import settings
from django.contrib.auth.models import User

from api.models import Game
from .models import PlayerIdentity, PlayoffSettings
from .standings import compute_standings
from .challenges import records as challenge_records

REGULAR_SEASON_WEEKS = 18  # games after this week are playoff games

DIVISIONS = (
    'AFC East', 'AFC North', 'AFC South', 'AFC West',
    'NFC East', 'NFC North', 'NFC South', 'NFC West',
)


def _season_state(season):
    games = Game.objects.filter(season=season, week__lte=REGULAR_SEASON_WEEKS)
    total_games = games.count()
    unfinished = games.exclude(
        status=Game.FINAL, home_score__isnull=False, away_score__isnull=False
    )
    return total_games > 0 and not unfinished.exists(), total_games, unfinished.count()


def wildcard_score(wins, losses, ties, season_picks):
    """Win % x sqrt(picks made / season picks).

    Rewards consistent participation with diminishing returns, so a lucky
    short streak cannot beat an established player, but a strong late joiner
    can still beat a mediocre one. Ties count as half a win.
    """
    picks = wins + losses + ties
    if picks < 1 or season_picks < 1:
        return 0.0
    win_pct = (wins + 0.5 * ties) / picks
    return win_pct * (min(picks, season_picks) / season_picks) ** 0.5


def division_playoff_race(division, season=None):
    """Return division standings annotated by the dynamic qualification rules.

    There is no separate fixed-qualifier / division-wildcard system. The
    active-player algorithm determines the field and each player's route.
    """
    season = season or settings.NFL_SEASON
    season_complete, total_games, pending_games = _season_state(season)

    member_ids = PlayerIdentity.objects.filter(
        division=division, division_season=season, user__is_superuser=False
    ).values_list('user_id', flat=True)
    members = list(User.objects.filter(id__in=member_ids).order_by('username'))
    rows = compute_standings(
        season=season, users=members, with_pending=True,
        through_week=REGULAR_SEASON_WEEKS,
    )

    from .django_adapter import run_qualification
    result = run_qualification(season, write_entries=False)
    qualified_by_id = {p.user_id: p for p in result.qualified}
    division_seats = result.seats_by_division.get(division, 0)
    qualified_in_division = [
        p for p in result.qualified if p.division == division
    ]

    for index, row in enumerate(rows):
        player = qualified_by_id.get(row.user.id)
        row.wildcard_score = wildcard_score(
            row.wins, row.losses, row.ties, total_games
        )
        row.playoff_qualified = player is not None
        row.qualification_route = player.qualification_route if player else ''
        row.division_wildcard = bool(
            player and player.qualification_route == 'At-large wildcard'
        )
        row.head_to_head_wildcard = bool(
            player and player.qualification_route == 'Head-to-head wildcard'
        )
        row.playoff_rank = row.rank
        row.at_cutoff = bool(division_seats and row.rank == division_seats)
        row.playoff_status = 'qualified' if player else 'chasing'
        row.games_remaining = row.pending
        row.distance_from_cutoff = (
            max(0, row.rank - division_seats)
            if not row.playoff_qualified and division_seats else 0
        )
        row.players_ahead = rows[:index] if not row.playoff_qualified else []
        row.players_chased = rows[index + 1:index + 4]

    return {
        'standings': rows,
        'qualifiers_per_division': division_seats,
        'division_wildcard_spots': 0,
        'head_to_head_wildcard_spots': result.h2h_seats,
        'season_complete': season_complete,
        'qualification_final': season_complete,
        'total_games': total_games,
        'pending_games': pending_games,
        'active_players': result.N,
        'field_size': result.E,
        'qualified_in_division': len(qualified_in_division),
    }


def championship_bracket(season=None, field_size=None):
    """Build the playoff preview from the dynamic qualification algorithm.

    `field_size` is retained for compatibility with existing callers, but it
    no longer controls qualification. The algorithm's E(N) determines the field.
    """
    from .django_adapter import run_qualification

    season = season or settings.NFL_SEASON
    result = run_qualification(season, write_entries=False)
    field = []
    users_by_id = User.objects.in_bulk([p.user_id for p in result.qualified])
    for seed, p in enumerate(result.qualified, start=1):
        graded = p.wins + p.losses + p.ties
        field.append({
            'user_id': p.user_id,
            'user': users_by_id[p.user_id],
            'division': p.division,
            'record': f'{p.wins}-{p.losses}-{p.ties}',
            'wins': p.wins,
            'losses': p.losses,
            'ties': p.ties,
            'win_pct': ((p.wins + 0.5 * p.ties) / graded) if graded else 0.0,
            'division_rank': None,
            'qualification_route': p.qualification_route,
            'head_to_head_wins': int(p.h2h_credit),
            'seed': seed,
        })

    count = len(field)
    bracket_size = 1
    while bracket_size < max(count, 2):
        bracket_size *= 2
    byes_count = max(0, count - bracket_size // 2)
    first_round = []
    if count > 1:
        entrants = field[byes_count:]
        half = len(entrants) // 2
        for i in range(half):
            first_round.append({'high': entrants[i], 'low': entrants[-(i + 1)], 'winner': None})

    season_complete, total_games, pending_games = _season_state(season)
    return {
        'season': season,
        'field_size': result.E,
        'field': field,
        'field_count': count,
        'slots_open': max(0, result.E - count),
        'divisions': [],
        'first_round': first_round,
        'byes': field[:byes_count],
        'round_one_winner_count': len(first_round),
        'bracket_size': bracket_size,
        'head_to_head_wildcard_spots': result.h2h_seats,
        'is_provisional': not season_complete,
        'active_players': result.N,
        'qualification_diagnostics': {
            'division_seats': result.division_seats,
            'at_large_seats': result.at_large_seats,
            'h2h_seats': result.h2h_seats,
            'division_filled': result.division_filled,
            'at_large_filled': result.at_large_filled,
            'h2h_filled': result.h2h_filled,
            'rolled_down': result.rolled_down,
            'lapsed': result.lapsed,
        },
    }
