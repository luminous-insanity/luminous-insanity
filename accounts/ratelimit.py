"""Simple rate limiting for views, backed by Django's cache.

    @ratelimit('login', limit=10, window=300, key='ip')
    def login_view(request): ...

Counts live in the "ratelimit" cache (a file cache, shared by every web
worker; see CACHES in settings). Set RATELIMIT_ENABLED = False to switch it
all off. The Flutter API keeps using DRF's built-in throttling (see
REST_FRAMEWORK in settings).
"""
import time
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.core.cache import InvalidCacheBackendError, caches
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import resolve_url
from django.utils.http import url_has_allowed_host_and_scheme

from .ratelimit_core import fixed_window_hit

DEFAULT_MESSAGE = 'Too many attempts. Please wait a bit and try again.'


def _cache():
    alias = getattr(settings, 'RATELIMIT_CACHE_ALIAS', 'ratelimit')
    try:
        return caches[alias]
    except InvalidCacheBackendError:
        return caches['default']


def client_ip(request):
    """Best guess at the caller's IP.

    Behind a proxy (PythonAnywhere, Render, ...) REMOTE_ADDR is the proxy, so
    the real address is in X-Forwarded-For. The proxy appends the address it
    saw to the END of that header, and everything before it is client-supplied
    and can be faked, so the last entry is the one to trust.
    """
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        last = forwarded.split(',')[-1].strip()
        if last:
            return last
    return request.META.get('REMOTE_ADDR', '') or 'unknown'


def _identifier(request, key):
    if callable(key):
        return key(request)
    user = getattr(request, 'user', None)
    authed = bool(user is not None and user.is_authenticated)
    if key == 'user':
        return f'u{user.pk}' if authed else f'ip{client_ip(request)}'
    if key == 'user_or_ip':
        return f'u{user.pk}' if authed else f'ip{client_ip(request)}'
    return f'ip{client_ip(request)}'


def check_rate_limit(request, scope, limit, window, key='ip'):
    """Count one attempt. Returns (allowed, retry_after_seconds)."""
    if not getattr(settings, 'RATELIMIT_ENABLED', True):
        return True, 0
    ident = _identifier(request, key)
    if not ident:
        return True, 0
    allowed, _count, retry_after = fixed_window_hit(
        _cache(), scope, ident, limit, window, time.time())
    return allowed, retry_after


def wants_json(request):
    accept = request.headers.get('Accept', '')
    return ('application/json' in accept
            or request.headers.get('X-Requested-With') == 'XMLHttpRequest')


def too_many(request, retry_after, message=DEFAULT_MESSAGE, fallback=None, as_json=None):
    """429 JSON for fetch() callers; flash message + redirect for page forms."""
    if as_json is None:
        as_json = wants_json(request)
    if as_json:
        response = JsonResponse({'error': message, 'retry_after': retry_after}, status=429)
        response['Retry-After'] = str(retry_after)
        response['Cache-Control'] = 'no-store'
        return response
    messages.error(request, message)
    referer = request.META.get('HTTP_REFERER', '')
    if referer and url_has_allowed_host_and_scheme(
            referer, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return HttpResponseRedirect(referer)
    target = resolve_url(fallback) if fallback else request.path
    return HttpResponseRedirect(target)


def ratelimit(scope, limit, window, key='ip', methods=('POST',), message=DEFAULT_MESSAGE,
              fallback=None, as_json=None):
    """Limit a view to `limit` calls per `window` seconds per key.

    key: 'ip', 'user' (falls back to IP when logged out) or a callable
         request -> identifier (return None to skip limiting that request).
    methods: only these HTTP methods are counted (default POST only).
    fallback: URL name to redirect to when there is no usable Referer.
    """
    wanted = {m.upper() for m in methods}

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method.upper() in wanted:
                allowed, retry_after = check_rate_limit(request, scope, limit, window, key)
                if not allowed:
                    return too_many(request, retry_after, message, fallback, as_json)
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


def username_key(field='username'):
    """key= helper: limit by the account name being attempted (stops
    credential stuffing that rotates IP addresses)."""
    def _key(request):
        value = (request.POST.get(field) or '').strip().lower()[:80]
        return f'name:{value}' if value else None
    return _key
