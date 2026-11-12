"""My insights: a player's own pick habits, worked out from graded picks.

Read-only. Nothing here changes picks or standings. Everything is recomputed
from picks and final scores each time, like the leaderboard.
"""
from django.db.models import Count

from api.models import Game
from api.rules import grade_pick

from .insights_rules import (
    Bucket, best_and_worst, crowd_side, favorite_from_records, pct, records_before_weeks,
)
from .models import Pick

CONFIDENCE_LABELS = {1: 'Lean', 2: 'Solid', 3: 'Lock', None: 'No confidence'}


def _favorite_side(game, snapshots):
    """Who was favored: Vegas line when we have one, else the better record then."""
    odds = getattr(game, 'odds', None)
    if odds is not None:
        side = odds.favorite_side
        if side in ('home', 'away'):
            return side, 'odds'
        if side == 'pickem':
            return None, 'odds'
    records = snapshots.get(game.week, {})
    return favorite_from_records(records.get(game.home_team), records.get(game.away_team)), 'record'


def build_insights(user, season):
    """Everything the insights page and API show for one player and season."""
    picks = list(
        Pick.objects.filter(user=user, game__season=season, game__status=Game.FINAL)
        .select_related('game', 'game__odds').order_by('game__week', 'game__id'))

    final_games = Game.objects.filter(season=season, status=Game.FINAL).exclude(
        home_score__isnull=True).exclude(away_score__isnull=True)
    snapshots = records_before_weeks(
        (g.week, g.home_team, g.away_team, g.home_score, g.away_score) for g in final_games)

    # How the whole site split on each game (to see who goes with the crowd).
    crowd = {}
    for row in (Pick.objects.filter(game__in=[p.game_id for p in picks])
                .values('game_id', 'team_picked').annotate(total=Count('id'))):
        crowd.setdefault(row['game_id'], {'home': 0, 'away': 0})[row['team_picked']] = row['total']

    overall = Bucket()
    sides = {'home': Bucket(), 'away': Bucket()}
    by_team = {}
    role = {'favorite': Bucket(), 'underdog': Bucket()}
    role_source = {'odds': 0, 'record': 0}
    confidence = {key: Bucket() for key in (3, 2, 1, None)}
    crowd_buckets = {'with': Bucket(), 'against': Bucket()}
    by_week = {}

    for pick in picks:
        game = pick.game
        result = grade_pick(pick.team_picked, game.home_score, game.away_score)
        if result is None:
            continue
        overall.add(result)
        sides[pick.team_picked].add(result)
        team = game.home_team if pick.team_picked == Pick.HOME else game.away_team
        by_team.setdefault(team, Bucket()).add(result)
        confidence[pick.confidence if pick.confidence in (1, 2, 3) else None].add(result)
        by_week.setdefault(game.week, Bucket()).add(result)

        favorite, source = _favorite_side(game, snapshots)
        if favorite:
            role['favorite' if pick.team_picked == favorite else 'underdog'].add(result)
            role_source[source] += 1

        counts = crowd.get(game.pk, {'home': 0, 'away': 0})
        majority = crowd_side(counts['home'], counts['away'])
        if majority:
            crowd_buckets['with' if pick.team_picked == majority else 'against'].add(result)

    best_team, worst_team = best_and_worst(by_team)
    data = {
        'season': season,
        'overall': overall.as_dict(),
        'home_vs_away': {k: v.as_dict() for k, v in sides.items()},
        'favorite_vs_underdog': {k: v.as_dict() for k, v in role.items()},
        'favorite_source': ('odds' if role_source['odds'] >= role_source['record'] and role_source['odds']
                            else 'record'),
        'confidence': [
            {'key': key, 'label': CONFIDENCE_LABELS[key], **confidence[key].as_dict()}
            for key in (3, 2, 1, None)
        ],
        'with_vs_against_crowd': {k: v.as_dict() for k, v in crowd_buckets.items()},
        'best_team': _team_row(best_team),
        'worst_team': _team_row(worst_team),
        'teams': sorted(
            ({'team': t, **b.as_dict()} for t, b in by_team.items()),
            key=lambda r: (-r['games'], r['team'])),
        'weeks': [{'week': w, **by_week[w].as_dict()} for w in sorted(by_week)],
    }
    data['takeaways'] = takeaways(data)
    return data


def _team_row(item):
    if item is None:
        return None
    name, stats = item
    return {'team': name, **stats}


def _gap(a, b, minimum=3):
    """Percent-point gap between two bucket dicts when both have enough picks."""
    if a['games'] < minimum or b['games'] < minimum or a['pct'] is None or b['pct'] is None:
        return None
    return round(a['pct'] - b['pct'], 1)


def takeaways(data):
    """Short plain-English notes. Only says things the numbers support."""
    notes = []
    if data['overall']['games'] < 5:
        return ['Make a few more picks and your habits will show up here.']

    gap = _gap(data['home_vs_away']['home'], data['home_vs_away']['away'])
    if gap is not None and abs(gap) >= 10:
        side = 'home' if gap > 0 else 'road'
        notes.append(f'You pick {side} teams better, by about {abs(gap):.0f} points.')

    gap = _gap(data['favorite_vs_underdog']['favorite'], data['favorite_vs_underdog']['underdog'])
    if gap is not None and abs(gap) >= 10:
        who = 'favorites' if gap > 0 else 'underdogs'
        notes.append(f'You do better with {who} than the other side by about {abs(gap):.0f} points.')

    locks = next((c for c in data['confidence'] if c['key'] == 3), None)
    others = [c for c in data['confidence'] if c['key'] in (1, 2)]
    other_games = sum(c['games'] for c in others)
    if locks and locks['games'] >= 3 and other_games >= 3 and locks['pct'] is not None:
        wins = sum(c['wins'] for c in others) + 0.5 * sum(c['ties'] for c in others)
        other_pct = round(wins / other_games * 100, 1)
        if locks['pct'] >= other_pct + 10:
            notes.append('Your Locks are earning their name: they win more than your other picks.')
        elif locks['pct'] <= other_pct - 10:
            notes.append('Your Locks win less often than your other picks. Save Lock for your surest calls.')

    crowd = data['with_vs_against_crowd']
    gap = _gap(crowd['with'], crowd['against'])
    if gap is not None and abs(gap) >= 10:
        if gap > 0:
            notes.append('Going with the crowd has worked better for you than going against it.')
        else:
            notes.append('Your contrarian picks beat the crowd picks. Trust your gut.')

    if data['best_team']:
        t = data['best_team']
        notes.append(f"Best team to pick: {t['team']} ({t['wins']}-{t['losses']}-{t['ties']}).")
    if data['worst_team']:
        t = data['worst_team']
        notes.append(f"Toughest team for you: {t['team']} ({t['wins']}-{t['losses']}-{t['ties']}).")
    return notes
