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
    """Return division standings with automatic spots and one performance wildcard."""
    season = season or settings.NFL_SEASON
    config = PlayoffSettings.objects.filter(season=season).first()
    qualifiers = config.qualifiers_per_division if config else 4
    season_complete, total_games, pending_games = _season_state(season)

    member_ids = PlayerIdentity.objects.filter(
        division=division, division_season=season, user__is_superuser=False
    ).values_list('user_id', flat=True)
    members = list(User.objects.filter(id__in=member_ids).order_by('username'))
    if config and config.qualifier_percent:
        # Percentage mode: the same share of every division, at least one player.
        qualifiers = max(1, int(len(members) * config.qualifier_percent / 100 + 0.5))  # round half up
    rows = compute_standings(season=season, users=members, with_pending=True,
                             through_week=REGULAR_SEASON_WEEKS)

    # Automatic qualifiers are based on the existing leaderboard rank. Tied
    # players at the cutoff all remain in position, consistent with Division Wars.
    for row in rows:
        row.qualification_route = ''
        row.division_wildcard = False
        row.head_to_head_wildcard = False
        row.playoff_qualified = bool(row.rank <= qualifiers)
        if row.playoff_qualified:
            row.qualification_route = 'Division qualifier'

    eligible_pct = [r for r in rows if not r.playoff_qualified and (r.wins + r.losses + r.ties) > 0]
    for r in rows:
        r.wildcard_score = wildcard_score(r.wins, r.losses, r.ties, total_games)
    if eligible_pct:
        # One division wildcard: best participation-weighted win percentage.
        # Tiebreaks: more picks made, then standings rank, then username.
        pct_winner = sorted(eligible_pct, key=lambda r: (
            -r.wildcard_score, -(r.wins + r.losses + r.ties), r.rank, r.user.username.lower()))[0]
        pct_winner.playoff_qualified = True
        pct_winner.division_wildcard = True
        pct_winner.qualification_route = 'Division wildcard (participation-weighted win %)'

    cutoff_rank = rows[qualifiers - 1].rank if len(rows) >= qualifiers and qualifiers > 0 else None
    for index, row in enumerate(rows):
        row.playoff_rank = row.rank
        row.at_cutoff = bool(cutoff_rank is not None and row.rank == cutoff_rank)
        row.playoff_status = 'qualified' if row.playoff_qualified else 'chasing'
        row.games_remaining = row.pending
        row.distance_from_cutoff = max(0, row.rank - qualifiers) if not row.playoff_qualified else 0
        row.players_ahead = rows[:index] if not row.playoff_qualified else []
        row.players_chased = rows[index + 1:index + 4]

    return {
        'standings': rows,
        'qualifiers_per_division': qualifiers,
        'division_wildcard_spots': 1,
        'head_to_head_wildcard_spots': config.head_to_head_wildcard_spots if config else 2,
        'season_complete': season_complete,
        'qualification_final': season_complete,
        'total_games': total_games,
        'pending_games': pending_games,
    }


def championship_bracket(season=None, field_size=50):
    """Build a seeded bracket preview using division and league-wide wildcard routes."""
    season = season or settings.NFL_SEASON
    config = PlayoffSettings.objects.filter(season=season).first()
    h2h_slots = config.head_to_head_wildcard_spots if config else 2
    candidates = []
    division_races = []
    all_rows = []

    for division in DIVISIONS:
        race = division_playoff_race(division, season)
        division_races.append((division, race))
        for row in race['standings']:
            all_rows.append((division, row))
            if row.playoff_qualified:
                candidates.append({
                    'user': row.user,
                    'division': division,
                    'record': f'{row.wins}-{row.losses}-{row.ties}',
                    'wins': row.wins,
                    'losses': row.losses,
                    'ties': row.ties,
                    'win_pct': row.win_pct,
                    'division_rank': row.rank,
                    'qualification_route': row.qualification_route,
                    'head_to_head_wins': 0,
                })

    already_qualified = {p['user'].id for p in candidates}
    h2h_records = challenge_records(user_ids=[row.user.id for _, row in all_rows], season=season)
    row_by_user = {row.user.id: (division, row) for division, row in all_rows}
    wildcard_pool = []
    for user_id, (division, row) in row_by_user.items():
        if user_id in already_qualified:
            continue
        won, lost, tied = h2h_records.get(user_id, [0, 0, 0])
        if won < 1:
            continue
        wildcard_pool.append({
            'user': row.user,
            'division': division,
            'record': f'{row.wins}-{row.losses}-{row.ties}',
            'wins': row.wins,
            'losses': row.losses,
            'ties': row.ties,
            'win_pct': row.win_pct,
            'division_rank': row.rank,
            'qualification_route': 'League-wide head-to-head wildcard',
            'head_to_head_wins': won,
            'head_to_head_losses': lost,
            'head_to_head_ties': tied,
        })

    # Most completed challenge victories first. Tiebreaks: challenge win rate,
    # season pick percentage, then existing division rank and username.
    def h2h_key(p):
        played = p['head_to_head_wins'] + p['head_to_head_losses'] + p['head_to_head_ties']
        pct = (p['head_to_head_wins'] + 0.5 * p['head_to_head_ties']) / played if played else 0
        return (-p['head_to_head_wins'], -pct, -(p['win_pct'] or 0), p['division_rank'], p['user'].username.lower())

    wildcard_pool.sort(key=h2h_key)
    for player in wildcard_pool[:h2h_slots]:
        player['user_id'] = player['user'].id
        candidates.append(player)
        division, row = row_by_user[player['user'].id]
        row.playoff_qualified = True
        row.head_to_head_wildcard = True
        row.qualification_route = 'League-wide head-to-head wildcard'
        row.playoff_status = 'qualified'

    # Stable seed order: qualification source first (division winners/rank first),
    # then season performance, then username.
    route_order = {'Division qualifier': 0, 'Division wildcard (participation-weighted win %)': 1,
                   'League-wide head-to-head wildcard': 2}
    candidates.sort(key=lambda p: (
        route_order.get(p['qualification_route'], 3), p['division_rank'],
        -(p['win_pct'] or 0), -p['wins'], p['losses'],
        p['user'].username.lower(), p['division'],
    ))
    field = candidates[:field_size]
    for seed, player in enumerate(field, start=1):
        player['seed'] = seed

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
    byes = field[:byes_count]
    return {
        'season': season,
        'field_size': field_size,
        'field': field,
        'field_count': count,
        'slots_open': max(0, field_size - count),
        'divisions': division_races,
        'first_round': first_round,
        'byes': byes,
        'round_one_winner_count': len(first_round),
        'bracket_size': bracket_size,
        'head_to_head_wildcard_spots': h2h_slots,
        'is_provisional': any(not race['season_complete'] for _, race in division_races),
    }
