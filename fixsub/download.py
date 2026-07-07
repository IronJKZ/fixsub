from __future__ import annotations

import re
from pathlib import Path
from pathlib import PureWindowsPath

SUPPORTED_DOWNLOAD_EXTENSIONS = {".zip", ".rar", ".7z", ".srt", ".ass", ".ssa"}


def safe_download_name(candidate_id: str, original_name: str) -> str:
    suffix = Path(original_name).suffix.lower()
    if suffix not in SUPPORTED_DOWNLOAD_EXTENSIONS:
        suffix = ".bin"
    safe_id = Path(PureWindowsPath(candidate_id).name).name
    safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", safe_id).strip("._")
    if not safe_id:
        safe_id = "download"
    return f"{safe_id}{suffix}"
