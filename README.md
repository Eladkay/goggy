# Goggy

A simple, readable single-admin blogging platform. One server = one blog. The
admin writes posts in Markdown; everyone else reads them.

## Features

- Markdown posts, rendered for readers — with code syntax highlighting + auto table-of-contents
- Single admin: log in to create / edit / delete posts
- Live Markdown preview in the editor (server-rendered, matches reader view) + **fullscreen writing mode**
- Image upload + insert — by button **or by pasting (Ctrl/Cmd+V) anywhere in the post**
- **Editable site settings** (blog name, tagline, default language, posts-per-page, footer) — "Goggy" is the software; the blog has its own name
- **Internationalized UI** (English + Hebrew) with full **RTL** support; readers switch language, admin sets the default
- **Drafts** and **scheduled publishing** — both via one request-time rule, no background job
- **Tags** with per-tag pages and a tag cloud
- **Full-text search** over titles, bodies, and tags
- **Prev/next** navigation between posts; reading-time estimate
- **Revision history** — every edit is snapshotted; view and restore prior versions
- **Backup/export** — download a zip of all posts + images
- Dark-mode toggle (no flash on load)
- SEO: slug URLs (`/post/my-first-post`), `sitemap.xml`, `robots.txt`
- Security: bcrypt password, **mandatory TOTP two-factor auth** (with single-use recovery codes), signed `SameSite=Lax` session, per-form CSRF tokens, login rate-limiting, **sanitized rendered HTML (nh3)**, **magic-number upload sniffing**
- Flat-file storage — each post is a `.md` file with YAML front matter

### Visibility rule

A post is shown to readers only when **`not draft and publish_at <= now`**. This
single rule drives the home page, search, tags, prev/next, and `sitemap.xml`, so
drafts and future-scheduled posts never leak to anonymous visitors or crawlers.
The admin sees hidden posts (badged Draft / Scheduled) while logged in.

## Install

Requires Python 3.13+.

```bash
uv sync          # or: pip install -e .
```

## Run

```bash
goggy run                      # http://127.0.0.1:8000
goggy run --host 0.0.0.0 --port 8080 --reload
# or
python main.py
```

For production, point an ASGI server at the app:

```bash
uvicorn goggy.main:app --host 0.0.0.0 --port 8000
```

## Two-factor authentication

2FA is **mandatory**. On first login the admin enters the password, then is taken
to a setup page: scan the QR with an authenticator app (Google Authenticator,
Authy, 1Password…), confirm a 6-digit code, and Goggy shows **8 single-use
recovery codes** (stored only as bcrypt hashes — save them). After that, every
login is password → 6-digit code (or a recovery code). Regenerate recovery codes
anytime from Settings → Two-factor authentication.

2FA state lives in `twofa.json` (gitignored). Lost your authenticator *and*
recovery codes? Delete `twofa.json` to re-enroll on next login.

## Configuration

Two layers:

- **`settings.json`** — the handful of settings the admin edits live in the UI
  (blog name, tagline, default language, posts-per-page, footer).
- **`goggy.toml`** (global config file) — operational knobs: paths, secrets,
  limits, 2FA labels. Copy `goggy.example.toml` to `goggy.toml` and edit. Each
  key can also be overridden by an environment variable `GOGGY_<KEY>` (uppercase),
  which wins over the file. Precedence: **env var > `goggy.toml` > built-in default**.
  Point elsewhere with `GOGGY_CONFIG=/path/to/file.toml`.

### Keys (config-file name → env var)

