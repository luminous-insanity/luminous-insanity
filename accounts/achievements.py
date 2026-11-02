"""Achievement milestones — football-themed recognition from real pick data.

Unlocks are persistent (AchievementUnlock). Metrics are always recalculated from
picks, scores, playoff entries, challenges, and profile identity so corrections
never invent trophies — they only unlock when the data supports them.
"""
from collections import defaultdict

from django.conf import settings
from django.contrib.auth.models import User

from api.models import Game
from api.rules import grade_pick
from .careerstats import career_for, career_stats
from .leaderboard import season_is_finalized
from .models import (
    AchievementUnlock, Pick, PlayerIdentity, PlayoffEntry, Challenge,
    PlayoffSettings,
)
from .standings import compute_standings

REGULAR_SEASON_WEEKS = 18


# Trophy icon per achievement key (shown on cards and dashboard)
ACHIEVEMENT_ICONS = {
    'play_caller': '📋',
    'division_dominator': '🏟️',
    'january_football': '❄️',
    'perfect_drive': '🎯',
    'red_zone_streak': '🔥',
    'iron_man': '💪',
    'division_crown': '👑',
    'super_bowl_bound': '🎫',
    'gameday_lombardi': '🏆',
    'true_fan': '❤️',
    'never_missed_a_snap': '📅',
    'rivalry_king': '⚔️',
    'franchise_player': '⭐',
    'riding_with_the_team': '🚌',
    'clinched': '✅',
    'wild_card_weekend': '🃏',
    'upset_special': '💥',
    'locksmith': '🔐',
    'gridiron_guru': '🧠',
    'film_room': '🎬',
}

# key, title, description, metric, thresholds
# Titles are football-flavored; descriptions stay plain so rules stay clear.
ACHIEVEMENTS = [
    (
        'play_caller',
        'Play Caller',
        'Submit picks. Every locked-in call counts — graded or still pending.',
        'picks_made',
        (1, 10, 25, 100, 250, 500, 1000),
    ),
    (
        'division_dominator',
        'Division Dominator',
        'Finish first in your division for a completed week. Ties for first count.',
        'division_weeks_won',
        (1, 3, 5, 10),
    ),
    (
        'january_football',
        'January Football',
        'Win a completed playoff week (Wild Card and beyond). Ties count.',
        'playoff_weeks_won',
        (1, 2, 3),
    ),
    (
        'perfect_drive',
        'Perfect Drive',
        'Pick every game in a completed week correctly. No misses, no ties.',
        'perfect_weeks',
        (1, 2, 3),
    ),
    (
        'red_zone_streak',
        'Red Zone Streak',
        'Consecutive correct picks. Any miss or tie resets the streak.',
        'best_streak',
        (5, 10, 25),
    ),
    (
        'iron_man',
        'Iron Man',
        'Make graded picks in different weeks across your career.',
        'weeks_played',
        (5, 10, 18),
    ),
    (
        'division_crown',
        'Division Crown',
        'Best regular-season record in your division when the season is finalized.',
        'division_titles',
        (1, 2, 3),
    ),
    (
        'super_bowl_bound',
        'Super Bowl Bound',
        'Reach the Super Bowl field in the GameDayPicks playoffs.',
        'sb_appearances',
        (1, 2, 3),
    ),
    (
        'gameday_lombardi',
        'Gameday Lombardi',
        'Win the Super Bowl week among the playoff field — the site championship.',
        'sb_titles',
        (1,),
    ),
    (
        'true_fan',
        'True Fan',
        'Set a favorite NFL team on your profile.',
        'favorite_team_set',
        (1,),
    ),
    (
        'never_missed_a_snap',
        'Never Missed a Snap',
        'Pick every regular-season game in a single season (all weeks loaded).',
        'perfect_seasons_picked',
        (1,),
    ),
    (
        'rivalry_king',
        'Rivalry King',
        'Win accepted head-to-head challenges against other players.',
        'h2h_wins',
        (1, 5, 10, 25),
    ),
    (
        'franchise_player',
        'Franchise Player',
        'Make picks in multiple NFL seasons.',
        'seasons_played',
        (1, 2, 3),
    ),
    (
        'riding_with_the_team',
        'Riding with the Team',
        'Pick your favorite team and they win that game.',
        'favorite_team_wins',
        (1, 5, 10, 25),
    ),
    (
        'clinched',
        'Clinched',
        'Earn a playoff berth (any qualification route).',
        'playoff_berths',
        (1, 2, 3),
    ),
    (
        'wild_card_weekend',
        'Wild Card Weekend',
        'Reach the playoffs as a wildcard.',
        'wildcard_berths',
        (1,),
    ),
    # Extras that fit existing data
    (
        'upset_special',
        'Upset Special',
        'Correctly pick an underdog based on current team records (worse win percentage than the opponent).',
        'underdog_hits',
        (1, 5, 15, 50),
    ),
    (
        'locksmith',
        'Locksmith',
        'Correct picks marked Lock confidence.',
        'lock_hits',
        (1, 5, 15, 40),
    ),
    (
        'gridiron_guru',
        'Gridiron Guru',
        'Finish a finalized season at .700 win percentage or better (min 50 graded picks).',
        'elite_seasons',
        (1, 2, 3),
    ),
    (
        'film_room',
        'Film Room',
        'Graded picks in your career (wins, losses, and ties all count).',
        'graded_picks',
        (25, 100, 300, 750),
    ),
]


