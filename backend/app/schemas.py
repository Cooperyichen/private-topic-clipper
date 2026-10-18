from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


def _to_camel(name: str) -> str:
    first, *rest = name.split("_")
    return first + "".join(part.capitalize() for part in rest)


class CaptureCreate(BaseModel):
    model_config = ConfigDict(alias_generator=lambda name: _to_camel(name), populate_by_name=True)

    kind: Literal["TEXT", "RICH_TEXT", "CODE", "FORMULA", "LINK", "VIDEO"]
    raw_text: str | None = Field(default=None, max_length=2_000_000)
    note: str | None = Field(default=None, max_length=100_000)
    source_url: HttpUrl | None = None
    source_title: str | None = Field(default=None, max_length=1_000)
    video_start_seconds: float | None = Field(default=None, ge=0)
    video_end_seconds: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_content(self) -> CaptureCreate:
        if self.kind in {"TEXT", "RICH_TEXT", "CODE", "FORMULA"} and not self.raw_text:
            raise ValueError("rawText is required for textual captures")
        if self.kind in {"LINK", "VIDEO"} and self.source_url is None:
            raise ValueError("sourceUrl is required for link captures")
        if (
            self.video_start_seconds is not None
            and self.video_end_seconds is not None
            and self.video_end_seconds < self.video_start_seconds
        ):
            raise ValueError("videoEndSeconds must not precede videoStartSeconds")
        return self
