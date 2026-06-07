"""Runtime configuration.

Every value below can be set three ways, in priority order:

  1. an environment variable (``GOGGY_<KEY>``) — highest priority, wins over all
  2. the **global config file** — a TOML file (``goggy.toml`` by default) holding
     the same keys in lowercase; one place to configure a deployment without
     exporting a dozen env vars
  3. a built-in default

This is distinct from ``settings.json``, which holds the handful of settings the
admin edits live in the UI (blog name, tagline, language, …). The global config
file here covers the operational knobs (paths, secrets, limits, 2FA) that were
historically environment variables.

Defaults are safe-ish so the app boots out of the box, but the insecure ones
(admin password, session secret) emit a warning until set.
"""

from __future__ import annotations

import logging
import os
import secrets
import tomllib
from pathlib import Path
from typing import Callable, TypeVar

import bcrypt

log = logging.getLogger("goggy")

# Where the app lives. Data dirs default to siblings of the package's parent.
BASE_DIR = Path(__file__).resolve().parent.parent

# The global config file location is itself bootstrapped from the environment
# (it can't configure its own path).
CONFIG_FILE = Path(os.environ.get("GOGGY_CONFIG", BASE_DIR / "goggy.toml"))
_FILE: dict = {}
if CONFIG_FILE.exists():
    try:
        _FILE = tomllib.loads(CONFIG_FILE.read_text())
    except (tomllib.TOMLDecodeError, OSError) as exc:
        log.warning("Could not read config file %s: %s", CONFIG_FILE, exc)

T = TypeVar("T")


def _cfg(key: str, default: T, cast: Callable[..., T] = str) -> T:
    """Resolve a config value: env var (GOGGY_<KEY>) > config file (key) > default."""
    env_name = "GOGGY_" + key.upper()
    if env_name in os.environ:
        return cast(os.environ[env_name])
    if key in _FILE:
        return cast(_FILE[key])
    return default


def _bool(value) -> bool:
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _path(key: str, default_name: str) -> Path:
    return Path(_cfg(key, BASE_DIR / default_name, Path))


def _data_path(key: str, default_name: str) -> Path:
    p = _path(key, default_name)
    p.mkdir(parents=True, exist_ok=True)
    return p


# --- Blog identity (defaults; admin can override these live in Settings) ------
# "Goggy" is the software, not the blog. The blog gets its own name.
BLOG_TITLE = _cfg("title", "My Blog")
BLOG_TAGLINE = _cfg("tagline", "Thoughts, posts, and ideas.")
FOOTER_TEXT = _cfg("footer", "")

# --- Localization ------------------------------------------------------------
DEFAULT_LANG = _cfg("default_lang", "en")
LANG_COOKIE = "goggy_lang"

# Admin-editable settings (the live UI ones) are persisted here.
SETTINGS_FILE = _path("settings_file", "settings.json")

# --- Two-factor auth ---------------------------------------------------------
# TOTP secret + recovery-code hashes live here (secret in plaintext — required to
# verify codes). Keep this file private; it is gitignored.
TWOFA_FILE = _path("twofa_file", "twofa.json")
TWOFA_ISSUER = _cfg("twofa_issuer", "Goggy")
TWOFA_ACCOUNT = _cfg("twofa_account", "admin")
RECOVERY_CODE_COUNT = 8

# --- Storage -----------------------------------------------------------------
POSTS_DIR = _data_path("posts_dir", "posts")
UPLOADS_DIR = _data_path("uploads_dir", "uploads")
# Prior versions of edited posts. Sibling of POSTS_DIR so post globbing never
# sweeps them up.
REVISIONS_DIR = _data_path("revisions_dir", "revisions")

# --- Auto-backups ------------------------------------------------------------
# Snapshot the data dirs to BACKUPS_DIR every BACKUP_INTERVAL_HOURS, keeping
# BACKUP_KEEP most recent. Set interval to 0 to disable.
BACKUPS_DIR = _path("backups_dir", "backups")
BACKUP_INTERVAL_HOURS = _cfg("backup_interval_hours", 24, float)
BACKUP_KEEP = _cfg("backup_keep", 7, int)

# --- Login rate limiting -----------------------------------------------------
# Throttle failed admin logins per client IP to slow brute force.
LOGIN_MAX_FAILS = _cfg("login_max_fails", 5, int)
LOGIN_LOCKOUT_SECONDS = _cfg("login_lockout_seconds", 300, int)

# --- Pagination --------------------------------------------------------------
POSTS_PER_PAGE = _cfg("posts_per_page", 5, int)

# --- Uploads -----------------------------------------------------------------
MAX_UPLOAD_BYTES = _cfg("max_upload_bytes", 8 * 1024 * 1024, int)
ALLOWED_IMAGE_TYPES = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
}

# --- HTTPS / TLS -------------------------------------------------------------
# Serve TLS directly: point `ssl_certfile` + `ssl_keyfile` at a cert/key pair and
# `goggy run` listens over HTTPS. Behind a TLS-terminating reverse proxy leave
# these blank and instead set `https_only = true` so the session cookie is still
# marked Secure. `https_only` defaults on whenever a cert+key are configured.
SSL_CERTFILE = _cfg("ssl_certfile", "")
SSL_KEYFILE = _cfg("ssl_keyfile", "")
HTTPS_ONLY = _cfg("https_only", bool(SSL_CERTFILE and SSL_KEYFILE), _bool)

# --- Session secret ----------------------------------------------------------
# Must be stable across restarts or every restart logs the admin out.
SECRET_KEY = _cfg("secret_key", "")
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    log.warning(
        "secret_key not set — generated an ephemeral key. Sessions will not "
        "survive a restart. Set secret_key (config file) or GOGGY_SECRET_KEY."
    )

SESSION_COOKIE = "goggy_session"

# --- Admin password ----------------------------------------------------------
# Two ways to supply the password, in priority order:
#   admin_password_hash — a bcrypt hash (preferred; secret never in plaintext)
#   admin_password      — plaintext, hashed once at startup (convenience)
# If neither is set, falls back to "admin" with a loud warning.
_password_hash = _cfg("admin_password_hash", "")
_password_plain = _cfg("admin_password", "")

if _password_hash:
    ADMIN_PASSWORD_HASH = _password_hash.encode()
elif _password_plain:
    ADMIN_PASSWORD_HASH = bcrypt.hashpw(_password_plain.encode(), bcrypt.gensalt())
else:
    ADMIN_PASSWORD_HASH = bcrypt.hashpw(b"admin", bcrypt.gensalt())
    log.warning(
        "No admin password configured — defaulting to 'admin'. Set admin_password "
        "or admin_password_hash (config file) / GOGGY_ADMIN_PASSWORD before going live."
    )


def verify_password(candidate: str) -> bool:
    """Constant-time check of a candidate password against the configured hash."""
    try:
        return bcrypt.checkpw(candidate.encode(), ADMIN_PASSWORD_HASH)
    except ValueError:
        return False
