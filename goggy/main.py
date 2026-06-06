"""Goggy FastAPI application: reader routes, admin routes, auth, uploads."""

from __future__ import annotations

import io
import zipfile
from datetime import datetime
from pathlib import Path

import segno

from fastapi import FastAPI, Form, Request, UploadFile, status
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    PlainTextResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from . import auth, config, i18n, posts, ratelimit, settings, twofa, uploads

_PKG_DIR = Path(__file__).resolve().parent

app = FastAPI(title=config.BLOG_TITLE)
app.add_middleware(
    SessionMiddleware,
    secret_key=config.SECRET_KEY,
    session_cookie=config.SESSION_COOKIE,
    same_site="lax",  # CSRF mitigation for state-changing admin forms
    https_only=config.HTTPS_ONLY,  # Secure cookie when serving TLS
)

app.mount("/static", StaticFiles(directory=_PKG_DIR / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=config.UPLOADS_DIR), name="uploads")

templates = Jinja2Templates(directory=str(_PKG_DIR / "templates"))


def _lang(request: Request) -> str:
    """Active UI language: reader's cookie choice, else the admin's site default."""
    cookie = request.cookies.get(config.LANG_COOKIE)
    return i18n.normalize(cookie or settings.get("default_lang"))


def _ctx(request: Request, **extra) -> dict:
    """Common template context: request, blog identity, locale, admin, CSRF."""
    lang = _lang(request)
    return {
        "request": request,
        "blog_title": settings.get("blog_title"),
        "blog_tagline": settings.get("blog_tagline"),
        "footer_text": settings.get("footer_text"),
        "lang": lang,
        "dir": i18n.direction(lang),
        "languages": i18n.LANGUAGES,
        "t": lambda key, **kw: i18n.translate(lang, key, **kw),
        "is_admin": auth.is_admin(request),
        "csrf_token": auth.csrf_token(request),
        "all_tags": posts.all_tags(include_hidden=auth.is_admin(request)),
        **extra,
    }


def _parse_tags(raw: str) -> list[str]:
    return [t.strip() for t in raw.split(",") if t.strip()]


def _parse_publish_at(raw: str) -> datetime | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _not_found(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "404.html", _ctx(request), status_code=status.HTTP_404_NOT_FOUND
    )


# --- Reader routes -----------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
def index(request: Request, page: int = 1):
    admin = auth.is_admin(request)
    pg = posts.page(page, include_hidden=admin)
    return templates.TemplateResponse(request, "index.html", _ctx(request, pg=pg))


@app.get("/post/{slug}", response_class=HTMLResponse)
def view_post(request: Request, slug: str):
    admin = auth.is_admin(request)
    post = posts.get(slug)
    if post is None or (not post.is_visible() and not admin):
        return _not_found(request)
    newer, older = posts.neighbors(slug, include_hidden=admin)
    return templates.TemplateResponse(
        request, "post.html", _ctx(request, post=post, newer=newer, older=older)
    )


@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = ""):
    results = posts.search(q, include_hidden=auth.is_admin(request))
    return templates.TemplateResponse(
        request, "search.html", _ctx(request, q=q, results=results)
    )


@app.get("/tag/{tag}", response_class=HTMLResponse)
def tag(request: Request, tag: str):
    results = posts.by_tag(tag, include_hidden=auth.is_admin(request))
    return templates.TemplateResponse(
        request, "tag.html", _ctx(request, tag=tag, results=results)
    )


@app.get("/sitemap.xml")
def sitemap(request: Request):
    base = str(request.base_url).rstrip("/")
    urls = [f"{base}/"]
    for p in posts.all_posts(include_hidden=False):  # never leak drafts to crawlers
        urls.append(f"{base}/post/{p.slug}")
    body = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"{body}</urlset>"
    )
    return Response(content=xml, media_type="application/xml")


@app.get("/robots.txt")
def robots(request: Request):
    base = str(request.base_url).rstrip("/")
    return PlainTextResponse(
        f"User-agent: *\nDisallow: /admin\nDisallow: /login\nSitemap: {base}/sitemap.xml\n"
    )


@app.get("/lang/{code}")
def set_language(request: Request, code: str):
    """Reader-facing language switch. Stores the choice in a cookie and returns
    to wherever they were. Falls back to the default for unknown codes."""
    code = i18n.normalize(code)
    target = request.headers.get("referer") or "/"
    resp = RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
    resp.set_cookie(
        config.LANG_COOKIE, code, max_age=60 * 60 * 24 * 365, samesite="lax", httponly=False
    )
    return resp


# --- Auth routes -------------------------------------------------------------


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if auth.is_admin(request):
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request, "login.html", _ctx(request, error=None))


