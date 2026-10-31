from django.contrib import admin
from .models import (
    RelayAbility, RelayAbilityVote, RelayDraftTurn, RelayMatch, RelayMatchSide,
    RelayPick, RelayQueueEntry, RelayTeam, RelayTeamMember,
)


class RelayTeamMemberInline(admin.TabularInline):
    model = RelayTeamMember
    extra = 0


@admin.register(RelayTeam)
class RelayTeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'season', 'week', 'owner', 'status', 'is_random', 'created_at')
    list_filter = ('season', 'week', 'status', 'is_random')
    search_fields = ('name', 'owner__username', 'invite_code')
    inlines = [RelayTeamMemberInline]


class RelayPickInline(admin.TabularInline):
    model = RelayPick
    extra = 0


@admin.register(RelayMatch)
class RelayMatchAdmin(admin.ModelAdmin):
    list_display = ('season', 'week', 'team_a', 'team_b', 'status', 'lock_at')
    list_filter = ('season', 'week', 'status')
    inlines = [RelayPickInline]


admin.site.register((RelayQueueEntry, RelayTeamMember, RelayMatchSide, RelayDraftTurn, RelayPick, RelayAbility, RelayAbilityVote))
