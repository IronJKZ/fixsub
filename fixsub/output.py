from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path


def final_subtitle_path(video_path: Path, lang: str, subtitle_suffix: str) -> Path:
    suffix = subtitle_suffix if subtitle_suffix.startswith(".") else f".{subtitle_suffix}"
    return video_path.with_name(f"{video_path.stem}.{lang}{suffix}")


def write_final_subtitle(selected_subtitle: Path, video_path: Path, lang: str, backup_dir: Path) -> Path:
    final_path = final_subtitle_path(video_path, lang, selected_subtitle.suffix)
    if final_path.exists():
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        shutil.copy2(final_path, backup_dir / f"{timestamp}.{final_path.name}")
    shutil.copy2(selected_subtitle, final_path)
    return final_path