def _team_name(game, side):
    if side == Pick.HOME:
        return game.home_team
    if side == Pick.AWAY:
        return game.away_team
    return None


def _graded_pick_data(user):
    picks = list(Pick.objects.filter(
        user=user,
        game__status=Game.FINAL,
        game__home_score__isnull=False,
        game__away_score__isnull=False,
    ).select_related('game').order_by('game__game_date', 'game__kickoff', 'game_id'))
    outcomes = []
    weeks = set()
    week_picks = defaultdict(dict)
    for pick in picks:
        outcome = grade_pick(pick.team_picked, pick.game.home_score, pick.game.away_score)
        if outcome not in ('win', 'loss', 'tie'):
            continue
        outcomes.append((pick, outcome))
        weeks.add((pick.game.season, pick.game.week))
        week_picks[(pick.game.season, pick.game.week)][pick.game.game_id] = outcome
    return outcomes, weeks, week_picks


def _perfect_weeks_count(week_picks):
    perfect = 0
    games_by_week = defaultdict(list)
    for game in Game.objects.all():
        games_by_week[(game.season, game.week)].append(game)
    for key, games in games_by_week.items():
        if not games or any(not game.is_final for game in games):
            continue
        user_outcomes = week_picks.get(key, {})
        if len(user_outcomes) == len(games) and all(
            user_outcomes.get(game.game_id) == 'win' for game in games
        ):
            perfect += 1
    return perfect


def _playoff_week_start(season):
    config = PlayoffSettings.objects.filter(season=season).first()
    if config:
        return config.first_playoff_week
    return REGULAR_SEASON_WEEKS + 1


def _division_for_user(user_id, season):
    identity = PlayerIdentity.objects.filter(
        user_id=user_id, division_season=season
    ).first()
    if identity and identity.division:
        return identity.division
    return ''


def _week_winners(season, week, user_ids=None):
    """User ids tied for first in a completed week. Empty if week not fully final."""
    games = list(Game.objects.filter(season=season, week=week))
    if not games or any(not g.is_final for g in games):
        return []
    users = None
    if user_ids is not None:
        users = list(User.objects.filter(id__in=user_ids))
        if not users:
            return []
    rows = compute_standings(week=week, season=season, users=users)
    if not rows:
        return []
    # Only count if someone has at least one completed pick
    top = rows[0]
    if top.completed < 1:
        return []
    return [r.user.id for r in rows if r.rank == 1 and r.completed > 0]


def _count_division_weeks_won(user):
    """Weeks the user finished #1 among division-mates (regular season)."""
    count = 0
    # Seasons the user has a division for
    identities = {
        i.division_season: i.division
        for i in PlayerIdentity.objects.filter(user=user)
        if i.division_season and i.division
    }
    # Also use current identity division for seasons with picks
    seasons = set(
        Pick.objects.filter(user=user).values_list('game__season', flat=True)
    )
    for season in seasons:
        division = identities.get(season) or _division_for_user(user.id, season)
        if not division:
            continue
        mate_ids = list(
            PlayerIdentity.objects.filter(
                division=division, division_season=season
            ).values_list('user_id', flat=True)
        )
        if user.id not in mate_ids:
            mate_ids.append(user.id)
        start = _playoff_week_start(season)
        weeks = (
            Game.objects.filter(season=season, week__lt=start)
            .values_list('week', flat=True).distinct()
        )
        for week in weeks:
            winners = _week_winners(season, week, user_ids=mate_ids)
            if user.id in winners:
                count += 1
    return count


