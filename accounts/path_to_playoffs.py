"""Path to playoffs — compact status for the dashboard."""
from django.conf import settings

from .models import PlayerIdentity, PlayoffEntry
from .playoffs import division_playoff_race
from .standings import standing_for


def path_to_playoffs(user, season=None):
    season = season or settings.NFL_SEASON
    identity = PlayerIdentity.objects.filter(user=user, division_season=season).first()
    entry = PlayoffEntry.objects.filter(user=user, season=season).first()

    season_standing = standing_for(user, season=season)
    result = {
        'season': season,
        'division': identity.division if identity else '',
        'record': None,
        'division_rank': None,
        'status': 'no_division',
        'headline': 'Pick a favorite team to join a division race',
        'detail': 'Your division locks for the season from your profile team.',
        'qualified': False,
        'route': '',
        'wins_back': None,
        'players_in_division': 0,
    }
    if season_standing:
        result['record'] = (
            f'{season_standing.wins}-{season_standing.losses}-{season_standing.ties}'
        )

    if entry:
        active = entry.status == PlayoffEntry.ACTIVE
        result['qualified'] = True
        result['status'] = 'in_field' if active else 'eliminated'
        result['route'] = entry.route or 'Playoff field'
        result['headline'] = (
            'Playoff field — still alive' if active
            else f'Eliminated (round {entry.eliminated_round or "—"})'
        )
        result['detail'] = entry.route or 'Survive each weekly cut to reach the Super Bowl field.'
        return result

    if not identity or not identity.division:
        return result

    try:
        race = division_playoff_race(identity.division, season=season)
    except Exception:
        result['status'] = 'unavailable'
        result['headline'] = 'Division race unavailable'
        result['detail'] = 'Check back once more players are in your division.'
        return result

    rows = race.get('standings') or []
    result['players_in_division'] = len(rows)
    my_row = next((r for r in rows if r.user.id == user.id), None)
    if not my_row:
        result['status'] = 'unranked'
        result['headline'] = f'{identity.division} · no graded picks yet'
        result['detail'] = 'Make picks to enter the division standings.'
        return result

    result['division_rank'] = my_row.rank
    result['record'] = f'{my_row.wins}-{my_row.losses}-{my_row.ties}'
    if getattr(my_row, 'playoff_qualified', False):
        result['qualified'] = True
        result['status'] = 'clinched'
        result['route'] = getattr(my_row, 'qualification_route', '') or 'Qualified'
        result['headline'] = 'Playoff spot clinched'
        result['detail'] = result['route']
        return result

    # Distance to automatic cutoff
    qualifiers = race.get('qualifiers_per_division') or 4
    auto = [
        r for r in rows
        if getattr(r, 'playoff_qualified', False)
        and not getattr(r, 'division_wildcard', False)
    ]
    if auto:
        cutoff = auto[-1]
        wins_back = max(0, cutoff.wins - my_row.wins)
        result['wins_back'] = wins_back
        result['status'] = 'chasing'
        if wins_back == 0:
            result['headline'] = f'On the bubble · #{my_row.rank} in {identity.division}'
            result['detail'] = 'Tied with the cutoff on wins — every pick matters.'
        elif wins_back <= 3:
            result['headline'] = (
                f'{wins_back} win{"s" if wins_back != 1 else ""} from a playoff spot'
            )
            result['detail'] = f'#{my_row.rank} in {identity.division} · chase the top {qualifiers}.'
        else:
            result['headline'] = f'#{my_row.rank} in {identity.division}'
            result['detail'] = f'{wins_back} wins behind the last automatic qualifier.'
    else:
        result['status'] = 'chasing'
        result['headline'] = f'#{my_row.rank} in {identity.division}'
        result['detail'] = 'Division race is underway.'
    return result
