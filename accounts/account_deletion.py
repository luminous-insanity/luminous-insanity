"""Account deletion that never changes anyone else's records.

The user row is kept but anonymized and deactivated, instead of being removed.
Deleting the row would cascade through picks, challenges, leagues and playoff
entries and would shift other players' standings, ranks and head-to-head
records. Keeping the (now anonymous) row means every other player's numbers
stay exactly as they were. The person's own personal data is removed:
name, email, password, linked Google account, devices/push tokens, friend
links, chat text and sign-in tokens.

Deactivated accounts are also excluded from future playoff qualification (see
accounts/django_adapter.build_player_records), so a deleted player can never
take a playoff seat or a Super Bowl square.
"""
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q

DELETED_MESSAGE = '[deleted]'


def delete_account(user):
    """Anonymize and deactivate `user`. Safe to call twice."""
    from accounts.models import FriendRequest, LiveChatMessage, PlayerIdentity
    from mobileapi.models import (
        Device, IdempotencyRecord, NotificationPreference, PickReminderLog,
    )

    User = get_user_model()
    with transaction.atomic():
        # Sign-in tokens: blacklist every outstanding refresh token.
        from rest_framework_simplejwt.token_blacklist.models import (
            BlacklistedToken, OutstandingToken,
        )
        for token in OutstandingToken.objects.filter(user=user):
            BlacklistedToken.objects.get_or_create(token=token)

        Device.objects.filter(user=user).delete()
        NotificationPreference.objects.filter(user=user).delete()
        IdempotencyRecord.objects.filter(user=user).delete()
        PickReminderLog.objects.filter(user=user).delete()
        FriendRequest.objects.filter(Q(sender=user) | Q(receiver=user)).delete()

        # Chat: blank the text but keep the rows so moderation records stay intact.
        LiveChatMessage.objects.filter(author=user).update(body=DELETED_MESSAGE)
        LiveChatMessage.objects.filter(recipient=user).update(body=DELETED_MESSAGE)

        # Linked Google account and email records.
        from allauth.account.models import EmailAddress
        from allauth.socialaccount.models import SocialAccount
        SocialAccount.objects.filter(user=user).delete()
        EmailAddress.objects.filter(user=user).delete()

        PlayerIdentity.objects.filter(user=user).update(favorite_team='', active_title='')

        locked = User.objects.select_for_update().get(pk=user.pk)
        locked.username = f'deleted-{locked.pk}'
        locked.email = ''
        locked.first_name = ''
        locked.last_name = ''
        locked.is_active = False
        locked.set_unusable_password()
        locked.save()
    return True
