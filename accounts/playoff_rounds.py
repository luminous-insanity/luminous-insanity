"""Playoff entries and weekly cuts, worked out from picks and final scores.

Flow
  1. open_playoffs()  freezes the playoff field (division qualifiers plus both
                      wildcard routes) into PlayoffEntry rows, everyone 0-0.
  2. run_cut()        after each playoff week finishes, removes the players
                      with the worst playoff records, down to the Super Bowl
                      field size (50 by default) after the third cut.
  3. The last survivors are the Super Bowl field.

Records are cumulative across playoff rounds. A game a player didn't pick
counts as a loss here, otherwise skipping the playoffs would beat losing.
"""
from collections import defaultdict

from django.conf import settings
from django.db import transaction

from api.models import Game
from api.rules import grade_pick

from .models import Pick, PlayoffEntry, PlayoffSettings
from .playoff_cuts import cut_targets, split_field, survival_key, tiebreak_draw
from .playoffs import championship_bracket

ROUND_NAMES = ('Wild Card', 'Divisional', 'Conference', 'Super Bowl')
CUTS = 3  # cuts happen after Wild Card, Divisional and Conference


class PlayoffError(ValueError):
    """A problem worth showing to the person running the playoffs."""


def get_config(season):
    config, _ = PlayoffSettings.objects.get_or_create(season=season)
    return config


def round_week(config, round_no):
    """Game.week for round 1 (Wild Card) .. 4 (Super Bowl)."""
    return config.first_playoff_week + round_no - 1


def open_playoffs(season=None, force=False):
    """Freeze the playoff field. Returns the number of entrants."""
    season = season or settings.NFL_SEASON
    config = get_config(season)
    if PlayoffEntry.objects.filter(season=season).exists():
        raise PlayoffError(f'The {season} playoff field is already open.')

    # field_size is huge on purpose: the bracket helper caps at 50, but the
    # playoff field itself is everyone who qualified.
    bracket = championship_bracket(season, field_size=10 ** 6)
    if bracket['is_provisional'] and not force:
        raise PlayoffError(
            'The regular season is not finished, so qualification is still '
            'provisional. Use --force to open the field anyway.')
    if not bracket['field']:
        raise PlayoffError('Nobody has qualified yet.')

    entries = [
        PlayoffEntry(
            user=p['user'], season=season,
            route=p['qualification_route'], division=p['division'],
            regular_win_pct=p['win_pct'] or 0,
            head_to_head_wins=p.get('head_to_head_wins', 0),
            tiebreak_draw=tiebreak_draw(season, p['user'].id),
        )
        for p in bracket['field']
    ]
    PlayoffEntry.objects.bulk_create(entries)
    if config.rounds_cut:
        config.rounds_cut = 0
        config.save(update_fields=['rounds_cut'])
    return len(entries)


def playoff_records(user_ids, season, config, through_round):
    """{user_id: (wins, losses, ties)} over final playoff games, rounds 1..N.

    Unpicked games count as losses.
    """
    weeks = [round_week(config, n) for n in range(1, through_round + 1)]
    final_games = [g for g in Game.objects.filter(season=season, week__in=weeks)
                   if g.is_final]
    wins, ties = defaultdict(int), defaultdict(int)
    if final_games:
        picks = Pick.objects.filter(
            user_id__in=list(user_ids), game__in=final_games,
        ).values_list('user_id', 'team_picked', 'game__home_score', 'game__away_score')
        for user_id, side, home, away in picks:
            result = grade_pick(side, home, away)
            if result == 'win':
                wins[user_id] += 1
            elif result == 'tie':
                ties[user_id] += 1
    total = len(final_games)
    return {uid: (wins[uid], total - wins[uid] - ties[uid], ties[uid])
            for uid in user_ids}


def _sorted_entries(entries, records):
    def key(entry):
        w, l, t = records[entry.user_id]
        return survival_key(w, l, t, entry.regular_win_pct,
                            entry.head_to_head_wins, entry.tiebreak_draw)
    return key


@transaction.atomic
def run_cut(season=None, force=False):
    """Apply the next weekly cut. Returns a summary dict."""
    season = season or settings.NFL_SEASON
    config = get_config(season)
    round_no = config.rounds_cut + 1
    if round_no > CUTS:
        raise PlayoffError('All cuts are done. The Super Bowl field is set.')

    everyone = PlayoffEntry.objects.filter(season=season)
    total_entrants = everyone.count()
    if total_entrants == 0:
        raise PlayoffError('The playoff field is not open yet.')

    games = Game.objects.filter(season=season, week=round_week(config, round_no))
    if not games.exists():
        raise PlayoffError(
            f'No games are loaded for {ROUND_NAMES[round_no - 1]} '
            f'(week {round_week(config, round_no)}).')
    if not force and any(not g.is_final for g in games):
        raise PlayoffError(
            f'{ROUND_NAMES[round_no - 1]} games are not all final yet. '
            f'Use --force to cut anyway.')

    active = list(everyone.filter(status=PlayoffEntry.ACTIVE).select_related('user'))
    keep = cut_targets(total_entrants, config.field_target, CUTS)[round_no - 1]
    records = playoff_records([e.user_id for e in active], season, config, round_no)
    survivors, cut = split_field(active, keep, _sorted_entries(active, records))

    if cut:
        PlayoffEntry.objects.filter(id__in=[e.id for e in cut]).update(
            status=PlayoffEntry.ELIMINATED, eliminated_round=round_no)
    config.rounds_cut = round_no
    config.save(update_fields=['rounds_cut'])
    return {
        'round': round_no, 'round_name': ROUND_NAMES[round_no - 1],
        'before': len(active), 'after': len(survivors), 'cut': len(cut),
        'cut_line': records[survivors[-1].user_id] if survivors else None,
    }


def field_standings(season=None):
    """Active players ranked by their current playoff record, best first."""
    season = season or settings.NFL_SEASON
    config = get_config(season)
    active = list(PlayoffEntry.objects.filter(
        season=season, status=PlayoffEntry.ACTIVE).select_related('user'))
    through = min(config.rounds_cut + 1, CUTS)
    records = playoff_records([e.user_id for e in active], season, config, through)
    active.sort(key=_sorted_entries(active, records))
    return [(e, records[e.user_id]) for e in active]
