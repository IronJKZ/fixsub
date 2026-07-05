from __future__ import annotations

from pathlib import Path

from fixsub.models import WorkDirs


def create_workdirs(base_dir: Path) -> WorkDirs:
    root = base_dir / ".fixsub"
    workdirs = WorkDirs(
        root=root,
        downloads=root / "downloads",
        candidates=root / "candidates",
        synced=root / "synced",
        original=root / "original",
        logs=root / "logs",
        metadata=root / "metadata",
    )
    for directory in (
        workdirs.root,
        workdirs.downloads,
        workdirs.candidates,
        workdirs.synced,
        workdirs.original,
        workdirs.logs,
        workdirs.metadata,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return workdirs
