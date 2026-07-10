from pathlib import Path

import pytest

from fixsub.errors import NoVideoFoundError
from fixsub.movie import detect_video, generate_search_queries, parse_movie_info


def test_detect_video_chooses_only_video(tmp_path: Path) -> None:
    video = tmp_path / "Movie.1992.1080p.WEB-DL.mkv"
    video.write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")

    assert detect_video(tmp_path) == video


def test_detect_video_chooses_largest_when_multiple(tmp_path: Path) -> None:
    small = tmp_path / "sample.mp4"
    large = tmp_path / "Feature.1992.BluRay.mkv"
    small.write_bytes(b"x")
    large.write_bytes(b"x" * 10)

    assert detect_video(tmp_path) == large


def test_detect_video_raises_when_missing(tmp_path: Path) -> None:
    with pytest.raises(NoVideoFoundError):
        detect_video(tmp_path)


def test_parse_movie_info_from_release_name() -> None:
    info = parse_movie_info(Path("Unforgiven.1992.1080p.WEB-DL.ENG.DD5.1.H264-GROUP.mkv"))

    assert info.title == "Unforgiven"
    assert info.year == "1992"
    assert info.resolution == "1080p"
    assert info.source == "WEB-DL"
    assert info.release_group == "GROUP"


def test_parse_movie_info_does_not_treat_source_hyphen_as_release_group() -> None:
    info = parse_movie_info(Path("Movie.1992.1080p.WEB-DL.mkv"))

    assert info.source == "WEB-DL"
    assert info.release_group is None


def test_parse_movie_info_normalizes_web_dl_source_separator() -> None:
    dotted = parse_movie_info(Path("Movie.1992.1080p.WEB.DL.mkv"))
    spaced = parse_movie_info(Path("Movie.1992.1080p.WEB DL.mkv"))

    assert dotted.source == "WEB-DL"
    assert spaced.source == "WEB-DL"


def test_generate_search_queries_prefers_original_stem() -> None:
    info = parse_movie_info(Path("Unforgiven.1992.1080p.WEB-DL.ENG.DD5.1.H264-GROUP.mkv"))

    assert generate_search_queries(info) == [
        "Unforgiven.1992.1080p.WEB-DL.ENG.DD5.1.H264-GROUP",
        "file:Unforgiven.1992.1080p.WEB-DL.ENG.DD5.1.H264-GROUP",
        "Unforgiven 1992 1080p WEB-DL ENG H264-GROUP",
        "Unforgiven 1992 WEB-DL 1080p",
        "Unforgiven 1992 WEB-DL",
        "Unforgiven 1992",
    ]


def test_generate_search_queries_adds_file_and_release_variants() -> None:
    info = parse_movie_info(Path("Nell.1994.WEB-DL.1080p.mkv"))

    assert generate_search_queries(info) == [
        "Nell.1994.WEB-DL.1080p",
        "file:Nell.1994.WEB-DL.1080p",
        "Nell 1994 WEB-DL 1080p",
        "Nell 1994 WEB-DL",
        "Nell 1994",
    ]


def test_generate_search_queries_dedupes_case_insensitively() -> None:
    info = parse_movie_info(Path("Crash.2004.2004.WEB-DL.mkv"))

    queries = generate_search_queries(info)

    assert queries.count("Crash 2004") == 1
    assert len({query.lower() for query in queries}) == len(queries)


def test_generate_search_queries_normalizes_diacritics() -> None:
    info = parse_movie_info(Path("Dom.za.vešanje.1988.1080p.BluRay.mkv"))

    assert "Dom za vesanje 1988 BluRay" in generate_search_queries(info)
