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
