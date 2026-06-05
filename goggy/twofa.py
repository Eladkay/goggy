"""Two-factor authentication (TOTP) for the single admin.

State persists in a small JSON file (gitignored):

    {"secret": "<base32>", "enrolled": true, "recovery": ["<bcrypt>", ...]}

The TOTP secret is stored in plaintext because verifying codes requires it;
recovery codes are stored only as bcrypt hashes and are single-use.

2FA is mandatory: until ``enrolled`` is true the admin can authenticate with the
password but only to reach enrollment; full access requires a confirmed second
factor.
"""

from __future__ import annotations

import json
import secrets
import threading

import bcrypt
import pyotp

from . import config

_lock = threading.Lock()


def _load() -> dict:
    if config.TWOFA_FILE.exists():
        try:
            return json.loads(config.TWOFA_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"secret": None, "enrolled": False, "recovery": []}


def _save(state: dict) -> None:
    config.TWOFA_FILE.write_text(json.dumps(state, indent=2))


def is_enrolled() -> bool:
    return bool(_load().get("enrolled"))


def get_or_create_secret() -> str:
    """Return the current TOTP secret, generating a provisional one (not yet
    enrolled) on first call. Stable across page reloads so the QR doesn't churn."""
    with _lock:
        state = _load()
        if not state.get("secret"):
            state["secret"] = pyotp.random_base32()
            _save(state)
        return state["secret"]


def provisioning_uri(secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(
        name=config.TWOFA_ACCOUNT, issuer_name=config.TWOFA_ISSUER
    )


def verify_totp(code: str) -> bool:
    state = _load()
    secret = state.get("secret")
    if not secret or not code:
        return False
    # valid_window=1 tolerates ~30s clock skew on either side.
    return pyotp.TOTP(secret).verify(code.strip().replace(" ", ""), valid_window=1)


def _gen_codes() -> list[str]:
    # 10 hex chars, shown grouped; readable and unambiguous.
    return [secrets.token_hex(5) for _ in range(config.RECOVERY_CODE_COUNT)]


def enroll(code: str) -> list[str] | None:
    """Confirm enrollment with a TOTP code from the provisional secret. On
    success, mark enrolled, generate recovery codes, and return them in plaintext
    (shown to the admin exactly once). Returns None if the code is wrong."""
    if not verify_totp(code):
        return None
    with _lock:
        state = _load()
        plain = _gen_codes()
        state["enrolled"] = True
        state["recovery"] = [
            bcrypt.hashpw(c.encode(), bcrypt.gensalt()).decode() for c in plain
        ]
        _save(state)
        return plain


def regenerate_recovery() -> list[str]:
    with _lock:
        state = _load()
        plain = _gen_codes()
        state["recovery"] = [
            bcrypt.hashpw(c.encode(), bcrypt.gensalt()).decode() for c in plain
        ]
        _save(state)
        return plain


def recovery_remaining() -> int:
    return len(_load().get("recovery", []))


def verify_recovery(code: str) -> bool:
    """Check a recovery code; consume it (single-use) on success."""
    code = (code or "").strip().replace(" ", "").replace("-", "").lower()
    if not code:
        return False
    with _lock:
        state = _load()
        hashes = state.get("recovery", [])
        for i, h in enumerate(hashes):
            try:
                if bcrypt.checkpw(code.encode(), h.encode()):
                    hashes.pop(i)
                    state["recovery"] = hashes
                    _save(state)
                    return True
            except ValueError:
                continue
    return False
