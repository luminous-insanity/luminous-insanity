"""Live game chat (polling, World-of-Warcraft-vanilla style).

Rules in one place so the views stay thin:
  * One room per game. A room opens from that game's window in the Social
    drawer and is "live" while someone has posted publicly in the last
    LIVE_IDLE minutes. Going from idle to live is what the site-wide
    announcement keys off (see room_announcement / went_live_at).
  * say / emote / react lines are public to every signed-in player.
  * whisper lines are friend-to-friend only. Only the sender and the
    recipient are ever sent a whisper (see visible_messages).
  * Emote buttons reuse the existing GameReaction emojis and keep writing
    GameReaction rows, so the Live-energy reaction feed keeps working.
"""
import re
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Max, Q
from django.utils import timezone

from .models import FriendRequest, GameReaction, LiveChatMessage, LiveChatRoom
from .team_identity import team_palette

LIVE_IDLE = timedelta(minutes=10)      # silence longer than this -> room is idle
FINAL_WINDOW = timedelta(hours=6)      # matches live_game_moments()
MAX_LEN = LiveChatMessage._meta.get_field('body').max_length
BACKLOG = 60
POLL_LIMIT = 100
MIN_GAP_SECONDS = 1.0                  # one line per second per player
BURST_LINES = 8                        # ...and at most 8 lines per 15 seconds
BURST_WINDOW = timedelta(seconds=15)

_CONTROL_CHARS = re.compile(r'[\x00-\x1f\x7f]+')


class ChatError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def friend_ids(user):
    """Ids of every accepted friend of `user` (either side of the request)."""
    rows = FriendRequest.objects.filter(
        status=FriendRequest.ACCEPTED,
    ).filter(Q(sender=user) | Q(receiver=user)).values_list('sender_id', 'receiver_id')
    ids = set()
    for sender_id, receiver_id in rows:
        ids.add(receiver_id if sender_id == user.id else sender_id)
    ids.discard(user.id)
    return ids


def clean_text(raw):
    text = _CONTROL_CHARS.sub(' ', raw or '')
    return ' '.join(text.split())


def chat_window_open(game, now=None):
    """Chat is available while a game is in progress and for 6h after kickoff
    of a finished game (the same window the Live-energy list uses)."""
    now = now or timezone.now()
    if game.is_final:
        return bool(game.kickoff and (now - game.kickoff) < FINAL_WINDOW)
    return game.has_started


def room_is_live(room, now=None):
    now = now or timezone.now()
    return bool(room and (now - room.last_message_at) <= LIVE_IDLE)


def game_label(game):
    return f'{game.away_team} @ {game.home_team}'


def _team_for(user):
    try:
        return user.player_identity.favorite_team or ''
    except Exception:
        return ''


def _author_payload(user):
    code = _team_for(user)
    palette = team_palette(code) if code else None
    return {
        'id': user.id,
        'name': user.username,
        'team': code if palette else '',
        'primary': palette['primary'] if palette else '',
        'on_primary': palette['on_primary'] if palette else '',
    }


def serialize_message(msg, viewer, friends):
    return {
        'id': msg.id,
        'kind': msg.kind,
        'body': msg.body,
        'author': _author_payload(msg.author),
        'to': msg.recipient.username if msg.recipient_id else None,
        'mine': msg.author_id == viewer.id,
        'friend': msg.author_id in friends,
        'ts': int(msg.created_at.timestamp()),
    }


def visible_messages(room, user):
    """Everything `user` may see in `room`'s log.

    Public lines of this room, plus whispers they sent or received (those
    follow the player between rooms). Whispers between other people never
    match, so they can never reach another player.
    """
    return LiveChatMessage.objects.filter(is_hidden=False).filter(
        (Q(room=room) & ~Q(kind=LiveChatMessage.WHISPER))
        | (Q(kind=LiveChatMessage.WHISPER) & (Q(author=user) | Q(recipient=user)))
    ).select_related('author', 'author__player_identity', 'recipient')


# --------------------------------------------------------------------------
# reading
# --------------------------------------------------------------------------
def poll(game, user, after=None, now=None):
    """Payload for GET .../poll/. `after=None` means "first load: backlog"."""
    now = now or timezone.now()
    room = LiveChatRoom.objects.filter(game=game).first()
    payload = {
        'open': chat_window_open(game, now),
        'live': room_is_live(room, now),
        'room': bool(room),
        'game': {
            'id': game.game_id,
            'label': game_label(game),
            'status': game.status,
            'away': game.away_team, 'home': game.home_team,
            'away_score': game.away_score, 'home_score': game.home_score,
        },
        'messages': [],
        'cursor': after or 0,
    }
    if room is None:
        # No room yet: the only thing that can be waiting is a whisper.
        qs = LiveChatMessage.objects.filter(
            is_hidden=False, kind=LiveChatMessage.WHISPER,
        ).filter(Q(author=user) | Q(recipient=user)).select_related(
            'author', 'author__player_identity', 'recipient')
    else:
        qs = visible_messages(room, user)

    if after is None:
        rows = list(qs.order_by('-id')[:BACKLOG])[::-1]
    else:
        rows = list(qs.filter(id__gt=after).order_by('id')[:POLL_LIMIT])

    if rows:
        friends = friend_ids(user)
        payload['messages'] = [serialize_message(m, user, friends) for m in rows]
        payload['cursor'] = rows[-1].id
    if after is None:
        names = User.objects.filter(id__in=friend_ids(user)).order_by('username')
        payload['friends'] = [{'id': u.id, 'name': u.username} for u in names]
    return payload


