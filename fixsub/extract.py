from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
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


def extract_archive(archive_path: Path, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = archive_path.suffix.lower()
    if suffix not in ARCHIVE_EXTENSIONS:
        if archive_path.suffix.lower() in SUBTITLE_EXTENSIONS:
            target = output_dir / archive_path.name
            shutil.copy2(archive_path, target)
            return [target]
        return []
    if suffix == ".zip":
        with ZipFile(archive_path) as zip_file:
            zip_file.extractall(output_dir)
        return collect_subtitle_files(output_dir)
    tool = shutil.which("unar") or shutil.which("unrar")
    if not tool:
        raise MissingDependencyError("unar", "brew install unar")
    if Path(tool).name == "unar":
        command = [tool, "-o", str(output_dir), str(archive_path)]
    else:
        command = [tool, "x", str(archive_path), str(output_dir)]
    subprocess.run(command, check=True, capture_output=True, text=True)
    return collect_subtitle_files(output_dir)
