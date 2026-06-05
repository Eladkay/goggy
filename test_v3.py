"""Tests for v3 features: i18n/RTL, settings, sanitization, upload sniffing,
paste/fullscreen editor. Run: uv run python test_v3.py"""
import re

import pyotp
from fastapi.testclient import TestClient

from goggy.main import app
from goggy import posts, config, settings, twofa

ok = True


def check(name, cond):
    global ok
    ok = ok and bool(cond)
    print(f"{'PASS' if cond else 'FAIL'}  {name}")


def csrf(c):
    return re.search(r'name="csrf-token" content="([^"]+)"', c.get("/").text).group(1)


# clean slate
for p in config.POSTS_DIR.glob("*.md"):
    p.unlink()
if config.SETTINGS_FILE.exists():
    config.SETTINGS_FILE.unlink()
if config.TWOFA_FILE.exists():
    config.TWOFA_FILE.unlink()
settings._cache = None


def full_login(c, token):
    """Password + mandatory 2FA enrollment -> full admin."""
    c.post("/login", data={"password": "admin", "csrf_token": token}, follow_redirects=False)
    if not twofa.is_enrolled():
        secret = re.search(r'id="totp-secret">([^<]+)<', c.get("/admin/2fa/setup").text).group(1)
        c.post("/admin/2fa/setup", data={"code": pyotp.TOTP(secret).now(), "csrf_token": token})
    else:
        secret = twofa.get_or_create_secret()
        c.post("/login/verify", data={"code": pyotp.TOTP(secret).now(), "csrf_token": token},
               follow_redirects=False)


admin = TestClient(app)
t = csrf(admin)
full_login(admin, t)

# --- Settings: change blog name (Goggy is software, not the blog) ---
r = admin.post("/admin/settings", data={
    "blog_title": "Dovi's Diary", "blog_tagline": "hello",
    "default_lang": "en", "posts_per_page": "2", "footer_text": "© Dovi",
    "csrf_token": t,
}, follow_redirects=False)
check("settings save -> 303", r.status_code == 303)
check("settings.json written", config.SETTINGS_FILE.exists())
check("blog name applied on home", "Dovi&#39;s Diary" in TestClient(app).get("/").text)
check("footer text applied", "© Dovi" in TestClient(app).get("/").text)
check("settings page blocked for anon", TestClient(app).get("/admin/settings").status_code == 401)

# --- posts_per_page from settings (=2) ---
for i in range(3):
    admin.post("/admin/new", data={"title": f"Post {i}", "body": "x", "csrf_token": t},
               follow_redirects=False)
check("pagination uses settings (2/page -> 2 pages)", posts.page(1).total_pages == 2)

# --- i18n + RTL ---
anon = TestClient(app)
he = anon.get("/", headers={"Cookie": f"{config.LANG_COOKIE}=he"}).text
check("hebrew cookie -> dir rtl", 'dir="rtl"' in he and 'lang="he"' in he)
check("hebrew nav translated", "בית" in he)  # 'Home'
en = anon.get("/", headers={"Cookie": f"{config.LANG_COOKIE}=en"}).text
check("english -> dir ltr", 'dir="ltr"' in en and ">Home<" in en)

# default language via settings (no cookie)
settings.update({"default_lang": "he"})
check("default lang he -> anon rtl no cookie", 'dir="rtl"' in TestClient(app).get("/").text)
settings.update({"default_lang": "en"})

# lang switch route sets cookie
lr = anon.get("/lang/he", follow_redirects=False)
check("lang route sets cookie", lr.status_code == 303 and config.LANG_COOKIE in lr.headers.get("set-cookie", ""))
check("lang route rejects unknown -> default", "goggy_lang=en" in anon.get("/lang/zz", follow_redirects=False).headers.get("set-cookie", ""))

# --- HTML sanitization in a real rendered post ---
admin.post("/admin/new", data={
    "title": "XSS Try",
    "body": "Hello\n\n<script>alert(1)</script>\n\n<img src=x onerror=alert(2)>\n\n```python\nx=1\n```",
    "csrf_token": t,
}, follow_redirects=False)
pv = anon.get("/post/xss-try").text
check("script stripped from rendered post", "<script>alert" not in pv)
check("onerror stripped from rendered post", "onerror" not in pv)
check("codehilite still works after sanitize", "codehilite" in pv)

# --- Upload content sniffing ---
real_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
fake_png = b"<svg onload=alert(1)></svg>"  # lies about being a png
up_ok = admin.post("/admin/upload", files={"file": ("a.png", real_png, "image/png")},
                   headers={"X-CSRF-Token": t})
up_bad = admin.post("/admin/upload", files={"file": ("a.png", fake_png, "image/png")},
                    headers={"X-CSRF-Token": t})
check("real png accepted", up_ok.status_code == 200)
check("disguised non-image rejected (sniff)", up_bad.status_code == 400)

# --- Editor: paste + fullscreen present ---
ef = admin.get("/admin/new").text
check("fullscreen toggle in editor", 'id="fullscreen-toggle"' in ef)
check("paste hint shown", "Ctrl/Cmd+V" in ef or "Ctrl" in ef)
js = admin.get("/static/editor.js").text
check("paste handler in editor.js", 'addEventListener("paste"' in js)

# cleanup
for p in config.POSTS_DIR.glob("*.md"):
    p.unlink()
import shutil
shutil.rmtree(config.REVISIONS_DIR, ignore_errors=True)
for p in config.UPLOADS_DIR.glob("*"):
    p.unlink()
if config.SETTINGS_FILE.exists():
    config.SETTINGS_FILE.unlink()
if config.TWOFA_FILE.exists():
    config.TWOFA_FILE.unlink()
settings._cache = None

print("\n" + ("ALL PASS" if ok else "SOME FAILED"))
raise SystemExit(0 if ok else 1)
