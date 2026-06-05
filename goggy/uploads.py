"""Image upload handling: validate type/size, sniff real bytes, store safely."""

from __future__ import annotations

import secrets

from fastapi import HTTPException, UploadFile, status

from . import config


def _sniff(data: bytes) -> str | None:
    """Return canonical extension if the bytes really are a supported image,
    else None. Don't trust the client-supplied content-type alone."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


async def save_image(file: UploadFile) -> str:
    """Validate and store an uploaded image. Returns the public URL path.

    Both the declared content-type and the actual magic-number signature must
    name a supported image type, and they must agree."""
    declared = config.ALLOWED_IMAGE_TYPES.get(file.content_type or "")
    if declared is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported image type: {file.content_type}",
        )

    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds {config.MAX_UPLOAD_BYTES} bytes",
        )

    sniffed = _sniff(data)
    if sniffed is None or sniffed != declared:
        # Bytes aren't a real supported image, or they contradict the declared
        # content-type (e.g. an HTML/SVG/script payload sent as image/png).
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File contents do not match the declared image type.",
        )

    # Random name — never trust the client filename (path traversal / overwrite).
    name = f"{secrets.token_hex(16)}.{sniffed}"
    (config.UPLOADS_DIR / name).write_bytes(data)
    return f"/uploads/{name}"