| Config key | Env var | Default | Purpose |
|---|---|---|---|
| `title` | `GOGGY_TITLE` | `My Blog` | Default blog name (admin can change in Settings) |
| `tagline` | `GOGGY_TAGLINE` | `Thoughts, posts, and ideas.` | Default tagline |
| `default_lang` | `GOGGY_DEFAULT_LANG` | `en` | Default UI language (`en` / `he`) |
| `footer` | `GOGGY_FOOTER` | *(empty)* | Default footer text |
| `secret_key` | `GOGGY_SECRET_KEY` | *(ephemeral)* | Session signing key — **set this**, or restarts log the admin out |
| `admin_password_hash` | `GOGGY_ADMIN_PASSWORD_HASH` | — | bcrypt hash of admin password (preferred) |
| `admin_password` | `GOGGY_ADMIN_PASSWORD` | `admin` | Plaintext admin password (hashed at startup; convenience only) |
| `twofa_issuer` | `GOGGY_TWOFA_ISSUER` | `Goggy` | Label shown in the authenticator app |
| `twofa_account` | `GOGGY_TWOFA_ACCOUNT` | `admin` | Account name in the authenticator app |
| `posts_dir` | `GOGGY_POSTS_DIR` | `./posts` | Where post `.md` files live |
| `uploads_dir` | `GOGGY_UPLOADS_DIR` | `./uploads` | Where uploaded images live |
| `revisions_dir` | `GOGGY_REVISIONS_DIR` | `./revisions` | Where prior post versions are kept |
| `backups_dir` | `GOGGY_BACKUPS_DIR` | `./backups` | Where auto-backup zips are written |
| `backup_interval_hours` | `GOGGY_BACKUP_INTERVAL_HOURS` | `24` | Hours between auto-backups; `0` disables |
| `backup_keep` | `GOGGY_BACKUP_KEEP` | `7` | Most recent snapshots to retain |
| `settings_file` | `GOGGY_SETTINGS_FILE` | `./settings.json` | Where admin-edited settings persist |
| `twofa_file` | `GOGGY_TWOFA_FILE` | `./twofa.json` | Where 2FA secret + recovery hashes persist |
| `posts_per_page` | `GOGGY_POSTS_PER_PAGE` | `5` | Pagination size |
| `max_upload_bytes` | `GOGGY_MAX_UPLOAD_BYTES` | `8388608` | Max image upload size (8 MiB) |
| `login_max_fails` | `GOGGY_LOGIN_MAX_FAILS` | `5` | Failed logins per IP before lockout |
| `login_lockout_seconds` | `GOGGY_LOGIN_LOCKOUT_SECONDS` | `300` | Lockout duration after too many fails |
| `ssl_certfile` | `GOGGY_SSL_CERTFILE` | *(empty)* | TLS certificate path; `goggy run` serves HTTPS when set (with key) |
| `ssl_keyfile` | `GOGGY_SSL_KEYFILE` | *(empty)* | TLS private key path |
| `https_only` | `GOGGY_HTTPS_ONLY` | *(on if cert+key set)* | Mark the session cookie `Secure` (set behind a TLS-terminating proxy) |

The config-file location itself is set only via `GOGGY_CONFIG` (default `./goggy.toml`).

### Setting the admin password

```bash
goggy hash       # prompts, prints an export line for GOGGY_ADMIN_PASSWORD_HASH
export GOGGY_SECRET_KEY="$(python -c 'import secrets;print(secrets.token_hex(32))')"
```

The default password is `admin` — change it before exposing the server.

## How posts are stored

```
posts/my-first-post.md
---
title: My First Post
slug: my-first-post
created: 2026-06-05T10:00:00
updated: 2026-06-05T10:00:00
---
Body markdown here...
```

The filename equals the slug. Slugs are generated once at creation and never
change on edit, so URLs stay stable.

## Tests

A full end-to-end smoke test (auth, CSRF, the draft/scheduled leak check, CRUD,
revisions, export, rate-limiting) lives in `smoke_test.py`:

```bash
uv run python smoke_test.py   # core: auth, CSRF, leak check, CRUD, revisions, export
uv run python test_v3.py      # i18n/RTL, settings, sanitization, upload sniffing, editor
```

## Settings & internationalization

Log in and open **Settings** to change the blog name, tagline, default language,
posts-per-page, and footer — persisted to `settings.json` (these override the
env defaults). The UI ships with English and Hebrew; readers switch language from
the header (remembered in a cookie), and Hebrew renders the whole UI right-to-left.
Post titles and bodies use `dir="auto"`, so mixed Hebrew/English content flows
correctly regardless of the UI language.

## Notes

- Rendered Markdown is sanitized with **nh3**: `<script>`, event handlers, and
  `javascript:` URLs are stripped, while formatting, images, tables, footnotes,
  and code highlighting are preserved.
- Image uploads are checked by **magic number** — the bytes must actually be a
  PNG/JPEG/GIF/WebP and match the declared type; SVG is rejected (same-origin script).
- Session cookie is `SameSite=Lax`; state-changing forms also carry a per-session
  CSRF token (sent as a hidden field, or `X-CSRF-Token` header for fetch calls).
