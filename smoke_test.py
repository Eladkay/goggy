"""End-to-end smoke test for Goggy. Run: uv run python smoke_test.py"""
import re
from datetime import datetime, timedelta

import pyotp
from fastapi.testclient import TestClient

from goggy.main import app
from goggy import posts, ratelimit, config, twofa

ok = True


def check(name, cond):
    global ok
    ok = ok and bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {name}")


def csrf(client):
    html = client.get("/").text
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)


# Fresh state
for p in config.POSTS_DIR.glob("*.md"):
    p.unlink()
if config.TWOFA_FILE.exists():
    config.TWOFA_FILE.unlink()

admin = TestClient(app)
t = csrf(admin)

# --- CSRF enforcement ---
check("login without csrf -> 403", admin.post("/login", data={"password": "admin"}).status_code == 403)
check("login bad csrf -> 403", admin.post("/login", data={"password": "admin", "csrf_token": "x"}).status_code == 403)
check("login bad password -> 401", admin.post("/login", data={"password": "no", "csrf_token": t}).status_code == 401)

# --- Mandatory 2FA: password is only the first factor ---
r = admin.post("/login", data={"password": "admin", "csrf_token": t}, follow_redirects=False)
check("password ok -> redirect to 2FA setup", r.status_code == 303 and r.headers["location"] == "/admin/2fa/setup")
check("pending session can't reach admin CRUD", admin.get("/admin/new").status_code == 401)
setup = admin.get("/admin/2fa/setup").text
secret = re.search(r'id="totp-secret">([^<]+)<', setup).group(1)
check("setup shows QR + secret", "<svg" in setup and len(secret) >= 16)
# wrong code rejected
check("enroll wrong code -> 400", admin.post("/admin/2fa/setup", data={"code": "000000", "csrf_token": t}).status_code == 400)
# correct code enrolls and returns recovery codes
en = admin.post("/admin/2fa/setup", data={"code": pyotp.TOTP(secret).now(), "csrf_token": t})
check("enroll correct code -> recovery codes shown", en.status_code == 200 and "recovery" in en.text.lower())
recovery_codes = re.findall(r"<li><code>([0-9a-f]{10})</code></li>", en.text)
check("8 recovery codes generated", len(recovery_codes) == 8)
check("now full admin", admin.get("/admin/new").status_code == 200)

# --- Create posts: public, draft, scheduled, tagged ---
def create(title, body, **extra):
    data = {"title": title, "body": body, "csrf_token": t}
    data.update(extra)
    return admin.post("/admin/new", data=data, follow_redirects=False)

create("Public One", "alpha content here", tags="news, tech")
create("Hidden Draft", "secret beta", tags="news", draft="true")
future = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")
create("Future Sched", "gamma later", tags="tech", publish_at=future)

# --- LEAK CHECK as anonymous (the security spine) ---
anon = TestClient(app)
home = anon.get("/").text
check("anon home shows public", "Public One" in home)
check("anon home hides draft", "Hidden Draft" not in home)
check("anon home hides scheduled", "Future Sched" not in home)
sm = anon.get("/sitemap.xml").text
check("sitemap has public", "public-one" in sm)
check("sitemap hides draft", "hidden-draft" not in sm)
check("sitemap hides scheduled", "future-sched" not in sm)
srch = anon.get("/search", params={"q": "secret"}).text
check("anon search can't find draft body", "Hidden Draft" not in srch)
check("anon search finds public", "alpha" in anon.get("/search", params={"q": "alpha"}).text)
tagpg = anon.get("/tag/news").text
check("anon tag/news hides draft", "Hidden Draft" not in tagpg)
check("anon tag/news shows public", "Public One" in tagpg)
check("anon direct draft url -> 404", anon.get("/post/hidden-draft").status_code == 404)
check("anon direct scheduled url -> 404", anon.get("/post/future-sched").status_code == 404)
check("robots.txt ok", "Sitemap:" in anon.get("/robots.txt").text)

# --- Admin DOES see hidden ---
check("admin home shows draft", "Hidden Draft" in admin.get("/").text)
check("admin sees draft post", admin.get("/post/hidden-draft").status_code == 200)

# --- Reader features ---
pv = anon.get("/post/public-one").text
check("post shows reading time", "min read" in pv)
check("post shows tag link", '/tag/news' in pv)

# --- Editor render (both branches) + fields ---
check("new form renders", "New post" in admin.get("/admin/new").text)
ef = admin.get("/admin/edit/public-one").text
check("edit form renders w/ values", 'value="Public One"' in ef and "news, tech" in ef)

