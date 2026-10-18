from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str
    data_dir: Path
    vault_dir: Path
    allowed_login: str
    max_upload_bytes: int = 100 * 1024 * 1024

    @property
    def database_path(self) -> Path:
        return self.data_dir / "clipper.sqlite3"

    @property
    def assets_dir(self) -> Path:
        return self.data_dir / "assets"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    data_dir = Path(os.getenv("CLIPPER_DATA_DIR", "./var")).expanduser().resolve()
    vault_dir = Path(os.getenv("CLIPPER_VAULT_DIR", "../../vault")).expanduser().resolve()
    return Settings(
        environment=os.getenv("CLIPPER_ENV", "production"),
        data_dir=data_dir,
        vault_dir=vault_dir,
        allowed_login=os.getenv("CLIPPER_ALLOWED_LOGIN", "").strip().casefold(),
        max_upload_bytes=int(os.getenv("CLIPPER_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024))),
    )
