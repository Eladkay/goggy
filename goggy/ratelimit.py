"""In-memory failed-login rate limiter, keyed by client IP.

Personal-blog scale: a process-local dict is enough. After LOGIN_MAX_FAILS
failures within the window, the IP is locked out for LOGIN_LOCKOUT_SECONDS.
A successful login clears the counter.
"""

from __future__ import annotations

import time

from fastapi import Request

from . import config

# ip -> (fail_count, first_fail_monotonic)
_fails: dict[str, tuple[int, float]] = {}


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def is_locked(request: Request) -> bool:
    rec = _fails.get(_client_ip(request))
    if not rec:
        return False
    count, first = rec
    if count < config.LOGIN_MAX_FAILS:
        return False
    if time.monotonic() - first >= config.LOGIN_LOCKOUT_SECONDS:
        _fails.pop(_client_ip(request), None)  # window expired
        return False
    return True


def record_failure(request: Request) -> None:
    ip = _client_ip(request)
    now = time.monotonic()
    count, first = _fails.get(ip, (0, now))
    if now - first >= config.LOGIN_LOCKOUT_SECONDS:
        count, first = 0, now  # reset stale window
    _fails[ip] = (count + 1, first)


def clear(request: Request) -> None:
    _fails.pop(_client_ip(request), None)
