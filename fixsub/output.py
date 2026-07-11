from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

SUBTITLE_SUFFIXES = (".srt", ".ass", ".ssa")


def final_subtitle_path(video_path: Path, lang: str, subtitle_suffix: str) -> Path:
    suffix = subtitle_suffix if subtitle_suffix.startswith(".") else f".{subtitle_suffix}"
    return video_path.with_name(f"{video_path.stem}.{lang}{suffix}")


def compatible_language_tags(lang: str) -> tuple[str, ...]:
    """Include the former default tag when migrating Infuse-compatible Chinese output."""
    return (lang, "zh-Hans") if lang == "zh" else (lang,)


def _backup_path(backup_dir: Path, timestamp: str, final_filename: str) -> Path:
    backup_path = backup_dir / f"{timestamp}.{final_filename}"
    if not backup_path.exists():
        return backup_path
    index = 1
    while True:
        backup_path = backup_dir / f"{timestamp}-{index}.{final_filename}"
        if not backup_path.exists():
            return backup_path
        index += 1


def write_final_subtitle(selected_subtitle: Path, video_path: Path, lang: str, backup_dir: Path) -> Path:
    final_path = final_subtitle_path(video_path, lang, selected_subtitle.suffix)
    existing_paths = []
    for existing_lang in compatible_language_tags(lang):
        existing_paths.extend(
            path
            for suffix in SUBTITLE_SUFFIXES
            if (path := final_subtitle_path(video_path, existing_lang, suffix)).exists()
        )
    if existing_paths:
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        for existing_path in existing_paths:
            shutil.copy2(existing_path, _backup_path(backup_dir, timestamp, existing_path.name))
            if existing_path != final_path:
                existing_path.unlink()
    shutil.copy2(selected_subtitle, final_path)
    return final_path