def _count_playoff_weeks_won(user):
    count = 0
    seasons = set(
        Pick.objects.filter(user=user).values_list('game__season', flat=True)
    )
    for season in seasons:
        start = _playoff_week_start(season)
        weeks = (
            Game.objects.filter(season=season, week__gte=start)
            .values_list('week', flat=True).distinct()
        )
        for week in weeks:
            winners = _week_winners(season, week)
            if user.id in winners:
                count += 1
    return count


def _count_division_titles(user):
    """Finalized seasons where user had best record in their division."""
    count = 0
    seasons = set(
        Pick.objects.filter(user=user).values_list('game__season', flat=True)
    )
    for season in seasons:
        if not season_is_finalized(season):
            continue
        division = _division_for_user(user.id, season)
        if not division:
            continue
        mate_ids = list(
            PlayerIdentity.objects.filter(
                division=division, division_season=season
            ).values_list('user_id', flat=True)
        )
        if user.id not in mate_ids:
            mate_ids.append(user.id)
        users = list(User.objects.filter(id__in=mate_ids))
        rows = compute_standings(
            season=season, users=users, through_week=REGULAR_SEASON_WEEKS
        )
        if rows and rows[0].user_id == user.id and rows[0].rank == 1:
            count += 1
    return count


def _sb_field_user_ids(season):
    """Users who reached the Super Bowl field (still active after all cuts, or never cut)."""
    config = PlayoffSettings.objects.filter(season=season).first()
    rounds_cut = config.rounds_cut if config else 0
    qs = PlayoffEntry.objects.filter(season=season)
    if rounds_cut >= 3:
        return set(qs.filter(status=PlayoffEntry.ACTIVE).values_list('user_id', flat=True))
    # Provisional: anyone still active is "in" until cut
    return set(qs.filter(status=PlayoffEntry.ACTIVE).values_list('user_id', flat=True))


def _count_sb_appearances(user):
    count = 0
    seasons = PlayoffEntry.objects.filter(user=user).values_list('season', flat=True).distinct()
    for season in seasons:
        config = PlayoffSettings.objects.filter(season=season).first()
        if not config or config.rounds_cut < 3:
            # Only count when Super Bowl field is set (3 cuts done)
            continue
        if user.id in _sb_field_user_ids(season):
            count += 1
    return count


def _count_sb_titles(user):
    """Won Super Bowl week among the SB field (or sole survivor)."""
    count = 0
    seasons = PlayoffEntry.objects.filter(user=user).values_list('season', flat=True).distinct()
    for season in seasons:
        config = PlayoffSettings.objects.filter(season=season).first()
        if not config or config.rounds_cut < 3:
            continue
        field_ids = _sb_field_user_ids(season)
        if user.id not in field_ids:
            continue
        sb_week = config.first_playoff_week + 3  # round 4
        winners = _week_winners(season, sb_week, user_ids=list(field_ids))
        if user.id in winners:
            count += 1
    return count


def _h2h_wins(user):
    from django.db.models import Q
    from . import challenges as ch
    qs = list(
        Challenge.objects.filter(status=Challenge.ACCEPTED).filter(
            Q(challenger=user) | Q(opponent=user)
        ).select_related('challenger', 'opponent', 'game')
    )
    if not qs:
        return 0
    results = ch.evaluate_many(qs)
    wins = 0
    for challenge in qs:
        result = results.get(challenge.id)
        if result and result.state == 'final' and result.winner_id == user.id:
            wins += 1
    return wins


def _favorite_team_wins(user):
    identity = PlayerIdentity.objects.filter(user=user).first()
    if not identity or not identity.favorite_team:
        return 0
    fav = identity.favorite_team.upper()
    count = 0
    for pick in Pick.objects.filter(user=user).select_related('game'):
        game = pick.game
        if not game.is_final:
            continue
        picked_name = _team_name(game, pick.team_picked)
        if not picked_name or picked_name.upper() != fav:
            continue
        outcome = grade_pick(pick.team_picked, game.home_score, game.away_score)
        if outcome == 'win':
            count += 1
    return count


