# api/admin.py
from django.contrib import admin
from .models import Game, QuarterScore


class QuarterScoreInline(admin.TabularInline):
    """Running score at the end of Q1, halftime and Q3 (used by Super Bowl squares)."""
    model = QuarterScore
    extra = 0
    max_num = 3


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'season', 'week', 'status', 'home_score', 'away_score')
    list_filter = ('season', 'week', 'status')
    search_fields = ('game_id', 'home_team', 'away_team')
    inlines = [QuarterScoreInline]


# NFLWeek and Score are legacy (see models.py comments).
# Tables and historical rows are preserved; they are no longer registered in admin
# because runtime code uses Game + api.services.current_week() exclusively.


from .models import GameOdds, InjuryReport  # noqa: E402


@admin.register(GameOdds)
class GameOddsAdmin(admin.ModelAdmin):
    """Vegas lines. Display only; they never change scoring.

    Spread is from the HOME team's side: -3.5 means home is favored by 3.5.
    """
    list_display = ('game', 'spread_home', 'total_points', 'moneyline_home',
                    'moneyline_away', 'sportsbook', 'source', 'updated_at')
    list_filter = ('game__season', 'game__week', 'source')
    search_fields = ('game__game_id', 'game__home_team', 'game__away_team')
    raw_id_fields = ('game',)


@admin.register(InjuryReport)
class InjuryReportAdmin(admin.ModelAdmin):
    list_display = ('season', 'week', 'team', 'player_name', 'position', 'status',
                    'detail', 'is_key_player', 'source')
    list_filter = ('season', 'week', 'status', 'is_key_player', 'team')
    search_fields = ('player_name', 'team')
    list_editable = ('status', 'is_key_player')
