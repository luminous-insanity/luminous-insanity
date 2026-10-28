from django.contrib import admin
from .models import Pick, UserStatistics, AchievementUnlock  # Import the models

# Register the Pick model
@admin.register(Pick)
class PickAdmin(admin.ModelAdmin):
    list_display = ('user', 'game', 'team_picked')  # Columns to display in admin list view
    list_filter = ('team_picked',)  # Add a filter by team picked
    search_fields = ('user__username', 'game__game_id')  # Add search fields for user and game

# Register the UserStatistics model
@admin.register(UserStatistics)
class UserStatisticsAdmin(admin.ModelAdmin):
    list_display = ('user', 'wins', 'losses', 'ties')  # Display user statistics
    search_fields = ('user__username',)  # Add search field for user


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