def _perfect_seasons_picked(user):
    """Seasons where user picked every regular-season game that exists."""
    count = 0
    seasons = set(Pick.objects.filter(user=user).values_list('game__season', flat=True))
    for season in seasons:
        start = _playoff_week_start(season)
        games = list(Game.objects.filter(season=season, week__lt=start))
        if len(games) < 16 * 8:  # need a real schedule loaded (rough floor)
            # still allow if all games that exist were picked
            pass
        if not games:
            continue
        picked_ids = set(
            Pick.objects.filter(user=user, game__in=games).values_list('game_id', flat=True)
        )
        if all(g.game_id in picked_ids or g.id in picked_ids for g in games):
            # game_id is the API id string; Pick.game_id is FK to Game.id
            game_pks = {g.pk for g in games}
            if game_pks <= set(
                Pick.objects.filter(user=user, game_id__in=game_pks).values_list('game_id', flat=True)
            ):
                count += 1
    return count


def _underdog_hits(user):
    """Correct picks where the chosen team scored fewer pregame 'strength' —
    approximate: picked team was away (road dog) or final margin was an upset
    relative to community — simpler reliable rule: correct pick + confidence LOCK.
    True underdog via final: picked side had lower score expectation by being
    the team that was behind in season standings is complex; use lock+correct
    as 'conviction underdog energy' is wrong.

    Better: correct pick where the winner was the away team (road win) OR
    the picked team won by being the lower-scoring pre-game favorite isn't available.

    Use: graded win where pick.confidence == LOCK (locksmith is separate).
    For upset_special: correct pick on the team that was trailing in the game
    at some point is not stored.

    Practical definition: correct pick where the *other* team was favored by
    community picks (>55% on opponent). Requires community data at grade time — skip.

    Final practical rule: win when you picked the away team (road dog stereotype)
    OR win with confidence lock on any dog via is_underdog if we have records.

    Simplest honest metric: number of correct picks where home_score/away shows
    you picked the team that was not the higher-scoring team's opponent wait.

    Use confidence LOCK wins as locksmith; underdog_hits = correct picks where
    the winning team had a worse season record at end of that week — expensive.

    Final: underdog_hits = graded wins where pick.confidence == LOCK (overlap with locksmith)
    is bad.

    Definition: graded win + is_underdog_pick with current team_records (approximate).
    """
    try:
        from api.services import get_team_records
        from .confidence import is_underdog_pick
        records = get_team_records()
    except Exception:
        records = {}
        is_underdog_pick = None
    if not is_underdog_pick:
        return 0
    hits = 0
    for pick in Pick.objects.filter(user=user).select_related('game'):
        game = pick.game
        if not game.is_final:
            continue
        if grade_pick(pick.team_picked, game.home_score, game.away_score) != 'win':
            continue
        try:
            if is_underdog_pick(pick, records):
                hits += 1
        except Exception:
            continue
    return hits


def _lock_hits(user):
    hits = 0
    for pick in Pick.objects.filter(user=user, confidence=Pick.CONFIDENCE_LOCK).select_related('game'):
        game = pick.game
        if not game.is_final:
            continue
        if grade_pick(pick.team_picked, game.home_score, game.away_score) == 'win':
            hits += 1
    return hits


def _elite_seasons(user):
    count = 0
    seasons = set(Pick.objects.filter(user=user).values_list('game__season', flat=True))
    for season in seasons:
        if not season_is_finalized(season):
            continue
        rows = compute_standings(season=season, users=[user])
        if not rows:
            continue
        s = rows[0]
        if s.completed >= 50 and s.win_pct is not None and s.win_pct >= 0.7:
            count += 1
    return count


