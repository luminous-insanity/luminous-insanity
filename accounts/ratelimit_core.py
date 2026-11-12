"""Fixed-window rate counting with no Django imports (easy to test).

`cache` is anything with Django's cache API: add(), incr(), set().
"""
import hashlib


def safe_ident(value):
    """Short, cache-key-safe form of an IP, username or user id."""
    return hashlib.sha1(str(value).encode('utf-8', 'replace')).hexdigest()[:20]


def window_key(scope, ident, window, now):
    return f'rl:{scope}:{safe_ident(ident)}:{int(now // window)}'


def fixed_window_hit(cache, scope, ident, limit, window, now):
    """Count one attempt. Returns (allowed, attempts_so_far, retry_after_seconds).

    The first `limit` attempts inside a window are allowed; the rest are
    refused until the window rolls over. A cache that can't count never
    blocks anyone (fails open).
    """
    key = window_key(scope, ident, window, now)
    retry_after = max(1, int(window - (now % window)))
    try:
        cache.add(key, 0, window + 5)
        try:
            count = cache.incr(key)
        except ValueError:          # expired between add() and incr()
            cache.set(key, 1, window + 5)
            count = 1
    except Exception:               # cache unavailable: never lock people out
        return True, 0, 0
    return count <= limit, count, retry_after
