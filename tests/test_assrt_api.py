import io
import json
from pathlib import Path
import zipfile

import httpx
import pytest

from fixsub.models import MovieInfo, SearchResult
from fixsub.providers.assrt_api import AssrtClient, parse_search_response
from fixsub.ranking import score_search_result


def test_parse_search_response_extracts_results() -> None:
    payload = json.loads(Path("tests/fixtures/assrt_search.json").read_text(encoding="utf-8"))

    results = parse_search_response(payload)

    assert [result.result_id for result in results] == ["1001", "1002"]
    assert results[0].title == "Unforgiven 1992 WEB-DL bilingual.ass"
    assert results[0].language == "bilingual"
    assert results[0].format == "ass"
    assert results[0].download_url is not None


def test_parse_search_response_ignores_missing_or_malformed_shapes() -> None:
    assert parse_search_response({"sub": None}) == []

    results = parse_search_response({"sub": {"subs": ["bad", {"id": "3", "native_name": "Ok.zh.srt"}]}})

    assert [result.result_id for result in results] == ["3"]
    assert results[0].title == "Ok.zh.srt"
    assert results[0].format == "srt"


def test_parse_search_response_detects_format_from_tokens_and_extensions() -> None:
    payload = {
        "sub": {
            "subs": [
                {"id": "1", "native_name": "class notes"},
                {"id": "2", "native_name": "srtipped"},
                {"id": "3", "native_name": "movie.ass"},
                {"id": "4", "native_name": "movie.ssa"},
                {"id": "5", "native_name": "movie.srt"},
                {"id": "6", "native_name": "movie", "subtype": "ass"},
                {"id": "7", "native_name": "movie", "subtype": "ssa"},
                {"id": "8", "native_name": "movie", "subtype": "srt"},
            ]
        }
    }

    results = parse_search_response(payload)

    assert [result.format for result in results] == [None, None, "ass", "ssa", "srt", "ass", "ssa", "srt"]


def test_search_result_scoring_prefers_matching_chinese_ass() -> None:
    payload = json.loads(Path("tests/fixtures/assrt_search.json").read_text(encoding="utf-8"))
    info = MovieInfo(
        path=Path("Unforgiven.1992.1080p.WEB-DL-GROUP.mkv"),
        stem="Unforgiven.1992.1080p.WEB-DL-GROUP",
        title="Unforgiven",
        year="1992",
        source="WEB-DL",
        resolution="1080p",
        release_group="GROUP",
    )
    results = parse_search_response(payload)

    scored = [score_search_result(result, info) for result in results]

    assert scored[0].pre_score > scored[1].pre_score


def test_search_result_scoring_penalizes_conflicting_year() -> None:
    info = MovieInfo(
        path=Path("Unforgiven.1992.1080p.WEB-DL-GROUP.mkv"),
        stem="Unforgiven.1992.1080p.WEB-DL-GROUP",
        title="Unforgiven",
        year="1992",
        source="WEB-DL",
        resolution="1080p",
        release_group="GROUP",
    )
    clean = parse_search_response(
        {"sub": {"subs": [{"id": "1", "native_name": "Unforgiven.1992.1080p.WEB-DL-GROUP.ass"}]}}
    )[0]
    conflicting = parse_search_response(
        {"sub": {"subs": [{"id": "2", "native_name": "Unforgiven.1992.2013.1080p.WEB-DL-GROUP.ass"}]}}
    )[0]

    assert score_search_result(conflicting, info).pre_score < score_search_result(clean, info).pre_score


def test_search_result_scoring_handles_non_string_raw_videoname() -> None:
    info = MovieInfo(
        path=Path("Unforgiven.1992.1080p.WEB-DL-GROUP.mkv"),
        stem="Unforgiven.1992.1080p.WEB-DL-GROUP",
        title="Unforgiven",
        year="1992",
        source="WEB-DL",
        resolution="1080p",
        release_group="GROUP",
    )
    result = SearchResult(
        provider="assrt",
        result_id="1",
        title="Unforgiven.1992.ass",
        format="ass",
        raw={"videoname": 123},
    )

    scored = score_search_result(result, info)

    assert isinstance(scored, SearchResult)
    assert isinstance(scored.pre_score, float)


def test_client_requires_token() -> None:
    with pytest.raises(ValueError, match="ASSRT_TOKEN"):
        AssrtClient(token="")


def test_client_search_uses_token_and_query() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "token=secret-token" in str(request.url)
        assert "q=Unforgiven" in str(request.url)
        payload = json.loads(Path("tests/fixtures/assrt_search.json").read_text(encoding="utf-8"))
        return httpx.Response(200, json=payload)

    client = AssrtClient(token="secret-token", http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    results = client.search("Unforgiven")

    assert results[0].result_id == "1001"


def test_client_download_sanitizes_result_id_and_creates_target_dir(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"subtitle")

    target_dir = tmp_path / "nested"
    client = AssrtClient(token="secret-token", http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    downloaded = client.download(
        result=parse_search_response({"sub": {"subs": [{"id": "../../x", "native_name": "movie.srt"}]}})[0],
        target_dir=target_dir,
    )

    assert downloaded.path.parent == target_dir
    assert downloaded.path.name == "assrt_x.srt"
    assert downloaded.path.read_bytes() == b"subtitle"
    assert not (tmp_path / "x.srt").exists()


def test_client_download_uses_archive_suffix_when_content_is_zip(tmp_path: Path) -> None:
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("movie.ass", "[Events]\n")
    archive_bytes = archive_buffer.getvalue()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=archive_bytes)

    client = AssrtClient(token="secret-token", http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    downloaded = client.download(
        result=parse_search_response({"sub": {"subs": [{"id": "1001", "native_name": "movie.ass"}]}})[0],
        target_dir=tmp_path,
    )

    assert downloaded.path.name == "assrt_1001.zip"
    assert not (tmp_path / "assrt_1001.ass").exists()
    assert downloaded.path.read_bytes() == archive_bytes


def test_client_download_infers_subtitle_suffix_from_download_url(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"1\n00:00:01,000 --> 00:00:02,000\nHi\n")

    client = AssrtClient(token="secret-token", http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    downloaded = client.download(
        result=SearchResult(
            provider="assrt",
            result_id="1001",
            title="movie",
            download_url="https://example.test/movie.srt",
            format=None,
        ),
        target_dir=tmp_path,
    )

    assert downloaded.path.name == "assrt_1001.srt"
    assert not (tmp_path / "assrt_1001.bin").exists()


def test_client_download_infers_subtitle_suffix_from_content_disposition(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"[Script Info]\n",
            headers={"Content-Disposition": 'attachment; filename="movie.ass"'},
        )

    client = AssrtClient(token="secret-token", http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    downloaded = client.download(
        result=SearchResult(provider="assrt", result_id="1001", title="movie", format=None),
        target_dir=tmp_path,
    )

    assert downloaded.path.name == "assrt_1001.ass"
    assert not (tmp_path / "assrt_1001.bin").exists()
