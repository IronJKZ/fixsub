from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from fixsub.errors import NoVideoFoundError
from fixsub.models import MovieInfo

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".m4v", ".avi", ".mov"}
SOURCE_PATTERNS = ["WEB-DL", "WEBRip", "BluRay", "BDRip", "HDTV", "DVDRip"]
SOURCE_ALIASES = [
    ("WEB-DL", re.compile(r"\bWEB[-. ]DL\b", re.IGNORECASE)),
    *[(source, re.compile(source, re.IGNORECASE)) for source in SOURCE_PATTERNS if source != "WEB-DL"],
]
DROP_QUERY_TOKENS = {
    "AAC",
    "AC3",
    "DD5",
    "DDP5",
    "DTS",
    "H264",
    "H265",
    "HEVC",
    "X264",
    "X265",
}


def _unique_preserve_order(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = " ".join(value.strip().split())
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        result.append(normalized)
        seen.add(key)
    return result


def _normalize_search_title(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return "".join(character for character in normalized if not unicodedata.combining(character))


def _space_release_name(stem: str) -> str:
    return " ".join(part for part in re.split(r"[._]+", stem) if part)


def _drop_noisy_tokens(value: str) -> str:
    tokens = []
    for token in value.split():
        clean = re.sub(r"[^A-Za-z0-9-]", "", token).upper()
        if clean in DROP_QUERY_TOKENS:
            continue
        if re.fullmatch(r"\d+(?:\.\d+)?", token) and not re.fullmatch(r"(19|20)\d{2}", token):
            continue
        tokens.append(token)
    return " ".join(tokens)


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
    source = next((source for source, pattern in SOURCE_ALIASES if pattern.search(stem)), None)
    release_group = None
    if "-" in stem:
        release_prefix, release_suffix = stem.rsplit("-", 1)
        prefix_token = re.split(r"[. _]", release_prefix)[-1]
        hyphenated_tail = f"{prefix_token}-{release_suffix}"
        if not any(pattern.fullmatch(hyphenated_tail) for _, pattern in SOURCE_ALIASES):
            release_group = release_suffix or None
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
    queries: list[str] = [info.stem, f"file:{info.stem}"]

    spaced_stem = _drop_noisy_tokens(_space_release_name(info.stem))
    if spaced_stem:
        queries.append(spaced_stem)

    normalized_spaced_stem = _normalize_search_title(spaced_stem)
    if normalized_spaced_stem != spaced_stem:
        queries.append(normalized_spaced_stem)

    title_variants: list[str] = []
    if info.title:
        title_variants.append(info.title)
        normalized_title = _normalize_search_title(info.title)
        if normalized_title != info.title:
            title_variants.append(normalized_title)

    for title in title_variants:
        if info.year and info.source and info.resolution:
            queries.append(f"{title} {info.year} {info.source} {info.resolution}")
        if info.year and info.source:
            queries.append(f"{title} {info.year} {info.source}")
        if info.year:
            queries.append(f"{title} {info.year}")
        else:
            queries.append(title)

    return _unique_preserve_order(queries)
