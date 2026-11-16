"""Keeps secrets in URLs out of uvicorn's access log.

A provider sends the browser back to `/api/v1/oauth/callback?code=…&state=…`: the code can be
exchanged for a token (with the verifier) and the state names a sign-in in progress. uvicorn's
access log would print both, so its lines for these paths show `?<redacted>` instead of the query.
`create_app` installs this, so `pnpm dev`, `start` and any other server get it.
"""

import logging

# Paths whose query string never reaches a log line.
REDACTED_QUERY_PATHS = ("/api/v1/oauth/callback",)
ACCESS_LOGGER = "uvicorn.access"


class RedactOAuthCallback(logging.Filter):
    """uvicorn logs each request as `'%s - "%s %s HTTP/%s" %d'` with (client, method, path with
    query, http version, status). This rewrites the path; every other line passes unchanged."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) == 5 and isinstance(args[2], str):
            path, has_query, _ = args[2].partition("?")
            if has_query and path in REDACTED_QUERY_PATHS:
                record.args = (*args[:2], f"{path}?<redacted>", *args[3:])
        return True


def redact_access_log() -> None:
    """Add the filter to uvicorn's access logger, once."""
    logger = logging.getLogger(ACCESS_LOGGER)
    if not any(isinstance(existing, RedactOAuthCallback) for existing in logger.filters):
        logger.addFilter(RedactOAuthCallback())
