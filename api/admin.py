# api/admin.py
from django.contrib import admin
from .models import Game, QuarterScore, Score, NFLWeek


class ScoreAdmin(admin.ModelAdmin):
    list_display = ('game_id', 'home_score', 'away_score', 'game_date')
    search_fields = ('game_id',)
    list_filter = ('game_date',)


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


admin.site.register(Score, ScoreAdmin)
admin.site.register(NFLWeek)
