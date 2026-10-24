from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path, PurePath

from .errors import ApiError

MEDIA_SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "application/pdf": (b"%PDF-",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/webp": (b"RIFF",),
}

EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


@dataclass(frozen=True, slots=True)
class StoredAsset:
    original_name: str
    media_type: str
    byte_size: int
    checksum_sha256: str
    relative_path: str


def safe_filename(value: str | None, media_type: str) -> str:
    candidate = (value or f"upload{EXTENSIONS.get(media_type, '')}").replace("\\", "/")
    candidate = PurePath(candidate).name
    candidate = re.sub(r"[^\w.() -]", "_", candidate, flags=re.UNICODE).strip(". ")
    return candidate[:240] or f"upload{EXTENSIONS.get(media_type, '')}"


def validate_media(data: bytes, media_type: str) -> None:
    signatures = MEDIA_SIGNATURES.get(media_type)
    valid = signatures is not None and any(data.startswith(signature) for signature in signatures)
    if media_type == "image/webp" and valid:
        valid = len(data) >= 12 and data[8:12] == b"WEBP"
    if not valid:
        raise ApiError(415, "UNSUPPORTED_MEDIA", "File content does not match a supported type")


def require_supported_media_type(media_type: str) -> str:
    if media_type not in MEDIA_SIGNATURES:
        raise ApiError(415, "UNSUPPORTED_MEDIA", "The stored asset type is not supported")
    return media_type


def store_asset(
    assets_dir: Path,
    data: bytes,
    original_name: str,
    media_type: str,
) -> StoredAsset:
    validate_media(data, media_type)
    checksum = hashlib.sha256(data).hexdigest()
    relative = Path(checksum[:2]) / f"{checksum}{EXTENSIONS[media_type]}"
    target = assets_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(data)
        temporary.replace(target)
    return StoredAsset(
        original_name=safe_filename(original_name, media_type),
        media_type=media_type,
        byte_size=len(data),
        checksum_sha256=checksum,
        relative_path=relative.as_posix(),
    )


def resolve_asset_path(assets_dir: Path, relative_path: str) -> Path:
    root = assets_dir.resolve()
    candidate = (root / relative_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ApiError(
            400,
            "INVALID_ASSET_PATH",
            "The stored asset path is outside the configured asset directory",
        ) from error
    if candidate == root:
        raise ApiError(400, "INVALID_ASSET_PATH", "The stored asset path is invalid")
    return candidate
