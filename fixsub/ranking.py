from __future__ import annotations

import re
import unicodedata
from dataclasses import replace

from fixsub.models import CandidateDecision, MovieInfo, SearchResult

RAW_HAYSTACK_FIELDS = ("videoname", "version", "movie_title", "filename", "native_name")


def _contains(text: str, value: str | None) -> bool:
    if not value:
        return False
    normalized_text = _normalize_match_text(text)
    normalized_value = _normalize_match_text(value)
    if not normalized_value:
        return False
    if normalized_value.isascii():
        pattern = rf"(?<![a-z0-9]){re.escape(normalized_value)}(?![a-z0-9])"
        return bool(re.search(pattern, normalized_text))
    return normalized_value in normalized_text


def _normalize_match_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    alphanumeric = "".join(character if character.isalnum() else " " for character in normalized)
    return " ".join(alphanumeric.split())


def _raw_haystack(result: SearchResult) -> str:
    parts = []
    for field in RAW_HAYSTACK_FIELDS:
        value = result.raw.get(field)
        if value:
            parts.append(str(value))
    return " ".join(parts)


def _years(text: str) -> set[str]:
    return set(re.findall(r"\b(19\d{2}|20\d{2})\b", text))


def score_search_result(result: SearchResult, movie: MovieInfo) -> SearchResult:
    haystack = " ".join([result.title, _raw_haystack(result)]).lower()
    score = 0.0
    if result.language in {"bilingual", "zh-Hans", "zh-Hant", "zh"}:
        score += 30
    if result.language == "bilingual":
        score += 5
    if _contains(haystack, movie.title):
        score += 15
    if _contains(haystack, movie.year):
        score += 12
    if _contains(haystack, movie.source):
        score += 8
    if _contains(haystack, movie.resolution):
        score += 4
    if _contains(haystack, movie.release_group):
        score += 6
    if result.format in {"ass", "ssa"}:
        score += 4
    elif result.format == "srt":
        score += 2
    if re.search(r"\bS\d{1,2}E\d{1,2}\b", haystack, re.IGNORECASE):
        score -= 20
    years = _years(haystack)
    if movie.year and years and movie.year not in years:
        score -= 12
    elif movie.year and any(year != movie.year for year in years):
        score -= 12
    return replace(result, pre_score=score)


def rank_search_results(results: list[SearchResult], movie: MovieInfo) -> list[SearchResult]:
    return sorted((score_search_result(result, movie) for result in results), key=lambda item: item.pre_score, reverse=True)


def rank_decisions(decisions: list[CandidateDecision]) -> list[CandidateDecision]:
    return sorted(
        decisions,
        key=lambda decision: (
            not decision.is_poor,
            decision.selected_score,
            decision.candidate.pre_score,
            1 if decision.candidate.format in {"ass", "ssa"} else 0,
        ),
        reverse=True,
    )
