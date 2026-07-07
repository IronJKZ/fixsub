from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from posixpath import normpath
from zipfile import ZipFile

from fixsub.errors import MissingDependencyError

SUBTITLE_EXTENSIONS = {".ass", ".ssa", ".srt"}
ARCHIVE_EXTENSIONS = {".zip", ".rar", ".7z"}


def collect_subtitle_files(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in SUBTITLE_EXTENSIONS
    )


def _collision_safe_path(path: Path) -> Path:
    if not path.exists():
        return path
    counter = 1
    while True:
        candidate = path.with_name(f"{path.stem}.{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def _safe_zip_destination(output_dir: Path, member_name: str) -> Path | None:
    normalized = normpath(member_name)
    if normalized.startswith("../") or normalized == ".." or normalized.startswith("/"):
        return None
    destination = (output_dir / normalized).resolve()
    output_root = output_dir.resolve()
    if output_root != destination and output_root not in destination.parents:
        return None
    return destination


def _extract_zip(archive_path: Path, output_dir: Path) -> list[Path]:
    extracted_subtitles: list[Path] = []
    with ZipFile(archive_path) as zip_file:
        for member in zip_file.infolist():
            if member.is_dir():
                continue
            destination = _safe_zip_destination(output_dir, member.filename)
            if destination is None:
                continue
            destination = _collision_safe_path(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with zip_file.open(member) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)
            if destination.suffix.lower() in SUBTITLE_EXTENSIONS:
                extracted_subtitles.append(destination)
    return sorted(extracted_subtitles)


def extract_archive(archive_path: Path, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = archive_path.suffix.lower()
    if suffix not in ARCHIVE_EXTENSIONS:
        if archive_path.suffix.lower() in SUBTITLE_EXTENSIONS:
            target = _collision_safe_path(output_dir / archive_path.name)
            shutil.copy2(archive_path, target)
            return [target]
        return []
    if suffix == ".zip":
        return _extract_zip(archive_path, output_dir)
    before = set(collect_subtitle_files(output_dir))
    if suffix == ".7z":
        tool = shutil.which("unar")
    else:
        tool = shutil.which("unar") or shutil.which("unrar")
    if not tool:
        raise MissingDependencyError("unar", "brew install unar")
    if Path(tool).name == "unar":
        command = [tool, "-o", str(output_dir), str(archive_path)]
    else:
        command = [tool, "x", str(archive_path), str(output_dir)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    return sorted(path for path in collect_subtitle_files(output_dir) if path not in before)
