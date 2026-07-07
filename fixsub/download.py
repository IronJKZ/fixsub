from __future__ import annotations

from pathlib import Path

SUPPORTED_DOWNLOAD_EXTENSIONS = {".zip", ".rar", ".7z", ".srt", ".ass", ".ssa"}


def safe_download_name(candidate_id: str, original_name: str) -> str:
    suffix = Path(original_name).suffix.lower()
    if suffix not in SUPPORTED_DOWNLOAD_EXTENSIONS:
        suffix = ".bin"
    return f"{candidate_id}{suffix}"
