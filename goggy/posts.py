"""Flat-file post storage.

Each post is a single Markdown file in POSTS_DIR named ``<slug>.md`` with YAML
front matter:

    ---
    title: My First Post
    slug: my-first-post
    created: 2026-06-05T10:00:00
    updated: 2026-06-05T10:00:00
    publish_at: 2026-06-05T10:00:00
    draft: false
    tags: [intro, meta]
    ---
    Body markdown here...

The filename is the slug, generated once at creation and never changed on edit,
so URLs stay stable.

Reader visibility is computed at request time by a single rule:

    visible = (not draft) and (publish_at <= now)

This covers both drafts (hidden until published) and scheduled posts (hidden
until their publish time passes) without any background job.
"""

from __future__ import annotations

import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from functools import cached_property
from pathlib import Path

import frontmatter
import markdown as md
import nh3

from . import config, settings as _settings

# HTML sanitization whitelist. Markdown is admin-authored, but raw HTML in a
# post (e.g. a pasted <script>) would otherwise execute for every reader — so we
# strip anything not on this list. The allowances below keep Markdown output
# intact: codehilite (class on span/div/pre/code), footnotes + TOC anchors
# (id, href), tables, and images.
_ALLOWED_TAGS = nh3.ALLOWED_TAGS | {
    "h1", "h2", "h3", "h4", "h5", "h6", "pre", "span", "img", "hr",
    "table", "thead", "tbody", "tr", "th", "td", "sup", "sub", "details", "summary",
}
_ALLOWED_ATTRS = {
    "*": {"class", "id", "dir"},
    "a": {"href", "title", "name"},
    "img": {"src", "alt", "title", "width", "height"},
    "td": {"align"},
    "th": {"align"},
    "ol": {"start"},
}


def sanitize_html(html: str) -> str:
    return nh3.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        url_schemes={"http", "https", "mailto", "tel"},
        link_rel="noopener noreferrer nofollow",
    )

_MD_EXTENSIONS = [
    "fenced_code",
    "tables",
    "footnotes",
    "sane_lists",
    "nl2br",
    "toc",
    "codehilite",
]


def _new_md() -> md.Markdown:
    return md.Markdown(
        extensions=_MD_EXTENSIONS,
        extension_configs={"codehilite": {"guess_lang": False}},
        output_format="html",
    )


def render_markdown(text: str) -> tuple[str, str]:
    """Render markdown to (html, table_of_contents_html), both sanitized. Fresh
    instance per call so codehilite/toc state never leaks between renders."""
    m = _new_md()
    html = m.convert(text)
    return sanitize_html(html), sanitize_html(getattr(m, "toc", ""))


_SLUG_STRIP = re.compile(r"[^\w\s-]")
_SLUG_DASH = re.compile(r"[-\s]+")
_WORD = re.compile(r"\w+")


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = _SLUG_STRIP.sub("", value).strip().lower()
    value = _SLUG_DASH.sub("-", value)
    return value or "post"


def _unique_slug(base: str) -> str:
    slug = base
    n = 2
    while _path_for(slug).exists():
        slug = f"{base}-{n}"
        n += 1
    return slug


def _path_for(slug: str) -> Path:
    return config.POSTS_DIR / f"{slug}.md"


@dataclass
class Post:
    slug: str
    title: str
    body: str
    created: datetime
    updated: datetime
    publish_at: datetime
    draft: bool = False
    tags: list[str] = field(default_factory=list)

    def _render(self) -> tuple[str, str]:
        return render_markdown(self.body)

    @cached_property
    def _rendered(self) -> tuple[str, str]:
        return self._render()

    @property
    def html(self) -> str:
        return self._rendered[0]

    @property
    def toc(self) -> str:
        return self._rendered[1]

    @property
    def excerpt_html(self) -> str:
        chunk = self.body.strip().split("\n\n", 1)[0]
        return render_markdown(chunk)[0]

    @property
    def reading_minutes(self) -> int:
        words = len(_WORD.findall(self.body))
        return max(1, round(words / 200))

    @property
    def scheduled(self) -> bool:
        return not self.draft and self.publish_at > datetime.now()

    def is_visible(self, now: datetime | None = None) -> bool:
        now = now or datetime.now()
        return (not self.draft) and self.publish_at <= now


def _dt(value, fallback: datetime | None = None) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return fallback or datetime.min


def _parse(post: frontmatter.Post, slug: str) -> Post:
    created = _dt(post.get("created"))
    tags = post.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    return Post(
        slug=post.get("slug", slug),
        title=post.get("title", slug),
        body=post.content,
        created=created,
        updated=_dt(post.get("updated"), created),
        publish_at=_dt(post.get("publish_at"), created),
        draft=bool(post.get("draft", False)),
        tags=[str(t) for t in tags],
    )


def get(slug: str) -> Post | None:
    path = _path_for(slug)
    if not path.exists():
        return None
    return _parse(frontmatter.load(path), slug)


