"""Auto-backups.

A background asyncio task that snapshots the blog to a timestamped zip in
``BACKUPS_DIR`` on a fixed interval, and prunes anything older than ``BACKUP_KEEP``.
The snapshot is a superset of the manual ``/admin/export`` zip: posts, uploads,
revisions, ``settings.json`` and ``twofa.json``.

Disabling: set ``backup_interval_hours = 0`` in ``goggy.toml`` (or
``GOGGY_BACKUP_INTERVAL_HOURS=0``).

Security note: the snapshot contains ``twofa.json``, which holds the TOTP secret
and recovery-code hashes. Treat backups as sensitive material — store them with
the same care as the source data directory.
"""

from __future__ import annotations

import asyncio
import logging
import zipfile
from datetime import datetime
from pathlib import Path

from . import config

log = logging.getLogger("goggy.backup")

_TASK: asyncio.Task | None = None


def _gather_files() -> list[tuple[Path, str]]:
    """Yield (source_path, archive_name) pairs to include in a snapshot."""
    items: list[tuple[Path, str]] = []
    for p in config.POSTS_DIR.glob("*.md"):
        items.append((p, f"posts/{p.name}"))
    for p in config.UPLOADS_DIR.iterdir():
        if p.is_file():
            items.append((p, f"uploads/{p.name}"))
    if config.REVISIONS_DIR.exists():
        for p in config.REVISIONS_DIR.rglob("*"):
            if p.is_file():
                rel = p.relative_to(config.REVISIONS_DIR)
                items.append((p, f"revisions/{rel.as_posix()}"))
    for meta in (config.SETTINGS_FILE, config.TWOFA_FILE):
        if meta.exists():
            items.append((meta, meta.name))
    return items


def make_backup() -> Path:
    """Write a fresh snapshot zip into ``BACKUPS_DIR``. Returns the new path."""
    config.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = config.BACKUPS_DIR / f"goggy-backup-{stamp}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for src, name in _gather_files():
            zf.write(src, name)
    return out


def prune_backups(keep: int) -> int:
    """Delete oldest snapshots so at most ``keep`` remain. Returns count removed."""
    if keep <= 0 or not config.BACKUPS_DIR.exists():
        return 0
    snaps = sorted(
        config.BACKUPS_DIR.glob("goggy-backup-*.zip"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    removed = 0
    for old in snaps[keep:]:
        try:
            old.unlink()
            removed += 1
        except OSError as exc:
            log.warning("Could not remove old backup %s: %s", old, exc)
    return removed


async def _loop(interval_hours: float, keep: int) -> None:
    """Sleep first, then snapshot — so importing the app in tests never writes
    a backup file as a side effect of starting the task."""
    delay = interval_hours * 3600
    while True:
        try:
            await asyncio.sleep(delay)
            path = await asyncio.to_thread(make_backup)
            removed = await asyncio.to_thread(prune_backups, keep)
            log.info("Wrote backup %s (pruned %d old)", path.name, removed)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Backup failed; will retry next interval")


def start() -> None:
    """Spawn the scheduler task. No-op if backups are disabled."""
    global _TASK
    if _TASK is not None and not _TASK.done():
        return
    if config.BACKUP_INTERVAL_HOURS <= 0:
        return
    _TASK = asyncio.create_task(
        _loop(config.BACKUP_INTERVAL_HOURS, config.BACKUP_KEEP),
        name="goggy-backup",
    )


async def stop() -> None:
    global _TASK
    if _TASK is None:
        return
    _TASK.cancel()
    try:
        await _TASK
    except asyncio.CancelledError:
        pass
    _TASK = None
