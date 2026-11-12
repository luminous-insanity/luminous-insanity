"""JSON endpoints for live game chat. Isolated from the core picks views.

All endpoints answer 401 JSON (not a login redirect) when the session has
expired so the polling script can stop quietly.
"""
from functools import wraps

from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST

from api.models import Game

from . import chat, moderation
from .models import ChatReport, LiveChatMessage
from .ratelimit import ratelimit


def _json_login_required(view):
    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return _no_store(JsonResponse({'error': 'Please log in again.'}, status=401))
        return view(request, *args, **kwargs)
    return wrapper


def _no_store(response):
    response['Cache-Control'] = 'no-store'
    return response


def _int_or_none(value):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def _game_or_404(game_id):
    game = Game.objects.filter(game_id=game_id).first()
    if game is None:
        return None, _no_store(JsonResponse({'error': 'Game not found.'}, status=404))
    return game, None


@_json_login_required
@require_GET
def chat_status(request):
    """Site-wide: which chats are live, and any new whispers for the viewer."""
    data = chat.live_status(
        request.user, whisper_after=_int_or_none(request.GET.get('whisper_after')),
    )
    return _no_store(JsonResponse(data))


@_json_login_required
@require_GET
def chat_poll(request, game_id):
    """Polled about once a second by the open chat panel."""
    game, error = _game_or_404(game_id)
    if error:
        return error
    data = chat.poll(game, request.user, after=_int_or_none(request.GET.get('after')))
    return _no_store(JsonResponse(data))


@_json_login_required
@require_POST
def chat_start(request, game_id):
    """The game window's "Start chat" button."""
    game, error = _game_or_404(game_id)
    if error:
        return error
    try:
        _room, went_live = chat.open_room(game, request.user)
    except chat.ChatError as exc:
        return _no_store(JsonResponse({'error': exc.message}, status=exc.status))
    return _no_store(JsonResponse({'ok': True, 'went_live': went_live}))


@_json_login_required
@require_POST
@ratelimit('chat_send', limit=40, window=60, key='user', as_json=True,
           message="You're sending messages too quickly. Take a breath.")
def chat_send(request, game_id):
    game, error = _game_or_404(game_id)
    if error:
        return error
    kind = request.POST.get('kind') or LiveChatMessage.SAY
    try:
        msg = chat.post_message(
            game, request.user,
            body=request.POST.get('body', ''),
            kind=kind,
            to=request.POST.get('to'),
            emoji=request.POST.get('emoji'),
        )
    except chat.ChatError as exc:
        return _no_store(JsonResponse({'error': exc.message}, status=exc.status))
    friends = chat.friend_ids(request.user)
    return _no_store(JsonResponse({
        'ok': True,
        'message': chat.serialize_message(msg, request.user, friends),
    }))


# --------------------------------------------------------------------------
# Moderation: report a line, mute / block a player
# --------------------------------------------------------------------------
@_json_login_required
@require_POST
@ratelimit('chat_report', limit=10, window=3600, key='user', as_json=True,
           message='You have sent a lot of reports. Please try again later.')
def chat_report(request):
    """A player reports one chat line for staff to review."""
    message_id = _int_or_none(request.POST.get('message_id'))
    if not message_id:
        return _no_store(JsonResponse({'error': 'Choose a message to report.'}, status=400))
    try:
        report, created = moderation.report_message(
            request.user, message_id,
            reason=request.POST.get('reason', ''),
            details=request.POST.get('details', ''),
        )
    except moderation.ModerationBlocked as exc:
        return _no_store(JsonResponse({'error': exc.message}, status=exc.status))
    note = ('Thanks. Staff will review this report.' if created
            else 'You already reported this message.')
    return _no_store(JsonResponse({'ok': True, 'created': created, 'message': note}))


@_json_login_required
@require_POST
@ratelimit('chat_block', limit=30, window=600, key='user', as_json=True)
def chat_block(request):
    """Mute, block, unmute or unblock a player (by username)."""
    try:
        note = moderation.set_block(
            request.user, request.POST.get('username', ''), request.POST.get('action', ''))
    except moderation.ModerationBlocked as exc:
        return _no_store(JsonResponse({'error': exc.message}, status=exc.status))
    return _no_store(JsonResponse({
        'ok': True, 'message': note, 'blocks': moderation.list_blocks(request.user)}))


@_json_login_required
@require_GET
def chat_blocks(request):
    """Who the viewer has muted or blocked."""
    return _no_store(JsonResponse({'blocks': moderation.list_blocks(request.user)}))


REPORT_REASONS = [{'value': value, 'label': label} for value, label in ChatReport.REASON_CHOICES]
