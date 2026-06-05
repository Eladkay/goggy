"""Admin authentication helpers.

Single admin user. Login sets a flag in the signed session cookie (managed by
Starlette's SessionMiddleware). Routes that mutate posts depend on ``require_admin``.
"""

from __future__ import annotations

import secrets

from fastapi import Depends, HTTPException, Request, status

SESSION_KEY = "is_admin"
PENDING_KEY = "pending_2fa"
CSRF_KEY = "csrf"


def is_admin(request: Request) -> bool:
    return bool(request.session.get(SESSION_KEY))


def login(request: Request) -> None:
    """Grant full admin (password + second factor both satisfied)."""
    request.session[SESSION_KEY] = True
    request.session.pop(PENDING_KEY, None)


def logout(request: Request) -> None:
    request.session.pop(SESSION_KEY, None)
    request.session.pop(PENDING_KEY, None)


# --- Pending state: password verified, second factor not yet satisfied -------


def set_pending(request: Request) -> None:
    request.session[PENDING_KEY] = True
    request.session.pop(SESSION_KEY, None)


def is_pending(request: Request) -> bool:
    return bool(request.session.get(PENDING_KEY))


def clear_pending(request: Request) -> None:
    request.session.pop(PENDING_KEY, None)


def require_pending_or_admin(request: Request) -> None:
    """Dependency for the 2FA enrollment/verify routes: reachable either mid-login
    (pending) or when already fully authenticated (to manage 2FA)."""
    if not (is_admin(request) or is_pending(request)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Login required"
        )


def require_admin(request: Request) -> None:
    """FastAPI dependency: 401 unless the session is authenticated."""
    if not is_admin(request):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin login required"
        )


AdminRequired = Depends(require_admin)
PendingOrAdmin = Depends(require_pending_or_admin)


# --- CSRF --------------------------------------------------------------------
# Per-session token. Generated once (writing it to the session triggers the
# Set-Cookie that makes it round-trip, even pre-login). Validated on every POST
# from either the `csrf_token` form field or the `X-CSRF-Token` header (for
# fetch-based endpoints).


def csrf_token(request: Request) -> str:
    token = request.session.get(CSRF_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_KEY] = token
    return token


async def require_csrf(request: Request) -> None:
    expected = request.session.get(CSRF_KEY)
    sent = request.headers.get("x-csrf-token")
    if sent is None:
        form = await request.form()
        sent = form.get("csrf_token")
    if not expected or not sent or not secrets.compare_digest(str(sent), expected):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="CSRF token missing or invalid"
        )


CsrfProtected = Depends(require_csrf)