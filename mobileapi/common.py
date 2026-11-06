"""Shared imports and serializers for the versioned mobile API."""
import logging

from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.db import transaction
from django.db.models import Q, Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.serializers import TokenRefreshSerializer

from api.models import Game
from api.services import current_week
from accounts.forms import SignUpForm
from accounts.models import (
    Pick, FriendRequest, PerformanceReaction, PlayerIdentity, LiveChatMessage,
)
from accounts.leaderboard import build_board, default_week
from accounts.team_identity import TEAM_DATA, team_palette, team_division
from accounts import chat
from accounts.signals import touch_activity
from .models import Device, NotificationPreference
from .idempotency import idempotent

log = logging.getLogger(__name__)
User = get_user_model()


def _tokens_for(user):
    refresh = RefreshToken.for_user(user)
    return {'refresh': str(refresh), 'access': str(refresh.access_token)}


def _user_payload(user):
    identity, _ = PlayerIdentity.objects.get_or_create(user=user)
    palette = team_palette(identity.favorite_team) if identity.favorite_team else None
    return {
        'id': user.pk,
        'username': user.username,
        'email': user.email,
        'favorite_team': identity.favorite_team,
        'favorite_team_name': TEAM_DATA.get(identity.favorite_team, {}).get('name', ''),
        'active_title': identity.active_title,
        'team_colors': ({'primary': palette['primary'], 'secondary': palette['secondary'],
                         'on_primary': palette['on_primary']} if palette else None),
    }


def _game_payload(game, user=None, include_community=False):
    pick = None
    if user and user.is_authenticated:
        pick = Pick.objects.filter(user=user, game=game).first()
    payload = {
        'id': game.pk,
        'game_id': game.game_id,
        'season': game.season,
        'week': game.week,
        'home_team': game.home_team,
        'away_team': game.away_team,
        'game_date': game.game_date.isoformat() if game.game_date else None,
        'kickoff': game.kickoff.isoformat() if game.kickoff else None,
        'lock_at': game.lock_at.isoformat() if game.lock_at else None,
        'has_started': game.has_started,
        'pick_available': not game.has_started,
        'status': game.status,
        'home_score': game.home_score,
        'away_score': game.away_score,
        'is_final': game.is_final,
        'winner': game.winner_name,
        'my_pick': ({'side': pick.team_picked, 'confidence': pick.confidence} if pick else None),
    }
    # Community percentages stay hidden until this player has picked this game.
    if include_community and pick:
        counts = {row['team_picked']: row['total'] for row in Pick.objects.filter(game=game)
                  .values('team_picked').annotate(total=Count('id'))}
        home = counts.get(Pick.HOME, 0)
        away = counts.get(Pick.AWAY, 0)
        total = home + away
        payload['community_picks'] = {
            'total': total,
            'home_percent': round(home * 100 / total) if total else 0,
            'away_percent': round(away * 100 / total) if total else 0,
        }
    else:
        payload['community_picks'] = None
    return payload
