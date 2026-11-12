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


# ---------------------------------------------------------------------------
# Chat moderation
# ---------------------------------------------------------------------------
from django.contrib import messages as admin_messages  # noqa: E402

from . import moderation  # noqa: E402
from .models import ChatBlock, ChatReport, ChatSanction  # noqa: E402


@admin.register(ChatReport)
class ChatReportAdmin(admin.ModelAdmin):
    """Review queue for reported chat lines. Open reports first.

    Pick reports, then use the Action menu: dismiss, hide the line, or hide it
    and time the player out (15 minutes, 24 hours, or until you lift it).
    """
    list_display = ('created_at', 'status', 'reason', 'reported_user', 'short_body',
                    'game_label', 'reporter', 'reviewed_by')
    list_filter = ('status', 'reason')
    search_fields = ('reported_user__username', 'reporter__username', 'body_snapshot')
    raw_id_fields = ('reporter', 'reported_user', 'message', 'reviewed_by')
    readonly_fields = ('created_at', 'reviewed_at')
    actions = ('dismiss_reports', 'hide_message', 'hide_and_timeout_15m',
               'hide_and_timeout_24h', 'hide_and_mute_until_lifted')

    @admin.display(description='Message')
    def short_body(self, obj):
        return (obj.body_snapshot[:60] + '…') if len(obj.body_snapshot) > 60 else obj.body_snapshot

    def _resolve(self, request, queryset, action, minutes=None):
        closed = moderation.resolve_reports(queryset, request.user, action, minutes=minutes)
        self.message_user(request, f'{closed} report(s) closed.', admin_messages.SUCCESS)

    @admin.action(description='Dismiss (no action)')
    def dismiss_reports(self, request, queryset):
        self._resolve(request, queryset, 'dismiss')

    @admin.action(description='Hide the message')
    def hide_message(self, request, queryset):
        self._resolve(request, queryset, 'hide')

    @admin.action(description='Hide the message + time player out 15 minutes')
    def hide_and_timeout_15m(self, request, queryset):
        self._resolve(request, queryset, 'hide_timeout', minutes=15)

    @admin.action(description='Hide the message + time player out 24 hours')
    def hide_and_timeout_24h(self, request, queryset):
        self._resolve(request, queryset, 'hide_timeout', minutes=24 * 60)

    @admin.action(description='Hide the message + mute player until I lift it')
    def hide_and_mute_until_lifted(self, request, queryset):
        self._resolve(request, queryset, 'hide_timeout', minutes=None)


@admin.register(ChatSanction)
class ChatSanctionAdmin(admin.ModelAdmin):
    """Timeouts from live chat. Add one by hand, or lift one with the action."""
    list_display = ('user', 'until', 'source', 'reason', 'created_by', 'created_at', 'revoked', 'active_now')
    list_filter = ('source', 'revoked')
    search_fields = ('user__username', 'reason')
    raw_id_fields = ('user', 'created_by')
    actions = ('lift_sanctions',)

    @admin.display(boolean=True, description='Active')
    def active_now(self, obj):
        return obj.is_active

    def save_model(self, request, obj, form, change):
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.action(description='Lift selected timeouts')
    def lift_sanctions(self, request, queryset):
        count = queryset.update(revoked=True)
        self.message_user(request, f'{count} timeout(s) lifted.', admin_messages.SUCCESS)


@admin.register(ChatBlock)
class ChatBlockAdmin(admin.ModelAdmin):
    """Read-only view of who has muted or blocked whom (useful for spotting abuse)."""
    list_display = ('blocker', 'blocked', 'kind', 'created_at')
    list_filter = ('kind',)
    search_fields = ('blocker__username', 'blocked__username')
    raw_id_fields = ('blocker', 'blocked')


# ---------------------------------------------------------------------------
# Private leagues
# ---------------------------------------------------------------------------
from .models import League, LeagueMembership  # noqa: E402


class LeagueMembershipInline(admin.TabularInline):
    model = LeagueMembership
    extra = 0
    raw_id_fields = ('user',)


@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'invite_code', 'is_open', 'member_count', 'created_at')
    list_filter = ('is_open',)
    search_fields = ('name', 'owner__username', 'invite_code')
    raw_id_fields = ('owner',)
    readonly_fields = ('invite_code', 'created_at')
    inlines = [LeagueMembershipInline]

    @admin.display(description='Members')
    def member_count(self, obj):
        return obj.memberships.count()


# ---------------------------------------------------------------------------
# Tiebreaker: The Score is Right
# ---------------------------------------------------------------------------
from .models import TiebreakerGame, TiebreakerPick  # noqa: E402


@admin.register(TiebreakerGame)
class TiebreakerGameAdmin(admin.ModelAdmin):
    """Optional. Without a row, the last game of the week is the tiebreaker."""
    list_display = ('season', 'week', 'game')
    list_filter = ('season',)
    raw_id_fields = ('game',)


@admin.register(TiebreakerPick)
class TiebreakerPickAdmin(admin.ModelAdmin):
    list_display = ('user', 'game', 'total_points', 'updated_at')
    list_filter = ('game__season', 'game__week')
    search_fields = ('user__username', 'game__game_id')
    raw_id_fields = ('user', 'game')
