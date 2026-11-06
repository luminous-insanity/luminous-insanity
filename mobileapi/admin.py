from django.contrib import admin

from .models import Device, IdempotencyRecord, NotificationPreference


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'platform', 'device_name', 'is_active', 'last_seen_at')
    list_filter = ('platform', 'is_active')
    search_fields = ('user__username', 'user__email', 'device_name')
    readonly_fields = ('created_at', 'updated_at', 'last_seen_at')
    exclude = ('token',)


@admin.register(NotificationPreference)
class NotificationPreferenceAdmin(admin.ModelAdmin):
    list_display = ('user', 'friend_requests', 'challenges', 'whispers', 'relay_turns')
    search_fields = ('user__username', 'user__email')


@admin.register(IdempotencyRecord)
class IdempotencyRecordAdmin(admin.ModelAdmin):
    list_display = ('user', 'key', 'method', 'path', 'response_status', 'created_at')
    search_fields = ('user__username', 'key', 'path')
    readonly_fields = ('user', 'key', 'method', 'path', 'response_status', 'response_body', 'created_at')
