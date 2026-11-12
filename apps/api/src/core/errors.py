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
