from django.conf import settings
from django.db import models
from django.utils import timezone


class Device(models.Model):
    """A registered mobile device token. No push provider is called here."""
    ANDROID = 'android'
    IOS = 'ios'
    PLATFORM_CHOICES = [(ANDROID, 'Android'), (IOS, 'iOS')]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mobile_devices')
    token = models.CharField(max_length=512, unique=True)
    platform = models.CharField(max_length=10, choices=PLATFORM_CHOICES)
    device_name = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_seen_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-last_seen_at']
        indexes = [models.Index(fields=['user', 'is_active'], name='mobile_device_user_active_idx')]

    def __str__(self):
        return f'{self.user_id} · {self.platform} · {self.pk}'


class NotificationPreference(models.Model):
    """Per-user push preferences; delivery is added when FCM is configured."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mobile_notification_preferences')
    friend_requests = models.BooleanField(default=True)
    challenges = models.BooleanField(default=True)
    whispers = models.BooleanField(default=True)
    relay_turns = models.BooleanField(default=True)
    pick_reminders = models.BooleanField(default=False)
    game_results = models.BooleanField(default=False)
    crossfire_resolved = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Notification preferences for {self.user_id}'


class IdempotencyRecord(models.Model):
    """Cached response for a retryable mobile mutation keyed by the client."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mobile_idempotency_records')
    key = models.CharField(max_length=128)
    method = models.CharField(max_length=8)
    path = models.CharField(max_length=255)
    request_hash = models.CharField(max_length=64)
    response_status = models.PositiveSmallIntegerField(default=0)
    response_body = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'key'], name='mobile_unique_idempotency_key')]
        indexes = [models.Index(fields=['created_at'], name='mobile_idem_created_idx')]

    def __str__(self):
        return f'{self.user_id} · {self.key}'
