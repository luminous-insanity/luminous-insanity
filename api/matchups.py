"""Matchup context for the picks page: Vegas odds and injury reports.

Everything here is display/analytics only. Nothing in this module changes
picks, scoring or standings. Data comes from admin, from
`manage.py import_matchups`, or from any future provider that calls
upsert_odds() / upsert_injury().
"""
from decimal import Decimal, InvalidOperation

from .models import Game, GameOdds, InjuryReport

STATUS_LABELS = dict(InjuryReport.STATUS_CHOICES)
# Statuses worth showing as a warning chip next to a team on the picks page.
SERIOUS_STATUSES = (InjuryReport.OUT, InjuryReport.IR, InjuryReport.DOUBTFUL)


def _decimal(value):
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value)).quantize(Decimal('0.1'))
    except (InvalidOperation, ValueError):
        raise ValueError(f'Not a number: {value!r}')


def _int(value):
    if value in (None, ''):
        return None
    try:
        return int(str(value).replace('+', '').strip())
    except ValueError:
        raise ValueError(f'Not a whole number: {value!r}')


def upsert_odds(game, spread_home=None, total_points=None, moneyline_home=None,
                moneyline_away=None, sportsbook='', source='import'):
    """Create or update the odds row for a game. Returns the GameOdds."""
    values = {
        'spread_home': _decimal(spread_home),
        'total_points': _decimal(total_points),
        'moneyline_home': _int(moneyline_home),
        'moneyline_away': _int(moneyline_away),
        'sportsbook': (sportsbook or '')[:40],
        'source': (source or 'import')[:20],
    }
    odds, _ = GameOdds.objects.update_or_create(game=game, defaults=values)
    return odds


def upsert_injury(season, week, team, player_name, status, position='', detail='',
                  is_key_player=False, source='import'):
    """Create or update one player's report. Returns the InjuryReport."""
    status = (status or '').strip().lower().replace(' ', '_')
    aliases = {'injured_reserve': InjuryReport.IR, 'ir': InjuryReport.IR}
    status = aliases.get(status, status)
    if status not in STATUS_LABELS:
        raise ValueError(f'Unknown injury status: {status!r}')
    report, _ = InjuryReport.objects.update_or_create(
        season=int(season), week=int(week),
        team=str(team).strip().upper(), player_name=str(player_name).strip()[:80],
        defaults={
            'status': status,
            'position': (position or '')[:8],
            'detail': (detail or '')[:120],
            'is_key_player': bool(is_key_player),
            'source': (source or 'import')[:20],
        },
    )
    return report


def find_game(season=None, week=None, game_id=None, home=None, away=None):
    """Match a game by its id, or by season + week + both teams."""
    if game_id:
        return Game.objects.filter(game_id=str(game_id)).first()
    if None in (season, week) or not home or not away:
        return None
    return Game.objects.filter(
        season=int(season), week=int(week),
        home_team__iexact=str(home).strip(), away_team__iexact=str(away).strip(),
    ).first()


def sorted_injuries(reports):
    """Key players first, then most serious status, then name."""
    return sorted(reports, key=lambda r: (not r.is_key_player, r.severity, r.player_name))


def injuries_by_team(season, week, teams=None):
    """{team: [InjuryReport, ...]} for one week, sorted for display."""
    rows = InjuryReport.objects.filter(season=season, week=week)
    if teams is not None:
        rows = rows.filter(team__in=list(teams))
    grouped = {}
    for row in rows:
        grouped.setdefault(row.team, []).append(row)
    return {team: sorted_injuries(items) for team, items in grouped.items()}


def injury_payload(report):
    return {
        'player': report.player_name,
        'position': report.position,
        'status': report.status,
        'status_label': STATUS_LABELS.get(report.status, report.status),
        'detail': report.detail,
        'key_player': report.is_key_player,
    }


def odds_payload(odds):
    """JSON-friendly odds (None when the game has no line)."""
    if odds is None:
        return None
    return {
        'spread_home': float(odds.spread_home) if odds.spread_home is not None else None,
        'spread_label': odds.spread_label,
        'total_points': float(odds.total_points) if odds.total_points is not None else None,
        'total_label': odds.total_label,
        'moneyline_home': odds.moneyline_home,
        'moneyline_away': odds.moneyline_away,
        'favorite': odds.favorite_side,
        'favorite_team': odds.favorite_team,
        'sportsbook': odds.sportsbook,
        'updated_at': odds.updated_at.isoformat() if odds.updated_at else None,
    }


def matchup_for_game(game, injuries=None):
    """Odds + both teams' injuries for one game.

    `injuries` may be the dict from injuries_by_team() so a page of games does
    one query instead of one per game.
    """
    if injuries is None:
        injuries = injuries_by_team(game.season, game.week, [game.home_team, game.away_team])
    odds = getattr(game, 'odds', None)
    return {
        'odds': odds,
        'home_injuries': injuries.get(game.home_team, []),
        'away_injuries': injuries.get(game.away_team, []),
    }


def matchup_payload(game, injuries=None):
    data = matchup_for_game(game, injuries)
    return {
        'game_id': game.game_id,
        'odds': odds_payload(data['odds']),
        'home_injuries': [injury_payload(r) for r in data['home_injuries']],
        'away_injuries': [injury_payload(r) for r in data['away_injuries']],
    }