def live_status(user, whisper_after=None, now=None):
    """Site-wide payload: which chats are live + any new whispers for `user`."""
    now = now or timezone.now()
    rooms = LiveChatRoom.objects.filter(
        last_message_at__gte=now - LIVE_IDLE,
    ).select_related('game', 'started_by').order_by('-went_live_at')
    live = []
    for room in rooms:
        if not chat_window_open(room.game, now):
            continue
        live.append({
            'game_id': room.game.game_id,
            'label': game_label(room.game),
            # changes every time the room goes idle -> live again
            'key': f'{room.id}:{int(room.went_live_at.timestamp())}',
            'started_by': room.started_by.username if room.started_by_id else '',
            'mine': room.started_by_id == user.id,
        })

    whispers_to_me = LiveChatMessage.objects.filter(
        is_hidden=False, kind=LiveChatMessage.WHISPER, recipient=user,
    )
    cursor = whispers_to_me.aggregate(m=Max('id'))['m'] or 0
    new = []
    if whisper_after is not None:
        rows = whispers_to_me.filter(id__gt=whisper_after).select_related(
            'author', 'room__game').order_by('id')[:5]
        for m in rows:
            new.append({
                'id': m.id,
                'from': m.author.username,
                'preview': m.body[:80],
                'game_id': m.room.game.game_id,
            })
    return {'live': live, 'whisper_cursor': cursor, 'whispers': new}


# --------------------------------------------------------------------------
# writing
# --------------------------------------------------------------------------
def _check_rate_limit(user, now):
    recent = list(
        LiveChatMessage.objects.filter(author=user)
        .exclude(kind=LiveChatMessage.SYSTEM)
        .order_by('-id').values_list('created_at', flat=True)[:BURST_LINES]
    )
    if recent and (now - recent[0]).total_seconds() < MIN_GAP_SECONDS:
        raise ChatError('Slow down a little.', status=429)
    if len(recent) >= BURST_LINES and (now - recent[-1]) < BURST_WINDOW:
        raise ChatError("You're sending messages too quickly. Take a breath.", status=429)


def open_room(game, user, now=None):
    """Start the chat for a game (or revive an idle one).

    Returns (room, went_live). `went_live` is True when this call is what made
    the room live, in which case the whole site gets the announcement.
    """
    now = now or timezone.now()
    if not chat_window_open(game, now):
        raise ChatError('Chat opens at kickoff.', status=403)
    existing = LiveChatRoom.objects.filter(game=game).first()
    if existing and room_is_live(existing, now):
        return existing, False          # fast path: already live
    with transaction.atomic():
        room, created = LiveChatRoom.objects.select_for_update().get_or_create(
            game=game,
            defaults={'started_by': user, 'went_live_at': now, 'last_message_at': now},
        )
        went_live = created
        if not created and not room_is_live(room, now):
            room.started_by = user
            room.went_live_at = now
            room.last_message_at = now
            room.save(update_fields=['started_by', 'went_live_at', 'last_message_at'])
            went_live = True
        if went_live:
            LiveChatMessage.objects.create(
                room=room, author=user, kind=LiveChatMessage.SYSTEM,
                body=f'{user.username} started the chat.',
            )
    return room, went_live


def post_message(game, user, body='', kind=LiveChatMessage.SAY, to=None, emoji=None, now=None):
    """Validate and store one chat line. Returns the LiveChatMessage."""
    now = now or timezone.now()
    if not chat_window_open(game, now):
        raise ChatError('Chat is closed for this game.', status=403)
    if kind not in (LiveChatMessage.SAY, LiveChatMessage.EMOTE,
                    LiveChatMessage.REACT, LiveChatMessage.WHISPER):
        raise ChatError('Unknown message type.')

    recipient = None
    if kind == LiveChatMessage.REACT:
        if emoji not in dict(GameReaction.choices):
            raise ChatError('Pick a valid reaction.')
        body = emoji
    else:
        body = clean_text(body)
        if not body:
            raise ChatError('Type something first.')
        if len(body) > MAX_LEN:
            raise ChatError(f'Messages are limited to {MAX_LEN} characters.')

    if kind == LiveChatMessage.WHISPER:
        name = clean_text(to)
        if not name:
            raise ChatError('Whisper to whom?')
        recipient = User.objects.filter(username__iexact=name).first()
        if recipient is None or recipient.id == user.id:
            raise ChatError(f'No friend named {name}.', status=404)
        if recipient.id not in friend_ids(user):
            raise ChatError('You can only whisper to friends.', status=403)

    _check_rate_limit(user, now)
    if kind == LiveChatMessage.WHISPER:
        # A whisper needs a room to hang off, but must never make the room
        # "live" or trigger the site-wide announcement: park it as idle.
        room = LiveChatRoom.objects.filter(game=game).first()
        if room is None:
            stale = now - LIVE_IDLE - timedelta(seconds=1)
            room, _ = LiveChatRoom.objects.get_or_create(
                game=game,
                defaults={'started_by': None, 'went_live_at': stale, 'last_message_at': stale},
            )
    else:
        room, _ = open_room(game, user, now)

    with transaction.atomic():
        msg = LiveChatMessage.objects.create(
            room=room, author=user, recipient=recipient, kind=kind, body=body,
        )
        if kind != LiveChatMessage.WHISPER:
            # Whispers are private: they never keep a public room "live".
            LiveChatRoom.objects.filter(pk=room.pk).update(last_message_at=now)
        if kind == LiveChatMessage.REACT:
            GameReaction.objects.update_or_create(
                user=user, game=game, defaults={'emoji': emoji},
            )
    msg.author = user
    msg.recipient = recipient
    return msg

