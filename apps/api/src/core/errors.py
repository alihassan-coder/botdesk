"""Errors that services raise. `main.py` turns them into JSON responses: {"detail": message}.

Services stay free of HTTP details: they say *what* went wrong; the status code follows.
"""


class AppError(Exception):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class BadRequest(AppError):
    status_code = 400


class Unauthorized(AppError):
    status_code = 401


class Forbidden(AppError):
    status_code = 403


class NotFound(AppError):
    status_code = 404


class Conflict(AppError):
    status_code = 409


class Unavailable(AppError):
    """Something the API depends on (e.g. the memory store) isn't answering. Try again later."""

    status_code = 503


class TooManyRequests(AppError):
    """A rate limit (core/rate_limit.py). The response carries Retry-After."""

    status_code = 429

    def __init__(self, message: str, *, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
