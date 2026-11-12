"""Chat text screening: pure Python, no Django, easy to test.

Three outcomes for a message:
  allow  sent as typed
  mask   sent with strong profanity starred out (f***)
  block  refused, with a reason shown to the sender

What it catches out of the box:
  * strong profanity            -> masked (token based, so "class" is safe)
  * threats / self-harm baiting -> blocked ("kill yourself", "kys", ...)
  * phone numbers and emails    -> blocked (stops doxxing and scams)
  * links                       -> blocked unless links are allowed
  * word spam ("buy buy buy..") -> blocked; long letter runs are shortened

What it does NOT ship with: a slur list. Add your own terms in settings
(CHAT_BLOCKED_TERMS) or let the AI moderator hook handle it. Terms of five or
more characters match inside words ("squashed" text, which also catches
"s p a c e d" and "l33t" spellings); shorter terms match whole words only so
innocent words are not caught.
"""
import re
from dataclasses import dataclass

ALLOW, MASK, BLOCK = 'allow', 'mask', 'block'

# Starter list: strong profanity only. Football trash talk ("hell", "damn",
# "suck") is deliberately left alone. Extend with CHAT_PROFANITY_EXTRA.
STARTER_PROFANITY = (
    'fuck', 'shit', 'bullshit', 'bitch', 'bastard', 'asshole', 'motherfucker',
    'dickhead', 'cunt', 'wanker', 'twat', 'prick',
)
_SUFFIXES = ('', 's', 'es', 'ed', 'er', 'ers', 'ing', 'in', 'y', 'ty')

# Threat and harassment phrases blocked by default. Short ones match as whole words.
STARTER_BLOCKED = (
    'kill yourself', 'kys', 'go die', 'hope you die', 'hang yourself',
    'i will kill you', 'ill kill you', 'im going to kill you',
    'i will find you', 'ill find you', 'i know where you live',
)

_LEET = str.maketrans({
    '0': 'o', '1': 'i', '3': 'e', '4': 'a', '5': 's', '7': 't',
    '@': 'a', '$': 's', '!': 'i', '+': 't',
})
_TOKEN = re.compile(r"[A-Za-z0-9@$!+']+")
_URL = re.compile(
    r'(https?://|www\.)\S+|\b[a-z0-9-]+\.(com|net|org|io|gg|ly|me|co|us|tv|xyz|info|biz)\b',
    re.IGNORECASE)
_EMAIL = re.compile(r'[\w.+-]+\s*(@|\(at\)|\[at\])\s*[\w-]+(\.|\s*dot\s*)[a-z]{2,}', re.IGNORECASE)
_PHONE = re.compile(r'(?<!\d)(\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\d)')
_LONG_RUN = re.compile(r'(.)\1{4,}')
MAX_SAME_WORD = 5


@dataclass
class Screened:
    action: str          # allow / mask / block
    text: str            # what to store (masked / shortened when action != block)
    reason: str = ''     # shown to the sender when blocked


def _collapse(word):
    """'shiiit' -> 'shit', 'ass' -> 'as' (applied to both sides of a match)."""
    return re.sub(r'(.)\1+', r'\1', word)


def _normalize_token(token):
    return _collapse(token.lower().translate(_LEET).replace("'", ''))


def _squash(text):
    """Lowercase, un-leet, drop everything but letters, collapse repeats."""
    text = text.lower().translate(_LEET)
    return _collapse(re.sub(r'[^a-z]', '', text))


def _spaced_out_words(raw_tokens):
    """'k y s' -> {'kys'}: runs of three or more single letters, joined."""
    joined, run = set(), []
    for token in list(raw_tokens) + ['']:
        if len(token) == 1 and token.isalnum():
            run.append(token)
            continue
        if len(run) >= 3:
            joined.add(_normalize_token(''.join(run)))
        run = []
    return joined


def _profanity_set(extra=()):
    words = set()
    for base in tuple(STARTER_PROFANITY) + tuple(extra or ()):
        base = _normalize_token(str(base))
        if not base:
            continue
        for suffix in _SUFFIXES:
            words.add(_collapse(base + suffix))
    return words


def _mask_word(token):
    return token[0] + '*' * (len(token) - 1) if len(token) > 1 else '*'


def screen_text(text, extra_profanity=(), blocked_terms=(), allow_links=False):
    """Screen one chat line. See the module docstring for the rules."""
    text = text or ''

    # --- hard blocks -----------------------------------------------------
    if _EMAIL.search(text) or _PHONE.search(text):
        return Screened(BLOCK, text, "Don't share phone numbers or email addresses in chat.")
    if not allow_links and _URL.search(text):
        return Screened(BLOCK, text, 'Links are not allowed in chat.')

    raw_tokens = _TOKEN.findall(text)
    tokens = {_normalize_token(t) for t in raw_tokens}
    tokens |= _spaced_out_words(raw_tokens)
    squashed = _squash(text)
    for term in tuple(STARTER_BLOCKED) + tuple(blocked_terms or ()):
        term_squashed = _squash(str(term))
        if not term_squashed:
            continue
        if len(term_squashed) >= 5:
            hit = term_squashed in squashed
        else:
            hit = term_squashed in tokens
        if hit:
            return Screened(BLOCK, text, 'That message breaks the chat rules.')

    # --- word spam ---------------------------------------------------------
    counts = {}
    for token in _TOKEN.findall(text.lower()):
        counts[token] = counts.get(token, 0) + 1
        if counts[token] > MAX_SAME_WORD and len(token) > 1:
            return Screened(BLOCK, text, "Please don't spam the same word.")

    # --- soft fixes ------------------------------------------------------
    cleaned = _LONG_RUN.sub(lambda m: m.group(1) * 3, text)
    profanity = _profanity_set(extra_profanity)
    masked = False

    def replace(match):
        nonlocal masked
        token = match.group(0)
        if _normalize_token(token) in profanity:
            masked = True
            return _mask_word(token)
        return token

    cleaned = _TOKEN.sub(replace, cleaned)
    return Screened(MASK if masked else ALLOW, cleaned)
