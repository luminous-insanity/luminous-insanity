"""Private leagues: create, join with a code, and a leaderboard per league.

A league's standings are never stored. They come from the same picks and
final scores as the main leaderboard (compute_standings), limited to the
league's members, so a league can never disagree with the site.

Limits (override in settings): LEAGUE_MAX_MEMBERS (50), LEAGUE_MAX_OWNED (5),
LEAGUE_MAX_JOINED (15).
"""
import re

from django.conf import settings
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Count

from .models import League, LeagueMembership
from .moderation_rules import ALLOW, screen_text
from .standings import compute_standings
from .tiebreaker import apply_weekly_tiebreaker

NAME_MIN, NAME_MAX = 3, 60


class LeagueError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def max_members():
    return int(getattr(settings, 'LEAGUE_MAX_MEMBERS', 50))


def max_owned():
    return int(getattr(settings, 'LEAGUE_MAX_OWNED', 5))


def max_joined():
    return int(getattr(settings, 'LEAGUE_MAX_JOINED', 15))


def clean_name(raw):
    name = ' '.join((raw or '').split())
    if len(name) < NAME_MIN:
        raise LeagueError(f'Give your league a name of at least {NAME_MIN} characters.')
    if len(name) > NAME_MAX:
        raise LeagueError(f'League names are limited to {NAME_MAX} characters.')
    # Same text rules as chat: no links, contact details, threats or profanity.
    if screen_text(
            name,
            extra_profanity=getattr(settings, 'CHAT_PROFANITY_EXTRA', ()),
            blocked_terms=getattr(settings, 'CHAT_BLOCKED_TERMS', ()),
            allow_links=False).action != ALLOW:
        raise LeagueError("That league name isn't allowed. Try a different one.")
    return name


def normalize_code(raw):
    return re.sub(r'[^A-Za-z0-9]', '', raw or '').upper()


def is_member(league, user):
    return bool(user and user.is_authenticated and LeagueMembership.objects.filter(
        league=league, user=user).exists())


def member_count(league):
    return LeagueMembership.objects.filter(league=league).count()


def my_leagues(user):
    """The leagues `user` belongs to, each with .members and .is_owner set."""
    leagues = list(
        League.objects.filter(memberships__user=user)
        .annotate(members=Count('memberships')).select_related('owner')
        .order_by('name', 'id'))
    for league in leagues:
        league.is_owner = league.owner_id == user.id
    return leagues


@transaction.atomic
def create_league(owner, name):
    name = clean_name(name)
    if League.objects.filter(owner=owner).count() >= max_owned():
        raise LeagueError(f'You can run up to {max_owned()} leagues.', status=403)
    if LeagueMembership.objects.filter(user=owner).count() >= max_joined():
        raise LeagueError(f'You can be in up to {max_joined()} leagues.', status=403)
    league = League.objects.create(name=name, owner=owner)
    LeagueMembership.objects.create(league=league, user=owner)
    return league


@transaction.atomic
def join_by_code(user, code):
    code = normalize_code(code)
    league = League.objects.select_for_update().filter(invite_code=code).first() if code else None
    if league is None or not league.is_open:
        # Same message for "no such code" and "closed": don't reveal which.
        raise LeagueError("That invite code didn't work. Check it with the league owner.", status=404)
    if LeagueMembership.objects.filter(league=league, user=user).exists():
        raise LeagueError(f"You're already in {league.name}.", status=409)
    if member_count(league) >= max_members():
        raise LeagueError('That league is full.', status=403)
    if LeagueMembership.objects.filter(user=user).count() >= max_joined():
        raise LeagueError(f'You can be in up to {max_joined()} leagues.', status=403)
    LeagueMembership.objects.create(league=league, user=user)
    return league


def leave_league(user, league):
    if league.owner_id == user.id:
        raise LeagueError('Owners cannot leave. Hand the league to someone else or delete it.', status=403)
    deleted, _ = LeagueMembership.objects.filter(league=league, user=user).delete()
    if not deleted:
        raise LeagueError("You're not in that league.", status=404)


def _require_owner(user, league):
    if league.owner_id != user.id:
        raise LeagueError('Only the league owner can do that.', status=403)


def rename(user, league, name):
    _require_owner(user, league)
    league.name = clean_name(name)
    league.save(update_fields=['name'])


def set_open(user, league, is_open):
    _require_owner(user, league)
    league.is_open = bool(is_open)
    league.save(update_fields=['is_open'])


def regenerate_code(user, league):
    """Replace the invite code (old code stops working). Members stay."""
    _require_owner(user, league)
    return league.regenerate_code()


def remove_member(user, league, member_id):
    _require_owner(user, league)
    if int(member_id) == league.owner_id:
        raise LeagueError("You can't remove the owner.", status=400)
    deleted, _ = LeagueMembership.objects.filter(league=league, user_id=member_id).delete()
    if not deleted:
        raise LeagueError('That player is not in this league.', status=404)


@transaction.atomic
def transfer_ownership(user, league, username):
    _require_owner(user, league)
    target = User.objects.filter(username__iexact=(username or '').strip()).first()
    if target is None or not LeagueMembership.objects.filter(league=league, user=target).exists():
        raise LeagueError('Choose someone who is already in the league.', status=404)
    if target.id == user.id:
        raise LeagueError("You already own this league.", status=400)
    if League.objects.filter(owner=target).count() >= max_owned():
        raise LeagueError(f'{target.username} already runs {max_owned()} leagues.', status=403)
    league.owner = target
    league.save(update_fields=['owner'])
    return target


def delete_league(user, league):
    _require_owner(user, league)
    league.delete()


def league_board(league, tab, season, week):
    """Ranked standings for one league. tab: 'season' or 'weekly'.

    Weekly boards use "The Score is Right" to separate players who are level.
    """
    members = list(User.objects.filter(league_memberships__league=league))
    weekly = tab == 'weekly'
    rows = compute_standings(
        week=week if weekly else None, season=season, users=members, with_pending=True)
    if weekly:
        rows = apply_weekly_tiebreaker(rows, season, week)
    return rows
