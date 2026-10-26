"""
Everything the "click a player" menu and the profile/dashboard stat cards need,
in one place, so the Leaderboard, the friends drawer and the profile pages all
show the same numbers.
"""
from urllib.parse import urlencode

from django.urls import reverse

from . import challenges as ch
from .careerstats import career_for, career_stats
from .ranking import format_pct
from .standings import compute_standings


def _record(row):
    return f"{row.wins}–{row.losses}–{row.ties}"


def _text(record):
    return "–".join(str(n) for n in record)


def menu_data(users, viewer, season, compare_week, show_week=False):
    """
    {user_id: dict} for the player menu.

    compare_week: the week "View Picks" compares.
    show_week:    also include each player's record for that week.
    """
    users = list(users)
    if not users:
        return {}
    season_rows = {r.user.id: r for r in compute_standings(season=season, users=users)}
    week_rows = {}
    if show_week:
        week_rows = {r.user.id: r for r in compute_standings(
            week=compare_week, season=season, users=users)}
    career = career_stats()
    battles = ch.records([u.id for u in users])
    signed_in = viewer is not None and viewer.is_authenticated
    qs = urlencode({"season": season, "week": compare_week})

    result = {}
    for user in users:
        is_me = signed_in and user.id == viewer.id
        season_row = season_rows[user.id]
        life = career_for(career, user.id)

        if is_me:
            profile_url = reverse("profile")
            picks_url = f"{reverse('picks')}?{qs}"
            challenge_url = ""
        else:
            profile_url = f"{reverse('player_profile', args=[user.id])}?season={season}"
            picks = f"{reverse('compare_picks', args=[user.id])}?{qs}"
            challenge = reverse("challenge_new", args=[user.id])
            if signed_in:
                picks_url, challenge_url = picks, challenge
            else:
                login = reverse("login")
                picks_url = f"{login}?{urlencode({'next': picks})}"
                challenge_url = f"{login}?{urlencode({'next': challenge})}"

        result[user.id] = {
            "username": user.username,
            "is_me": is_me,
            "season_record": _record(season_row),
            "season_pct": format_pct(season_row.win_pct),
            "week_record": _record(week_rows[user.id]) if show_week else "",
            "week_label": f"Week {compare_week}",
            "weeks_won": life.weeks_won,
            "seasons_won": life.seasons_won,
            "challenge_record": _text(battles.get(user.id, [0, 0, 0])),
            "profile_url": profile_url,
            "picks_url": picks_url,
            "challenge_url": challenge_url,
        }
    return result


def stats_summary(user, season):
    """Expanded stats for one player (dashboard, own profile, public profile)."""
    season_row = compute_standings(season=season, users=[user])[0]
    life = career_for(career_stats(), user.id)
    won, lost, tied = ch.records([user.id]).get(user.id, [0, 0, 0])
    return {
        "season_row": season_row,
        "season_record": _record(season_row),
        "season_pct": format_pct(season_row.win_pct),
        "career": life,
        "career_record": f"{life.wins}–{life.losses}–{life.ties}",
        "career_pct": format_pct(life.win_pct),
        "weeks_won": life.weeks_won,
        "seasons_won": life.seasons_won,
        "challenges_won": won,
        "challenges_lost": lost,
        "challenges_tied": tied,
        "battles": won + lost + tied,
        "challenge_record": f"{won}–{lost}–{tied}",
    }
