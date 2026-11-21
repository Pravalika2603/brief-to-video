"""Asset storage behind a tiny interface. Local by default; GCS if installed/configured."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Protocol


class Storage(Protocol):
    def upload(self, local_path: Path, name: str) -> str: ...


class LocalStorage:
    def __init__(self, root: Path):
        self.root = Path(root)

    def upload(self, local_path: Path, name: str) -> str:
        dest = self.root / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        if Path(local_path).resolve() != dest.resolve():
            shutil.copy2(local_path, dest)
        return str(dest)


class GCSStorage:
    """Requires: pip install -r requirements-gcs.txt and Application Default Credentials."""

    def __init__(self, bucket: str):
        from google.cloud import storage  # imported lazily so the core stays dependency-light
        self.bucket = storage.Client().bucket(bucket)

    def upload(self, local_path: Path, name: str) -> str:
        blob = self.bucket.blob(name)
        blob.upload_from_filename(str(local_path))
        return f"gs://{self.bucket.name}/{name}"
