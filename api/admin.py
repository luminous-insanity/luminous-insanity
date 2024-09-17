# accounts/admin.py
from django.contrib import admin
from .models import Game, Score, NFLWeek

class ScoreAdmin(admin.ModelAdmin):
    list_display = ('game_id', 'home_score', 'away_score', 'game_date')
    search_fields = ('game_id',)
    list_filter = ('game_date',)


admin.site.register(Game)
admin.site.register(Score, ScoreAdmin)
admin.site.register(NFLWeek)