def _current_metrics(user):
    outcomes, weeks, week_picks = _graded_pick_data(user)
    streak = best_streak = 0
    for _pick, outcome in outcomes:
        if outcome == 'win':
            streak += 1
            best_streak = max(best_streak, streak)
        else:
            streak = 0

    picks_made = Pick.objects.filter(user=user).count()
    seasons_played = Pick.objects.filter(user=user).values('game__season').distinct().count()
    identity = PlayerIdentity.objects.filter(user=user).first()
    favorite_set = 1 if identity and identity.favorite_team else 0

    playoff_berths = PlayoffEntry.objects.filter(user=user).count()
    wildcard_berths = PlayoffEntry.objects.filter(
        user=user, route__icontains='wildcard'
    ).count()

    return {
        'picks_made': picks_made,
        'graded_picks': len(outcomes),
        'weeks_played': len(weeks),
        'best_streak': best_streak,
        'perfect_weeks': _perfect_weeks_count(week_picks),
        'division_weeks_won': _count_division_weeks_won(user),
        'playoff_weeks_won': _count_playoff_weeks_won(user),
        'division_titles': _count_division_titles(user),
        'sb_appearances': _count_sb_appearances(user),
        'sb_titles': _count_sb_titles(user),
        'favorite_team_set': favorite_set,
        'perfect_seasons_picked': _perfect_seasons_picked(user),
        'h2h_wins': _h2h_wins(user),
        'seasons_played': seasons_played,
        'favorite_team_wins': _favorite_team_wins(user),
        'playoff_berths': playoff_berths,
        'wildcard_berths': wildcard_berths,
        'underdog_hits': _underdog_hits(user),
        'lock_hits': _lock_hits(user),
        'elite_seasons': _elite_seasons(user),
    }


def refresh_achievement_unlocks(user):
    """Persist newly earned milestones, then return cards with current progress."""
    metrics = _current_metrics(user)
    existing = {
        (item.achievement_key, item.level): item
        for item in AchievementUnlock.objects.filter(user=user)
    }
    for key, _title, _description, metric, thresholds in ACHIEVEMENTS:
        value = metrics.get(metric, 0)
        for level, threshold in enumerate(thresholds, start=1):
            if value >= threshold and (key, level) not in existing:
                item, _created = AchievementUnlock.objects.get_or_create(
                    user=user, achievement_key=key, level=level,
                )
                existing[(key, level)] = item

    cards = []
    for key, title, description, metric, thresholds in ACHIEVEMENTS:
        value = metrics.get(metric, 0)
        milestones = []
        next_threshold = None
        for level, threshold in enumerate(thresholds, start=1):
            unlock = existing.get((key, level))
            unlocked = unlock is not None
            milestones.append({
                'level': level,
                'threshold': threshold,
                'unlocked': unlocked,
                'unlocked_at': unlock.unlocked_at if unlock else None,
                'progress': min(value, threshold),
                'percent': min(100, int(value * 100 / threshold)) if threshold else 0,
            })
            if not unlocked and next_threshold is None:
                next_threshold = threshold
        unlocked_count = sum(1 for m in milestones if m['unlocked'])
        cards.append({
            'key': key,
            'icon': ACHIEVEMENT_ICONS.get(key, '🏆'),
            'title': title,
            'description': description,
            'metric': metric,
            'value': value,
            'milestones': milestones,
            'unlocked_count': unlocked_count,
            'total_levels': len(thresholds),
            'complete': unlocked_count == len(thresholds),
            'next_threshold': next_threshold,
            'percent': int(unlocked_count * 100 / len(thresholds)) if thresholds else 0,
        })

    unlocked = [
        {
            'title': card['title'],
            'milestone': milestone['threshold'],
            'unlocked_at': milestone['unlocked_at'],
            'key': card['key'],
            'level': milestone['level'],
            'icon': card['icon'],
            'complete': card['complete'] and milestone['level'] == card['total_levels'],
        }
        for card in cards for milestone in card['milestones'] if milestone['unlocked']
    ]
    unlocked.sort(key=lambda item: item['unlocked_at'] or item['key'], reverse=True)
    total_levels = sum(card['total_levels'] for card in cards)
    return {
        'cards': cards,
        'recent': unlocked[:4],
        'unlocked_count': len(unlocked),
        'total_unlocked': len(unlocked),  # alias for dashboard templates
        'total_levels': total_levels,
        'percent': int(len(unlocked) * 100 / total_levels) if total_levels else 0,
    }


def achievement_summary(user):
    """Public entry point used by dashboard and achievements page."""
    return refresh_achievement_unlocks(user)