@app.post("/login", response_class=HTMLResponse, dependencies=[auth.CsrfProtected])
def login_submit(request: Request, password: str = Form(...)):
    if ratelimit.is_locked(request):
        return templates.TemplateResponse(
            request,
            "login.html",
            _ctx(request, error="too_many_attempts"),
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    if config.verify_password(password):
        ratelimit.clear(request)
        # Password is only the first factor. 2FA is mandatory: hold the session
        # in a pending state and route to enrollment or verification.
        auth.set_pending(request)
        target = "/login/verify" if twofa.is_enrolled() else "/admin/2fa/setup"
        return RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
    ratelimit.record_failure(request)
    return templates.TemplateResponse(
        request,
        "login.html",
        _ctx(request, error="incorrect_password"),
        status_code=status.HTTP_401_UNAUTHORIZED,
    )


@app.get("/login/verify", response_class=HTMLResponse)
def verify_form(request: Request):
    if auth.is_admin(request):
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    if not auth.is_pending(request) or not twofa.is_enrolled():
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request, "twofa_verify.html", _ctx(request, error=None)
    )


@app.post("/login/verify", response_class=HTMLResponse, dependencies=[auth.CsrfProtected])
def verify_submit(request: Request, code: str = Form(""), recovery: str = Form("")):
    if not auth.is_pending(request):
        return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
    if (code and twofa.verify_totp(code)) or (recovery and twofa.verify_recovery(recovery)):
        auth.login(request)
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(
        request,
        "twofa_verify.html",
        _ctx(request, error="invalid_code"),
        status_code=status.HTTP_401_UNAUTHORIZED,
    )


@app.post("/logout", dependencies=[auth.CsrfProtected])
def logout(request: Request):
    auth.logout(request)
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


# --- Two-factor enrollment / management --------------------------------------


def _qr_svg(uri: str) -> str:
    buf = io.BytesIO()
    segno.make(uri, error="m").save(buf, kind="svg", scale=4, border=2)
    return buf.getvalue().decode()


@app.get("/admin/2fa/setup", response_class=HTMLResponse, dependencies=[auth.PendingOrAdmin])
def twofa_setup_form(request: Request):
    if twofa.is_enrolled():
        # Already on: only a fully-authenticated admin may manage it.
        if not auth.is_admin(request):
            return RedirectResponse("/login/verify", status_code=status.HTTP_303_SEE_OTHER)
        return templates.TemplateResponse(
            request,
            "twofa_manage.html",
            _ctx(request, remaining=twofa.recovery_remaining()),
        )
    secret = twofa.get_or_create_secret()
    return templates.TemplateResponse(
        request,
        "twofa_setup.html",
        _ctx(request, secret=secret, qr_svg=_qr_svg(twofa.provisioning_uri(secret)), error=None),
    )