def all_posts(include_hidden: bool = False) -> list[Post]:
    """Posts newest first. Readers must pass ``include_hidden=False`` (default);
    only admin paths pass True. This is the single visibility chokepoint —
    every reader route funnels through here."""
    posts = []
    now = datetime.now()
    for path in config.POSTS_DIR.glob("*.md"):
        post = _parse(frontmatter.load(path), path.stem)
        if include_hidden or post.is_visible(now):
            posts.append(post)
    posts.sort(key=lambda p: p.publish_at, reverse=True)
    return posts


def search(query: str, include_hidden: bool = False) -> list[Post]:
    q = query.strip().lower()
    if not q:
        return []
    out = []
    for p in all_posts(include_hidden):
        if q in p.title.lower() or q in p.body.lower() or any(q in t.lower() for t in p.tags):
            out.append(p)
    return out


def by_tag(tag: str, include_hidden: bool = False) -> list[Post]:
    tag = tag.lower()
    return [p for p in all_posts(include_hidden) if tag in (t.lower() for t in p.tags)]


def all_tags(include_hidden: bool = False) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for p in all_posts(include_hidden):
        for t in p.tags:
            counts[t] = counts.get(t, 0) + 1
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))


def neighbors(slug: str, include_hidden: bool = False) -> tuple[Post | None, Post | None]:
    """Return (newer, older) adjacent posts from the same visible, sorted list
    the index uses. Newest-first ordering => newer is the previous index."""
    posts = all_posts(include_hidden)
    for i, p in enumerate(posts):
        if p.slug == slug:
            newer = posts[i - 1] if i > 0 else None
            older = posts[i + 1] if i + 1 < len(posts) else None
            return newer, older
    return None, None


@dataclass
class Page:
    posts: list[Post]
    page: int
    total_pages: int

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages


def page(number: int, per_page: int | None = None, include_hidden: bool = False) -> Page:
    per_page = per_page or int(_settings.get("posts_per_page"))
    posts = all_posts(include_hidden)
    total = max(1, (len(posts) + per_page - 1) // per_page)
    number = max(1, min(number, total))
    start = (number - 1) * per_page
    return Page(posts=posts[start : start + per_page], page=number, total_pages=total)


def create(
    title: str,
    body: str,
    tags: list[str] | None = None,
    draft: bool = False,
    publish_at: datetime | None = None,
) -> Post:
    now = datetime.now().replace(microsecond=0)
    slug = _unique_slug(slugify(title))
    post = Post(
        slug=slug,
        title=title.strip() or slug,
        body=body,
        created=now,
        updated=now,
        publish_at=publish_at or now,
        draft=draft,
        tags=tags or [],
    )
    _write(post)
    return post


def update(
    slug: str,
    title: str,
    body: str,
    tags: list[str] | None = None,
    draft: bool | None = None,
    publish_at: datetime | None = None,
) -> Post | None:
    existing = get(slug)
    if existing is None:
        return None
    _save_revision(slug)  # snapshot prior version before overwrite
    existing.title = title.strip() or existing.title
    existing.body = body
    if tags is not None:
        existing.tags = tags
    if draft is not None:
        existing.draft = draft
    if publish_at is not None:
        existing.publish_at = publish_at
    existing.updated = datetime.now().replace(microsecond=0)
    _write(existing)
    return existing


def delete(slug: str) -> bool:
    path = _path_for(slug)
    if not path.exists():
        return False
    path.unlink()
    return True


def _write(post: Post) -> None:
    fm = frontmatter.Post(
        post.body,
        title=post.title,
        slug=post.slug,
        created=post.created.isoformat(),
        updated=post.updated.isoformat(),
        publish_at=post.publish_at.isoformat(),
        draft=post.draft,
        tags=post.tags,
    )
    _path_for(post.slug).write_bytes(frontmatter.dumps(fm).encode())


# --- Revisions ---------------------------------------------------------------


def _rev_dir(slug: str) -> Path:
    d = config.REVISIONS_DIR / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def _save_revision(slug: str) -> None:
    path = _path_for(slug)
    if not path.exists():
        return
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    shutil.copy2(path, _rev_dir(slug) / f"{stamp}.md")


def list_revisions(slug: str) -> list[str]:
    """Revision ids (filenames without .md), newest first."""
    d = config.REVISIONS_DIR / slug
    if not d.exists():
        return []
    return sorted((p.stem for p in d.glob("*.md")), reverse=True)


def get_revision(slug: str, rev_id: str) -> Post | None:
    path = _rev_dir(slug) / f"{rev_id}.md"
    if not path.exists():
        return None
    return _parse(frontmatter.load(path), slug)


def restore_revision(slug: str, rev_id: str) -> Post | None:
    rev = get_revision(slug, rev_id)
    if rev is None:
        return None
    _save_revision(slug)  # snapshot current state so restore is undoable
    rev.updated = datetime.now().replace(microsecond=0)
    _write(rev)
    return rev
