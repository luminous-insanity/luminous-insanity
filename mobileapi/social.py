from .common import *

class FriendsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        accepted = FriendRequest.objects.filter(status=FriendRequest.ACCEPTED).filter(
            Q(sender=request.user) | Q(receiver=request.user)
        ).select_related('sender', 'receiver')
        friends = []
        for row in accepted:
            friend = row.receiver if row.sender_id == request.user.id else row.sender
            friends.append({'id': friend.id, 'username': friend.username})
        incoming = FriendRequest.objects.filter(receiver=request.user, status=FriendRequest.PENDING).select_related('sender').order_by('-created_at')
        outgoing = FriendRequest.objects.filter(sender=request.user, status=FriendRequest.PENDING).select_related('receiver').order_by('-created_at')
        return Response({
            'friends': friends,
            'incoming': [{'id': r.id, 'user': {'id': r.sender_id, 'username': r.sender.username}, 'created_at': r.created_at.isoformat()} for r in incoming],
            'outgoing': [{'id': r.id, 'user': {'id': r.receiver_id, 'username': r.receiver.username}, 'created_at': r.created_at.isoformat()} for r in outgoing],
        })


class FriendSearchView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = str(request.query_params.get('q', '')).strip()
        if len(query) < 2:
            return Response({'results': []})
        users = User.objects.filter(username__icontains=query, is_active=True, is_superuser=False).exclude(pk=request.user.pk).order_by('username')[:20]
        return Response({'results': [{'id': u.id, 'username': u.username} for u in users]})


class FriendRequestView(APIView):
    permission_classes = [IsAuthenticated]

    @idempotent
    def post(self, request):
        try:
            target_id = int(request.data.get('user_id'))
        except (TypeError, ValueError):
            return Response({'detail': 'A valid user_id is required.'}, status=400)
        target = User.objects.filter(pk=target_id, is_active=True, is_superuser=False).first()
        if not target or target.pk == request.user.pk:
            return Response({'detail': 'That player cannot receive a friend request.'}, status=400)
        existing = FriendRequest.objects.filter(
            Q(sender=request.user, receiver=target) | Q(sender=target, receiver=request.user)
        ).first()
        if existing:
            if existing.status == FriendRequest.ACCEPTED:
                return Response({'detail': 'You are already friends.'}, status=409)
            if existing.sender_id == target.pk:
                return Response({'detail': 'That player has already sent you a request.'}, status=409)
            return Response({'detail': 'A request is already pending.'}, status=409)
        row = FriendRequest.objects.create(sender=request.user, receiver=target)
        touch_activity(request.user)
        return Response({'id': row.id, 'status': row.status}, status=201)


class FriendRespondView(APIView):
    permission_classes = [IsAuthenticated]

    @idempotent
    def post(self, request, request_id):
        action = request.data.get('action')
        row = get_object_or_404(FriendRequest, pk=request_id)
        if row.receiver_id != request.user.pk or row.status != FriendRequest.PENDING:
            return Response({'detail': 'This request cannot be changed by this account.'}, status=403)
        if action not in ('accept', 'decline'):
            return Response({'detail': 'Action must be accept or decline.'}, status=400)
        if action == 'accept':
            row.status = FriendRequest.ACCEPTED
            row.receiver_seen = True
            row.save(update_fields=['status', 'receiver_seen'])
            touch_activity(request.user)
        else:
            row.delete()
        return Response({'ok': True, 'status': action})


class NotificationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        requests_qs = FriendRequest.objects.filter(receiver=request.user, status=FriendRequest.PENDING).select_related('sender').order_by('-created_at')
        unread_reactions = PerformanceReaction.objects.filter(player=request.user, is_read=False).count()
        reactions_qs = PerformanceReaction.objects.filter(player=request.user).select_related('reactor').order_by('-created_at')[:50]
        return Response({
            'unread_count': requests_qs.filter(receiver_seen=False).count() + unread_reactions,
            'friend_requests': [{'id': r.id, 'username': r.sender.username, 'created_at': r.created_at.isoformat(), 'read': r.receiver_seen} for r in requests_qs],
            'performance_reactions': [{'id': r.id, 'from': r.reactor.username, 'emoji': r.emoji,
                                       'season': r.season, 'week': r.week,
                                       'created_at': r.created_at.isoformat(), 'read': r.is_read} for r in reactions_qs],
        })

    def post(self, request):
        FriendRequest.objects.filter(receiver=request.user, status=FriendRequest.PENDING, receiver_seen=False).update(receiver_seen=True)
        PerformanceReaction.objects.filter(player=request.user, is_read=False).update(is_read=True)
        return Response({'ok': True})


class ChatStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            after = max(0, int(request.query_params.get('whisper_after', 0)))
        except (TypeError, ValueError):
            after = 0
        return Response(chat.live_status(request.user, whisper_after=after))


