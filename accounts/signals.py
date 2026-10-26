"""
Records "meaningful activity" for the inactive-account rule.

Meaningful = logging in, making or changing a pick, or interacting with
friends (sending a request, or accepting one). Just browsing pages is NOT
counted, so a bot or a stray page view can't keep a dead account alive.
"""
from django.contrib.auth.signals import user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Challenge, FriendRequest, Pick, UserActivity


def touch_activity(user):
    if user is None or not getattr(user, 'pk', None):
        return
    UserActivity.objects.update_or_create(
        user_id=user.pk,
        defaults={'last_active': timezone.now()},
    )


@receiver(user_logged_in)
def _on_login(sender, request, user, **kwargs):
    touch_activity(user)


@receiver(post_save, sender=Pick)
def _on_pick(sender, instance, **kwargs):
    touch_activity(instance.user)


@receiver(post_save, sender=FriendRequest)
def _on_friend_request(sender, instance, created, **kwargs):
    if created:
        touch_activity(instance.sender)
    elif instance.status == FriendRequest.ACCEPTED:
        touch_activity(instance.receiver)


@receiver(post_save, sender=Challenge)
def _on_challenge(sender, instance, created, **kwargs):
    if created:
        touch_activity(instance.challenger)
    elif instance.status == Challenge.ACCEPTED:
        touch_activity(instance.opponent)
