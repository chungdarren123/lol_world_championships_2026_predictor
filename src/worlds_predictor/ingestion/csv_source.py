"""CSV validation and provenance, independent of modeling decisions."""

import csv
import hashlib
from datetime import datetime, timezone
from pathlib import Path


class SourceError(ValueError):
    """The supplied file cannot be treated as match data."""


def file_metadata(path: Path, source_url: str | None, retrieved_at: str | None) -> dict:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "file_name": path.name,
        "bytes": path.stat().st_size,
        "sha256": digest.hexdigest(),
        "source_url": source_url,
        "retrieved_at_utc": retrieved_at,
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "availability_caveat": (
            "Match timestamps do not prove data was published before the cutoff. "
            "A later download may contain backfills or corrections."
        ),
    }


def read_csv(path: Path):
    """Yield (header, iterator); caller must consume it inside the context."""
    return CsvSource(path)


class CsvSource:
    def __init__(self, path: Path):
        self.path = path
        self.stream = None

    def __enter__(self):
        self.stream = self.path.open("r", encoding="utf-8-sig", newline="")
        try:
            prefix = self.stream.read(8192)
            if not prefix.strip():
                raise SourceError("Source is empty.")
            if "<html" in prefix.lower() or "<!doctype html" in prefix.lower():
                detail = "Google Drive download quota exceeded" if "quota exceeded" in prefix.lower() else "HTML response"
                raise SourceError(f"{detail}; this file is not a CSV dataset.")
            self.stream.seek(0)
            reader = csv.DictReader(self.stream, strict=True)
            fields = reader.fieldnames or []
            if len(fields) < 2 or len(fields) != len(set(fields)) or any(not f for f in fields):
                raise SourceError("CSV header is absent, duplicated, or invalid.")
            return fields, reader
        except Exception:
            self.stream.close()
            raise

    def __exit__(self, *_):
        self.stream.close()
