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


from .models import LiveChatMessage, LiveChatRoom


@admin.register(LiveChatRoom)
class LiveChatRoomAdmin(admin.ModelAdmin):
    list_display = ('game', 'started_by', 'went_live_at', 'last_message_at')
    raw_id_fields = ('game', 'started_by')


@admin.register(LiveChatMessage)
class LiveChatMessageAdmin(admin.ModelAdmin):
    """Read/hide only for now; hiding removes a line from every player's chat."""
    list_display = ('created_at', 'room', 'author', 'kind', 'recipient', 'body', 'is_hidden')
    list_filter = ('kind', 'is_hidden')
    search_fields = ('author__username', 'recipient__username', 'body')
    raw_id_fields = ('room', 'author', 'recipient')
    actions = ('hide_selected', 'unhide_selected')

    @admin.action(description='Hide selected messages')
    def hide_selected(self, request, queryset):
        queryset.update(is_hidden=True)

    @admin.action(description='Unhide selected messages')
    def unhide_selected(self, request, queryset):
        queryset.update(is_hidden=False)
