from __future__ import annotations

import re
from pathlib import Path

from fixsub.errors import NoVideoFoundError
from fixsub.models import MovieInfo

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".m4v", ".avi", ".mov"}
SOURCE_PATTERNS = ["WEB-DL", "WEBRip", "BluRay", "BDRip", "HDTV", "DVDRip"]


def detect_video(directory: Path) -> Path:
    videos = [path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS]
    if not videos:
        raise NoVideoFoundError(f"No supported video file found in {directory}")
    if len(videos) == 1:
        return videos[0]
    return max(videos, key=lambda path: path.stat().st_size)


def parse_movie_info(video_path: Path) -> MovieInfo:
    stem = video_path.stem
    spaced = stem.replace(".", " ").replace("_", " ")
    year_match = re.search(r"\b(19\d{2}|20\d{2})\b", spaced)
    year = year_match.group(1) if year_match else None
    title = None
    if year_match:
        title = spaced[: year_match.start()].strip() or None
    resolution_match = re.search(r"\b(480p|576p|720p|1080p|2160p|4K)\b", spaced, re.IGNORECASE)
    resolution = resolution_match.group(1) if resolution_match else None
    source = next((source for source in SOURCE_PATTERNS if re.search(source, stem, re.IGNORECASE)), None)
    release_group = None
    if "-" in stem:
        release_group = stem.rsplit("-", 1)[-1] or None
    return MovieInfo(
        path=video_path,
        stem=stem,
        title=title,
        year=year,
        source=source,
        resolution=resolution,
        release_group=release_group,
    )


def generate_search_queries(info: MovieInfo) -> list[str]:
    queries = [info.stem]
    if info.title and info.year and info.source:
        queries.append(f"{info.title} {info.year} {info.source}")
    if info.title and info.year:
        queries.append(f"{info.title} {info.year}")
    deduped: list[str] = []
    for query in queries:
        if query not in deduped:
            deduped.append(query)
    return deduped
