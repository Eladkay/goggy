# CLAUDE.md

Guidance for working in this repo. See `README.md` for user-facing docs.

## What this is

**Goggy** — a single-admin Markdown blog. FastAPI + Jinja2 + flat Markdown files
(no database). "Goggy" is the software; the blog's name is configurable.

## Run & test

```bash
uv sync
uv run python main.py            # dev server at http://127.0.0.1:8000
uv run python smoke_test.py      # core: auth/2FA, CSRF, leak check, CRUD, revisions, export
uv run python test_v3.py         # i18n/RTL, settings, sanitization, upload sniffing, editor
```

Run **both** test files after any change; together they cover every route. They
write to the real data dirs and clean up after themselves (including
`settings.json` / `twofa.json`), so reset those if a run aborts mid-way.

## Architecture (package `goggy/`)

| File | Responsibility |
|---|---|
| `config.py` | Static config. Resolves **env var > `goggy.toml` > default** via `_cfg()`. |
| `settings.py` | Admin-editable live settings, persisted to `settings.json`. |
| `posts.py` | Flat-file post CRUD, Markdown render + **sanitize**, search, tags, neighbors, revisions. |
| `auth.py` | Session admin gate, **pending (2FA) state**, CSRF token + check. |
| `twofa.py` | TOTP enroll/verify, recovery codes (`twofa.json`). |
| `uploads.py` | Image upload: size + content-type + **magic-number sniff**. |
| `ratelimit.py` | In-memory failed-login lockout per IP. |
| `i18n.py` | EN/HE UI translations, `translate()`, RTL direction. |
| `main.py` | All routes + request context (`_ctx`). |
| `templates/`, `static/` | Jinja templates (+ `_macros.html`), CSS/JS. |

## Invariants — do not break these

- **Visibility chokepoint.** A post is reader-visible iff `not draft and
  publish_at <= now`. This lives in `posts.all_posts(include_hidden=False)` and
  **every reader path must go through it** (index, search, tags, neighbors,
  sitemap). Admin paths pass `include_hidden=True`. Leaking a draft/scheduled
  post to anonymous users or crawlers is the #1 regression to guard. `smoke_test`
  asserts no leak across home/search/tag/sitemap/direct-URL.
- **CSRF on every state change.** All POST routes carry `auth.CsrfProtected`.
  HTML forms include `<input name="csrf_token">`; fetch (`/admin/preview`,
  `/admin/upload`) sends `X-CSRF-Token`. Adding a POST means adding CSRF + a test.
- **2FA is mandatory.** Password only sets a *pending* session
  (`auth.set_pending`); full admin (`auth.login`) requires a confirmed TOTP code
  or recovery code. `require_admin` only passes for full admin. New admin tests
  must complete the enroll/verify flow (see `full_login` in `test_v3.py`).
- **Rendered Markdown is sanitized** (`posts.sanitize_html`, nh3). The whitelist
  deliberately keeps codehilite `class`, footnote/TOC `id`+`href`, tables, images.
  If you change Markdown extensions, re-verify the whitelist still passes those
  through (test: "codehilite still works after sanitize").
- **Slugs are immutable.** Generated once at create from the title; never
  regenerated on edit (would orphan the file / break URLs).

## Conventions / gotchas

- **Starlette ≥1.2 `TemplateResponse` signature** is `(request, name, context)`,
  not `(name, context)`. All calls use the new form.
- **Jinja macros need context.** Templates using `_macros.html` import it
  `{% import "_macros.html" as m with context %}` so macros can call `t(...)`.
- **i18n:** every user-facing string goes through `t('key')`; add the key to
  *both* `en` and `he` in `i18n.py`. Pass error messages to templates as
  translation keys (e.g. `error="invalid_code"`), not literal text.
- **RTL:** `<html dir>` follows the language; post title/body use `dir="auto"`
  for mixed content; code blocks are forced LTR in CSS.
- **Gitignored runtime files:** `posts/`, `uploads/`, `revisions/`,
  `settings.json`, `twofa.json`, `goggy.toml`. Don't commit these. `goggy.toml`
  may hold secrets — commit `goggy.example.toml` instead.
- **Config:** add new operational knobs via `config._cfg("key", default, cast)`
  and document them in `goggy.example.toml` + the README table. Don't read
  `os.environ` directly elsewhere.

## Pre-commit checklist

1. Both test files print `ALL PASS`.
2. App imports: `uv run python -c "from goggy.main import app"`.
3. New POST route → CSRF dependency + a test.
4. New reader query → routed through the visibility chokepoint.
5. New UI string → present in both `en` and `he`.
