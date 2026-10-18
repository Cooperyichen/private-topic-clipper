from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import ApiError


@dataclass(frozen=True, slots=True)
class RenderedExport:
    markdown: str
    manifest: str
    markdown_path: Path
    manifest_path: Path


def slugify(value: str) -> str:
    slug = re.sub(r"[^\w-]+", "-", value.casefold(), flags=re.UNICODE).strip("-")
    return slug[:80] or "topic"


def checksum_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def render_export(
    vault_dir: Path,
    topic: dict[str, Any],
    items: list[dict[str, Any]],
    exported_at: str,
) -> RenderedExport:
    root = (vault_dir / "Clippings").resolve()
    markdown_path = safe_child(root, f"{topic['export_basename']}.md")
    manifest_path = safe_child(root, f"{topic['export_basename']}.manifest.json")
    lines = [
        "---",
        "schema_version: 1",
        f"topic_id: {json.dumps(topic['id'], ensure_ascii=False)}",
        f"title: {json.dumps(topic['title'], ensure_ascii=False)}",
        f"exported_at: {json.dumps(exported_at)}",
        f"clip_count: {len(items)}",
        "---",
        "",
        f"# {topic['title']}",
        "",
    ]
    if topic.get("description"):
        lines.extend([topic["description"], ""])

    manifest_clips: list[dict[str, Any]] = []
    manifest_assets: list[dict[str, Any]] = []
    for index, item in enumerate(items, start=1):
        clip = item["clip"]
        lines.extend([f"## Clip {index}", ""])
        if item.get("annotation"):
            lines.extend([f"> {item['annotation']}", ""])
        content = select_content(clip, item["representation"])
        if clip["kind"] == "CODE":
            lines.extend(["```", content, "```", ""])
        elif clip["kind"] == "FORMULA":
            lines.extend(["$$", content, "$$", ""])
        elif content:
            lines.extend([content, ""])
        for asset in clip.get("assets", []):
            relative = f"assets/{Path(asset['relativePath']).name}"
            if asset["mediaType"].startswith("image/"):
                lines.extend([f"![[{relative}]]", ""])
            else:
                lines.extend([f"[{asset['originalName']}]({relative})", ""])
            manifest_assets.append(
                {
                    "clipId": clip["id"],
                    "path": relative,
                    "checksumSha256": asset["checksumSha256"],
                    "mediaType": asset["mediaType"],
                }
            )
        if clip.get("sourceUrl"):
            title = clip.get("sourceTitle") or clip["sourceUrl"]
            lines.extend([f"Source: [{title}]({clip['sourceUrl']})", ""])
        manifest_clips.append(
            {
                "id": clip["id"],
                "kind": clip["kind"],
                "position": index - 1,
                "representation": item["representation"],
                "annotation": item.get("annotation"),
                "sourceUrl": clip.get("sourceUrl"),
                "sourceTitle": clip.get("sourceTitle"),
                "minerUVersion": clip.get("minerUVersion"),
            }
        )

    markdown = "\n".join(lines).rstrip() + "\n"
    manifest_data = {
        "schemaVersion": 1,
        "topicId": topic["id"],
        "title": topic["title"],
        "exportedAt": exported_at,
        "clips": manifest_clips,
        "assets": manifest_assets,
    }
    manifest = json.dumps(manifest_data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    return RenderedExport(markdown, manifest, markdown_path, manifest_path)


def copy_export_assets(data_assets_dir: Path, vault_dir: Path, items: list[dict[str, Any]]) -> None:
    destination_root = (vault_dir / "Clippings" / "assets").resolve()
    destination_root.mkdir(parents=True, exist_ok=True)
    source_root = data_assets_dir.resolve()
    for item in items:
        for asset in item["clip"].get("assets", []):
            source = safe_child(source_root, asset["relativePath"])
            destination = safe_child(destination_root, Path(asset["relativePath"]).name)
            if not source.is_file():
                raise ApiError(500, "ASSET_MISSING", "An exported asset is missing")
            if destination.exists() and file_checksum(destination) == asset["checksumSha256"]:
                continue
            temporary = destination.with_suffix(destination.suffix + ".tmp")
            shutil.copyfile(source, temporary)
            os.replace(temporary, destination)


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    os.replace(temporary, path)


def file_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_child(root: Path, relative: str | Path) -> Path:
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise ApiError(400, "UNSAFE_PATH", "Path leaves its permitted directory")
    return target


def select_content(clip: dict[str, Any], representation: str) -> str:
    if representation == "ORIGINAL":
        return clip.get("rawText") or ""
    if representation == "OCR":
        return clip.get("ocrMarkdown") or clip.get("editableText") or ""
    return clip.get("editableText") or ""