@app.post("/admin/2fa/setup", response_class=HTMLResponse, dependencies=[auth.PendingOrAdmin, auth.CsrfProtected])
def twofa_setup_submit(request: Request, code: str = Form("")):
    if twofa.is_enrolled():
        return RedirectResponse("/admin/2fa/setup", status_code=status.HTTP_303_SEE_OTHER)
    codes = twofa.enroll(code)
    if codes is None:
        secret = twofa.get_or_create_secret()
        return templates.TemplateResponse(
            request,
            "twofa_setup.html",
            _ctx(request, secret=secret, qr_svg=_qr_svg(twofa.provisioning_uri(secret)),
                 error="invalid_code"),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    auth.login(request)  # enrollment confirmed -> full admin
    return templates.TemplateResponse(
        request, "twofa_codes.html", _ctx(request, codes=codes)
    )


@app.post("/admin/2fa/recovery", response_class=HTMLResponse, dependencies=[auth.AdminRequired, auth.CsrfProtected])
def twofa_regenerate(request: Request):
    codes = twofa.regenerate_recovery()
    return templates.TemplateResponse(
        request, "twofa_codes.html", _ctx(request, codes=codes)
    )


# --- Admin routes (post CRUD) ------------------------------------------------


@app.get("/admin/new", response_class=HTMLResponse, dependencies=[auth.AdminRequired])
def new_post_form(request: Request):
    return templates.TemplateResponse(
        request, "edit.html", _ctx(request, post=None, action="/admin/new")
    )


@app.post("/admin/new", dependencies=[auth.AdminRequired, auth.CsrfProtected])
def new_post_submit(
    request: Request,
    title: str = Form(...),
    body: str = Form(""),
    tags: str = Form(""),
    draft: bool = Form(False),
    publish_at: str = Form(""),
):
    post = posts.create(
        title, body, tags=_parse_tags(tags), draft=draft, publish_at=_parse_publish_at(publish_at)
    )
    return RedirectResponse(f"/post/{post.slug}", status_code=status.HTTP_303_SEE_OTHER)


@app.get(
    "/admin/edit/{slug}", response_class=HTMLResponse, dependencies=[auth.AdminRequired]
)
def edit_post_form(request: Request, slug: str):
    post = posts.get(slug)
    if post is None:
        return _not_found(request)
    return templates.TemplateResponse(
        request, "edit.html", _ctx(request, post=post, action=f"/admin/edit/{slug}")
    )


@app.post("/admin/edit/{slug}", dependencies=[auth.AdminRequired, auth.CsrfProtected])
def edit_post_submit(
    request: Request,
    slug: str,
    title: str = Form(...),
    body: str = Form(""),
    tags: str = Form(""),
    draft: bool = Form(False),
    publish_at: str = Form(""),
):
    post = posts.update(
        slug, title, body, tags=_parse_tags(tags), draft=draft,
        publish_at=_parse_publish_at(publish_at),
    )
    if post is None:
        return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(f"/post/{post.slug}", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/admin/delete/{slug}", dependencies=[auth.AdminRequired, auth.CsrfProtected])
def delete_post(request: Request, slug: str):
    posts.delete(slug)
    return RedirectResponse("/", status_code=status.HTTP_303_SEE_OTHER)


# --- Admin helpers: live preview + image upload ------------------------------


@app.post("/admin/preview", dependencies=[auth.AdminRequired, auth.CsrfProtected])
def preview(body: str = Form("")):
    """Server-side render so the preview matches the reader view exactly."""
    return HTMLResponse(posts.render_markdown(body)[0])


@app.post("/admin/upload", dependencies=[auth.AdminRequired, auth.CsrfProtected])
async def upload_image(file: UploadFile):
    url = await uploads.save_image(file)
    return JSONResponse({"url": url})


# --- Admin: revision history -------------------------------------------------


@app.get(
    "/admin/revisions/{slug}", response_class=HTMLResponse, dependencies=[auth.AdminRequired]
)
def revisions_list(request: Request, slug: str):
    post = posts.get(slug)
    if post is None:
        return _not_found(request)
    revs = posts.list_revisions(slug)
    return templates.TemplateResponse(
        request, "revisions.html", _ctx(request, post=post, revs=revs, viewing=None)
    )


@app.get(
    "/admin/revisions/{slug}/{rev_id}",
    response_class=HTMLResponse,
    dependencies=[auth.AdminRequired],
)
def revision_view(request: Request, slug: str, rev_id: str):
    post = posts.get(slug)
    rev = posts.get_revision(slug, rev_id)
    if post is None or rev is None:
        return _not_found(request)
    return templates.TemplateResponse(
        request,
        "revisions.html",
        _ctx(request, post=post, revs=posts.list_revisions(slug), viewing=(rev_id, rev)),
    )


@app.post(
    "/admin/revisions/{slug}/{rev_id}/restore",
    dependencies=[auth.AdminRequired, auth.CsrfProtected],
)
def revision_restore(request: Request, slug: str, rev_id: str):
    posts.restore_revision(slug, rev_id)
    return RedirectResponse(f"/post/{slug}", status_code=status.HTTP_303_SEE_OTHER)


# --- Admin: backup/export ----------------------------------------------------


@app.get("/admin/export", dependencies=[auth.AdminRequired])
def export_zip():
    """Download a zip of all posts (incl. drafts) and uploaded images."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in config.POSTS_DIR.glob("*.md"):
            zf.write(p, f"posts/{p.name}")
        for p in config.UPLOADS_DIR.iterdir():
            if p.is_file():
                zf.write(p, f"uploads/{p.name}")
    buf.seek(0)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="goggy-backup-{stamp}.zip"'},
    )


# --- Admin: site settings ----------------------------------------------------


@app.get("/admin/settings", response_class=HTMLResponse, dependencies=[auth.AdminRequired])
def settings_form(request: Request, saved: bool = False):
    return templates.TemplateResponse(
        request,
        "settings.html",
        _ctx(request, settings=settings.all(), saved=saved),
    )


@app.post("/admin/settings", dependencies=[auth.AdminRequired, auth.CsrfProtected])
def settings_save(
    request: Request,
    blog_title: str = Form(...),
    blog_tagline: str = Form(""),
    default_lang: str = Form("en"),
    posts_per_page: int = Form(5),
    footer_text: str = Form(""),
):
    settings.update(
        {
            "blog_title": blog_title.strip() or settings.get("blog_title"),
            "blog_tagline": blog_tagline.strip(),
            "default_lang": i18n.normalize(default_lang),
            "posts_per_page": posts_per_page,
            "footer_text": footer_text.strip(),
        }
    )
    return RedirectResponse(
        "/admin/settings?saved=1", status_code=status.HTTP_303_SEE_OTHER
    )