# --- Syntax highlight + TOC ---
html, toc = posts.render_markdown("# Head\n\n## Sub\n\n```python\nx=1\n```")
check("codehilite class present", "codehilite" in html)
check("toc generated", "<li" in toc)

# --- Preview / upload with CSRF header ---
check("preview no csrf -> 403", admin.post("/admin/preview", data={"body": "x"}).status_code == 403)
check("preview with csrf ok", admin.post("/admin/preview", data={"body": "**b**"}, headers={"X-CSRF-Token": t}).text.strip() == "<p><strong>b</strong></p>")
png = b"\x89PNG\r\n\x1a\n" + b"0" * 20
up = admin.post("/admin/upload", files={"file": ("x.png", png, "image/png")}, headers={"X-CSRF-Token": t})
check("upload ok", up.status_code == 200 and up.json()["url"].startswith("/uploads/"))

# --- Revisions ---
admin.post("/admin/edit/public-one", data={"title": "Public One", "body": "EDITED body", "tags": "news,tech", "csrf_token": t}, follow_redirects=False)
revs = posts.list_revisions("public-one")
check("revision saved on edit", len(revs) == 1)
check("current body edited", posts.get("public-one").body == "EDITED body")
rl = admin.get("/admin/revisions/public-one").text
check("revisions page renders", revs[0] in rl)
admin.post(f"/admin/revisions/public-one/{revs[0]}/restore", data={"csrf_token": t}, follow_redirects=False)
check("restore brings back original", posts.get("public-one").body == "alpha content here")
check("restore snapshots current", len(posts.list_revisions("public-one")) == 2)

# --- Export ---
ex = admin.get("/admin/export")
check("export is zip", ex.status_code == 200 and ex.content[:2] == b"PK")
check("export blocked for anon", anon.get("/admin/export").status_code == 401)

# --- Delete (CSRF) ---
check("delete no csrf -> 403", admin.post("/admin/delete/public-one").status_code == 403)
admin.post("/admin/delete/public-one", data={"csrf_token": t}, follow_redirects=False)
check("post deleted", posts.get("public-one") is None)

# --- 2FA verify path on a fresh login (now enrolled) ---
c2 = TestClient(app)
t2 = csrf(c2)
r = c2.post("/login", data={"password": "admin", "csrf_token": t2}, follow_redirects=False)
check("enrolled login -> verify step", r.status_code == 303 and r.headers["location"] == "/login/verify")
check("verify form renders", c2.get("/login/verify").status_code == 200)
check("verify wrong code -> 401", c2.post("/login/verify", data={"code": "000000", "csrf_token": t2}).status_code == 401)
check("pending can't reach admin", c2.get("/admin/new").status_code == 401)
r = c2.post("/login/verify", data={"code": pyotp.TOTP(secret).now(), "csrf_token": t2}, follow_redirects=False)
check("verify correct TOTP -> full admin", r.status_code == 303 and c2.get("/admin/new").status_code == 200)

# recovery code: single-use
c3 = TestClient(app); t3 = csrf(c3)
c3.post("/login", data={"password": "admin", "csrf_token": t3}, follow_redirects=False)
rc_code = recovery_codes[0]
check("recovery code logs in", c3.post("/login/verify", data={"recovery": rc_code, "csrf_token": t3}, follow_redirects=False).status_code == 303)
c4 = TestClient(app); t4 = csrf(c4)
c4.post("/login", data={"password": "admin", "csrf_token": t4}, follow_redirects=False)
check("used recovery code rejected (single-use)", c4.post("/login/verify", data={"recovery": rc_code, "csrf_token": t4}).status_code == 401)

# --- Rate limit ---
ratelimit._fails.clear()
rc = TestClient(app)
tt = csrf(rc)
for _ in range(config.LOGIN_MAX_FAILS):
    rc.post("/login", data={"password": "wrong", "csrf_token": tt})
locked = rc.post("/login", data={"password": "wrong", "csrf_token": tt})
check("locked out after max fails -> 429", locked.status_code == 429)
ratelimit._fails.clear()

# --- Logout ---
check("logout no csrf -> 403", admin.post("/logout").status_code == 403)
check("logout ok", admin.post("/logout", data={"csrf_token": t}, follow_redirects=False).status_code == 303)
check("admin gone after logout", admin.get("/admin/new").status_code == 401)

# Cleanup
for p in config.POSTS_DIR.glob("*.md"):
    p.unlink()
import shutil
shutil.rmtree(config.REVISIONS_DIR, ignore_errors=True)
for p in config.UPLOADS_DIR.glob("*"):
    p.unlink()
if config.TWOFA_FILE.exists():
    config.TWOFA_FILE.unlink()

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
raise SystemExit(0 if ok else 1)
