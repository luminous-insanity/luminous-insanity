from django.contrib import admin
from .models import GameReaction  # noqa registered below
from .models import Pick, AchievementUnlock

# UserStatistics is legacy: standings are always derived from picks + final
# scores (accounts/standings.py). The table and rows are preserved; the model
# is no longer registered in admin.


@admin.register(Pick)
class PickAdmin(admin.ModelAdmin):
    list_display = ('user', 'game', 'team_picked', 'confidence')
    list_filter = ('team_picked', 'confidence')
    search_fields = ('user__username', 'game__game_id')


@admin.register(AchievementUnlock)
class AchievementUnlockAdmin(admin.ModelAdmin):
    list_display = ('user', 'achievement_key', 'level', 'unlocked_at')
    list_filter = ('achievement_key', 'level')
    search_fields = ('user__username', 'achievement_key')

from .models import BoardSquare, PlayoffEntry, PlayoffSettings, SquaresBoard

@admin.register(PlayoffSettings)
class PlayoffSettingsAdmin(admin.ModelAdmin):
    list_display = ('season', 'qualifiers_per_division', 'qualifier_percent',
                    'head_to_head_wildcard_spots', 'field_target', 'first_playoff_week', 'rounds_cut')
    list_editable = ('qualifiers_per_division', 'qualifier_percent',
                     'head_to_head_wildcard_spots', 'field_target', 'first_playoff_week')
    readonly_fields = ('rounds_cut',)
    ordering = ('-season',)


@admin.register(PlayoffEntry)
class PlayoffEntryAdmin(admin.ModelAdmin):
    list_display = ('user', 'season', 'status', 'eliminated_round', 'route', 'division')
    list_filter = ('season', 'status', 'eliminated_round', 'division')
    search_fields = ('user__username',)


@admin.register(SquaresBoard)
class SquaresBoardAdmin(admin.ModelAdmin):
    list_display = ('season', 'game', 'home_digits', 'away_digits', 'created_at')
    readonly_fields = ('home_digits', 'away_digits', 'created_at')


@admin.register(BoardSquare)
class BoardSquareAdmin(admin.ModelAdmin):
    list_display = ('board', 'row', 'col', 'owner')
    list_filter = ('board',)
    search_fields = ('owner__username',)



@admin.register(GameReaction)
class GameReactionAdmin(admin.ModelAdmin):
    list_display = ('user', 'game', 'emoji', 'created_at')
    list_filter = ('emoji',)
    search_fields = ('user__username',)

from .models import Crossfire

@admin.register(Crossfire)
class CrossfireAdmin(admin.ModelAdmin):
    list_display = ('season', 'week', 'attacker', 'target', 'game', 'attacker_side', 'target_side', 'created_at')
    list_filter = ('season', 'week')
    search_fields = ('attacker__username', 'target__username', 'game__game_id')
    raw_id_fields = ('attacker', 'target', 'game')
