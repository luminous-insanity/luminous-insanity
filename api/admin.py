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
