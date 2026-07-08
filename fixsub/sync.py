from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from fixsub.errors import MissingDependencyError
from fixsub.models import SyncResult


def synced_output_path(candidate_path: Path, synced_dir: Path) -> Path:
    return synced_dir / f"{candidate_path.stem}.synced{candidate_path.suffix}"


def run_ffsubsync(video_path: Path, subtitle_path: Path, output_path: Path, audio_stream: str) -> SyncResult:
    if not shutil.which("ffs"):
        raise MissingDependencyError("ffs", "python3 -m pip install ffsubsync")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffs",
        str(video_path),
        "--reference-stream",
        audio_stream,
        "--skip-sync-on-low-quality",
        "-i",
        str(subtitle_path),
        "-o",
        str(output_path),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True)
    except OSError as exc:
        return SyncResult(attempted=True, succeeded=False, output_path=None, error=str(exc))
    if result.returncode != 0:
        return SyncResult(
            attempted=True,
            succeeded=False,
            output_path=None,
            error=result.stderr.strip() or result.stdout.strip(),
        )
    return SyncResult(attempted=True, succeeded=True, output_path=output_path, error=None)
