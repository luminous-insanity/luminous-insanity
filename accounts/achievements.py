"""Achievement milestones calculated from graded picks and finalized results."""
from collections import defaultdict

from api.models import Game
from api.rules import grade_pick
from .careerstats import career_for, career_stats
from .models import AchievementUnlock, Pick


# key, title, description, metric, milestone thresholds
ACHIEVEMENTS = [
    ('pick_maker', 'Pick Maker', 'Correctly or incorrectly graded picks count toward your total.', 'graded_picks', (1, 10, 25, 50, 100)),
    ('week_winner', 'Week Winner', 'Finish first in a completed weekly leaderboard. Ties count.', 'weeks_won', (1, 3, 5, 10, 20)),
    ('perfect_week', 'Perfect Week', 'Pick every game in a completed week correctly.', 'perfect_weeks', (1, 3, 5, 10)),
    ('hot_streak', 'Hot Streak', 'Consecutive correct picks, with any incorrect or tied result ending the streak.', 'best_streak', (5, 10, 25)),
    ('season_veteran', 'Season Veteran', 'Make picks that are graded in different weeks.', 'weeks_played', (5, 10, 18)),
    ('champion', 'Season Champion', 'Finish first in a finalized season. Co-champions count.', 'seasons_won', (1, 3, 5)),
]


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
        outcomes.append((pick.game, outcome))
        weeks.add((pick.game.season, pick.game.week))
        week_picks[(pick.game.season, pick.game.week)][pick.game_id] = outcome
    return outcomes, weeks, week_picks


def _perfect_weeks(user, week_picks):
    perfect = set()
    games_by_week = defaultdict(list)
    for game in Game.objects.all():
        games_by_week[(game.season, game.week)].append(game)

    for key, games in games_by_week.items():
        # A week is eligible only when every loaded game has a final score.
        if not games or any(not game.is_final for game in games):
            continue
        user_outcomes = week_picks.get(key, {})
        # Require a pick for every game and every pick to be correct.
        if len(user_outcomes) == len(games) and all(
            user_outcomes.get(game.game_id) == 'win' for game in games
        ):
            perfect.add(key)
    return len(perfect)


def _current_metrics(user):
    outcomes, weeks, week_picks = _graded_pick_data(user)
    streak = best_streak = 0
    for _game, outcome in outcomes:
        if outcome == 'win':
            streak += 1
            best_streak = max(best_streak, streak)
        else:
            streak = 0

    career = career_for(career_stats(), user.id)
    return {
        'graded_picks': len(outcomes),
        'weeks_played': len(weeks),
        'weeks_won': career.weeks_won,
        'seasons_won': career.seasons_won,
        'perfect_weeks': _perfect_weeks(user, week_picks),
        'best_streak': best_streak,
    }


def refresh_achievement_unlocks(user):
    """Persist newly earned milestones, then return cards with current progress."""
    metrics = _current_metrics(user)
    existing = {
        (item.achievement_key, item.level): item
        for item in AchievementUnlock.objects.filter(user=user)
    }
    for key, _title, _description, metric, thresholds in ACHIEVEMENTS:
        value = metrics[metric]
        for level, threshold in enumerate(thresholds, start=1):
            if value >= threshold and (key, level) not in existing:
                item, _created = AchievementUnlock.objects.get_or_create(
                    user=user, achievement_key=key, level=level,
                )
                existing[(key, level)] = item

    cards = []
    for key, title, description, metric, thresholds in ACHIEVEMENTS:
        value = metrics[metric]
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
                'percent': min(100, int(value * 100 / threshold)),
            })
            if not unlocked and next_threshold is None:
                next_threshold = threshold
        unlocked_count = sum(1 for milestone in milestones if milestone['unlocked'])
        cards.append({
            'key': key,
            'title': title,
            'description': description,
            'value': value,
            'milestones': milestones,
            'unlocked_count': unlocked_count,
            'total_levels': len(thresholds),
            'next_threshold': next_threshold,
            'next_progress': value if next_threshold is None else min(value, next_threshold),
            'next_percent': 100 if next_threshold is None else min(100, int(value * 100 / next_threshold)),
            'complete': unlocked_count == len(thresholds),
            'latest_unlocked': max(
                (m['unlocked_at'] for m in milestones if m['unlocked_at']),
                default=None,
            ),
        })
    return cards


def achievement_summary(user):
    cards = refresh_achievement_unlocks(user)
    unlocked = [
        {'title': card['title'], 'milestone': milestone['threshold'],
         'unlocked_at': milestone['unlocked_at'], 'key': card['key'],
         'level': milestone['level']}
        for card in cards for milestone in card['milestones'] if milestone['unlocked']
    ]
    unlocked.sort(key=lambda item: item['unlocked_at'], reverse=True)
    total_levels = sum(card['total_levels'] for card in cards)
    return {
        'cards': cards,
        'recent': unlocked[:3],
        'unlocked_count': len(unlocked),
        'total_levels': total_levels,
        'percent': int(len(unlocked) * 100 / total_levels) if total_levels else 0,
    }
