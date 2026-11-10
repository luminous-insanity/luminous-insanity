from django.conf import settings
from .team_identity import team_palette


def player_team_theme(request):
    """Expose the signed-in player's favorite-team palette to every template."""
    palette = None
    team_code = ''
    if getattr(request, 'user', None) is not None and request.user.is_authenticated:
        try:
            team_code = request.user.player_identity.favorite_team
        except Exception:
            # Existing accounts have no identity row until they visit/save Profile.
            team_code = ''
    palette = team_palette(team_code) if team_code else None
    if not palette:
        return {'team_theme': {'enabled': False}}
    return {
        'team_theme': {
            'enabled': True,
            'code': team_code,
            'name': palette['name'],
            'primary': palette['primary'],
            'secondary': palette['secondary'],
            'on_primary': palette['on_primary'],
        }
    }


def social_drawer(request):
    """Expose the Social drawer payload on every authenticated page.

    Always returns the keys the drawer template expects so missing
    dashboard-only variables never blow up other pages.
    """
    user = getattr(request, 'user', None)
    if user is None or not getattr(user, 'is_authenticated', False):
        return {}

    # Safe baseline so the template never looks up missing names.
    baseline = {
        'friend_query': '',
        'friend_results': [],
        'incoming_requests': [],
        'friend_rows': [],
        'invite_url': '',
        'invite_text': '',
        'invite_message': '',
        'live_moments': None,
        'shared_moment_weeks': [],
        'shared_moment_challenges': [],
        'social_selected_season': getattr(settings, 'NFL_SEASON', 2026),
        'social_mission_week': 1,
        'social_reaction_week': 1,
        'social_record_week': 'season',
        'reaction_choices': [],
    }
    try:
        from .live_features import social_drawer_context
        from .models import PerformanceReaction
        data = social_drawer_context(request) or {}
        baseline.update(data)
        if not baseline.get('reaction_choices'):
            baseline['reaction_choices'] = PerformanceReaction.choices
    except Exception:
        try:
            from .models import PerformanceReaction
            baseline['reaction_choices'] = PerformanceReaction.choices
        except Exception:
            pass
    return baseline