class ChatGameView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, game_id):
        game = Game.objects.filter(game_id=game_id).first()
        if not game:
            return Response({'detail': 'Game not found.'}, status=404)
        try:
            after = max(0, int(request.query_params.get('after', 0)))
        except (TypeError, ValueError):
            after = 0
        return Response(chat.poll(game, request.user, after=after))

    @idempotent
    def post(self, request, game_id):
        game = Game.objects.filter(game_id=game_id).first()
        if not game:
            return Response({'detail': 'Game not found.'}, status=404)
        action = request.data.get('action', 'send')
        try:
            if action == 'start':
                _room, went_live = chat.open_room(game, request.user)
                return Response({'ok': True, 'went_live': went_live})
            if action != 'send':
                return Response({'detail': 'Action must be start or send.'}, status=400)
            body = request.data.get('body', '')
            recipient = request.data.get('to')
            emoji = request.data.get('emoji')
            kind = request.data.get('kind') or LiveChatMessage.SAY
            if (not isinstance(body, str) or (recipient is not None and not isinstance(recipient, str))
                    or not isinstance(kind, str) or (emoji is not None and not isinstance(emoji, str))):
                return Response({'detail': 'Message body, type, recipient, and emoji must be text.'}, status=400)
            msg = chat.post_message(
                game, request.user, body=body,
                kind=kind, to=recipient, emoji=emoji,
            )
        except chat.ChatError as exc:
            return Response({'detail': exc.message}, status=exc.status)
        return Response({'ok': True, 'message': chat.serialize_message(msg, request.user, chat.friend_ids(request.user))}, status=201)


class DeviceRegistrationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)
        return Response({'preferences': self._prefs(prefs), 'devices': [
            {'id': d.id, 'platform': d.platform, 'device_name': d.device_name, 'last_seen_at': d.last_seen_at.isoformat()}
            for d in Device.objects.filter(user=request.user, is_active=True)
        ]})

    @staticmethod
    def _prefs(prefs):
        return {field: getattr(prefs, field) for field in (
            'friend_requests', 'challenges', 'whispers', 'relay_turns',
            'pick_reminders', 'game_results', 'crossfire_resolved')}

    @idempotent
    def post(self, request):
        token = str(request.data.get('token') or '').strip()
        platform = request.data.get('platform')
        device_name = str(request.data.get('device_name') or '')[:100]
        if not token or platform not in (Device.ANDROID, Device.IOS):
            return Response({'detail': 'A device token and android/ios platform are required.'}, status=400)
        device, _ = Device.objects.update_or_create(
            token=token,
            defaults={'user': request.user, 'platform': platform, 'device_name': device_name,
                      'is_active': True, 'last_seen_at': timezone.now()},
        )
        return Response({'id': device.id, 'registered': True}, status=201)

    @idempotent
    def patch(self, request):
        allowed = ('friend_requests', 'challenges', 'whispers', 'relay_turns', 'pick_reminders', 'game_results', 'crossfire_resolved')
        unknown = set(request.data.keys()) - set(allowed)
        if unknown:
            return Response({'detail': f'Unsupported preference: {sorted(unknown)[0]}'}, status=400)
        prefs, _ = NotificationPreference.objects.get_or_create(user=request.user)
        for field in allowed:
            if field in request.data:
                if not isinstance(request.data[field], bool):
                    return Response({'detail': f'{field} must be true or false.'}, status=400)
                setattr(prefs, field, request.data[field])
        prefs.save()
        return Response({'preferences': self._prefs(prefs)})

    @idempotent
    def delete(self, request):
        token = str(request.data.get('token') or request.query_params.get('token') or '').strip()
        if not token:
            return Response({'detail': 'Device token is required.'}, status=400)
        Device.objects.filter(user=request.user, token=token).update(is_active=False)
        return Response(status=204)


class GameReactionView(APIView):
    permission_classes = [IsAuthenticated]

    @idempotent
    def post(self, request, game_id):
        from accounts.models import GameReaction
        game = Game.objects.filter(game_id=game_id).first()
        if not game:
            return Response({'detail': 'Game not found.'}, status=404)
        emoji = str(request.data.get('emoji') or '').strip()
        if emoji not in dict(GameReaction.choices):
            return Response({'detail': 'Choose a valid game reaction.'}, status=400)
        if not game.has_started:
            return Response({'detail': 'Game reactions open at kickoff.'}, status=409)
        reaction, created = GameReaction.objects.update_or_create(
            user=request.user, game=game, defaults={'emoji': emoji},
        )
        return Response({'created': created, 'game_id': game.game_id, 'emoji': reaction.emoji})


class PerformanceReactionView(APIView):
    permission_classes = [IsAuthenticated]

    @idempotent
    def post(self, request):
        try:
            player_id = int(request.data.get('player_id'))
            season = int(request.data.get('season', settings.NFL_SEASON))
            week = int(request.data.get('week', default_week(settings.NFL_SEASON)))
        except (TypeError, ValueError):
            return Response({'detail': 'player_id, season, and week must be valid numbers.'}, status=400)
        player = User.objects.filter(pk=player_id, is_superuser=False).first()
        if not player or player.pk == request.user.pk:
            return Response({'detail': 'That player cannot receive this reaction.'}, status=400)
        if not 1 <= week <= 22:
            return Response({'detail': 'Week must be between 1 and 22.'}, status=400)
        emoji = request.data.get('emoji')
        if emoji not in dict(PerformanceReaction.choices):
            return Response({'detail': 'Choose a valid performance reaction.'}, status=400)
        existing = PerformanceReaction.objects.filter(
            reactor=request.user, player=player, season=season, week=week,
        ).first()
        if existing and existing.emoji == emoji:
            existing.delete()
            return Response({'removed': True})
        reaction, _ = PerformanceReaction.objects.update_or_create(
            reactor=request.user, player=player, season=season, week=week,
            defaults={'emoji': emoji},
        )
        return Response({'removed': False, 'emoji': reaction.emoji})


