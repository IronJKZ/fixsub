from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from fixsub.errors import MissingDependencyError
from fixsub.models import SyncResult

LOW_QUALITY_MARKERS = ("low-quality alignment", "leaving subtitles unmodified")


def _metric(output: str, label: str) -> float | None:
    match = re.search(rf"{re.escape(label)}:\s*([-+]?\d+(?:\.\d+)?)", output, re.IGNORECASE)
    return float(match.group(1)) if match else None


def _is_low_quality(diagnostics: str) -> bool:
    lowered = diagnostics.lower()
    return any(marker in lowered for marker in LOW_QUALITY_MARKERS)


def synced_output_path(candidate_path: Path, synced_dir: Path) -> Path:
    return synced_dir / f"{candidate_path.stem}.synced{candidate_path.suffix}"


def run_ffsubsync(video_path: Path, subtitle_path: Path, output_path: Path, audio_stream: str) -> SyncResult:
    if not shutil.which("ffs"):
        raise MissingDependencyError("ffs", "python3 -m pip install ffsubsync")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    conservative_command = [
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
    commands = [conservative_command]
    forced_low_quality = False

    for command in commands:
        output_path.unlink(missing_ok=True)
        try:
            result = subprocess.run(command, capture_output=True, text=True)
        except OSError as exc:
            return SyncResult(
                attempted=True,
                succeeded=False,
                output_path=None,
                error=str(exc),
                forced_low_quality=forced_low_quality,
            )
        diagnostics = "\n".join(part for part in [result.stdout, result.stderr] if part)
        metrics = {
            "ffsubsync_score": _metric(diagnostics, "score"),
            "offset_seconds": _metric(diagnostics, "offset seconds"),
            "framerate_scale": _metric(diagnostics, "framerate scale factor"),
        }
        if not forced_low_quality and result.returncode == 0 and _is_low_quality(diagnostics):
            output_path.unlink(missing_ok=True)
            forced_low_quality = True
            commands.append([part for part in conservative_command if part != "--skip-sync-on-low-quality"])
            continue
        if result.returncode != 0:
            output_path.unlink(missing_ok=True)
            return SyncResult(
                attempted=True,
                succeeded=False,
                output_path=None,
                error=result.stderr.strip() or result.stdout.strip(),
                forced_low_quality=forced_low_quality,
                **metrics,
            )
        if not output_path.exists():
            return SyncResult(
                attempted=True,
                succeeded=False,
                output_path=None,
                error="ffsubsync exited successfully without writing an output file",
                forced_low_quality=forced_low_quality,
                **metrics,
            )
        if any(value is None for value in metrics.values()):
            output_path.unlink(missing_ok=True)
            return SyncResult(
                attempted=True,
                succeeded=False,
                output_path=None,
                error="ffsubsync output did not include complete alignment metrics",
                forced_low_quality=forced_low_quality,
                **metrics,
            )
        return SyncResult(
            attempted=True,
            succeeded=True,
            output_path=output_path,
            error=None,
            forced_low_quality=forced_low_quality,
            **metrics,
        )

    raise AssertionError("ffsubsync command loop completed without a result")
