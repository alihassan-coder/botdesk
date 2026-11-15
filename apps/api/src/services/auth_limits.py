"""Rate limits on the auth routes people could abuse: guessing passwords, mass sign-ups, and
flooding someone's inbox with reset emails.

Keyed by the client's address, and for sign-in and forgot-password also by the email (lowercased),
so neither spreading guesses over many addresses nor over many emails gets around them. Unknown
emails are counted exactly like known ones: a 429 never tells you whether an account exists.
"""

import math

from src.core.errors import TooManyRequests
from src.core.rate_limit import Limit, RateLimiter

MINUTE = 60
HOUR = 60 * MINUTE

SIGN_IN_PER_IP = Limit(hits=10, seconds=MINUTE)
SIGN_IN_PER_EMAIL = Limit(hits=5, seconds=MINUTE)
SIGN_UP_PER_IP = Limit(hits=20, seconds=HOUR)
FORGOT_PASSWORD_PER_IP = Limit(hits=20, seconds=HOUR)
FORGOT_PASSWORD_PER_EMAIL = Limit(hits=5, seconds=HOUR)
RESET_PASSWORD_PER_IP = Limit(hits=20, seconds=HOUR)


def _wait_text(seconds: int) -> str:
    minutes = math.ceil(seconds / MINUTE)
    if minutes < 60:
        return "1 minute" if minutes == 1 else f"{minutes} minutes"
    hours = math.ceil(minutes / 60)
    return "1 hour" if hours == 1 else f"{hours} hours"


def _check(limiter: RateLimiter, *checks: tuple[str, Limit]) -> None:
    wait = limiter.hit(*checks)
    if wait is not None:
        raise TooManyRequests(f"Too many attempts. Try again in {_wait_text(wait)}.", retry_after_seconds=wait)


def sign_in(limiter: RateLimiter, *, ip: str, email: str) -> None:
    _check(limiter, (f"sign-in:ip:{ip}", SIGN_IN_PER_IP), (f"sign-in:email:{email.lower()}", SIGN_IN_PER_EMAIL))


def sign_up(limiter: RateLimiter, *, ip: str) -> None:
    _check(limiter, (f"sign-up:ip:{ip}", SIGN_UP_PER_IP))


def forgot_password(limiter: RateLimiter, *, ip: str, email: str) -> None:
    _check(
        limiter,
        (f"forgot:ip:{ip}", FORGOT_PASSWORD_PER_IP),
        (f"forgot:email:{email.lower()}", FORGOT_PASSWORD_PER_EMAIL),
    )


def reset_password(limiter: RateLimiter, *, ip: str) -> None:
    _check(limiter, (f"reset:ip:{ip}", RESET_PASSWORD_PER_IP))
