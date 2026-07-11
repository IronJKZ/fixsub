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


def test_client_download_falls_back_to_assrt_detail_page_on_api_404(tmp_path: Path) -> None:
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        if str(request.url).startswith("https://api.assrt.test/v1/sub/download"):
            return httpx.Response(404, request=request)
        if str(request.url) == "https://secure.assrt.net/xml/sub/156/156894.xml":
            return httpx.Response(
                200,
                text=(
                    '<a id="btn_download" '
                    'href="/download/156894/%E5%A6%AE%E5%84%BF%E7%9A%84%E8%8A%B3%E5%BF%83.Nell.1994.rar">'
                    "download</a>"
                ),
                request=request,
            )
        if (
            str(request.url)
            == "https://secure.assrt.net/download/156894/%E5%A6%AE%E5%84%BF%E7%9A%84%E8%8A%B3%E5%BF%83.Nell.1994.rar"
        ):
            return httpx.Response(200, content=b"Rar!\x1a\x07\x00archive", request=request)
        return httpx.Response(500, request=request)

    client = AssrtClient(
        token="secret-token",
        base_url="https://api.assrt.test/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True),
    )

    downloaded = client.download(
        result=SearchResult(provider="assrt", result_id="156894", title="Nell 1994", format=None),
        target_dir=tmp_path,
    )

    assert downloaded.path.name == "assrt_156894.rar"
    assert downloaded.path.read_bytes().startswith(b"Rar!")
    assert (
        downloaded.source_url
        == "https://secure.assrt.net/download/156894/%E5%A6%AE%E5%84%BF%E7%9A%84%E8%8A%B3%E5%BF%83.Nell.1994.rar"
    )
    assert requests[1] == "https://secure.assrt.net/xml/sub/156/156894.xml"


def test_client_default_http_client_ignores_environment_proxy() -> None:
    client = AssrtClient(token="secret-token")

    try:
        assert client.http_client._trust_env is False
    finally:
        client.http_client.close()


def test_client_download_follows_assrt_file_host_redirect(tmp_path: Path) -> None:
    requests: list[str] = []
    https_download_url = "https://secure.assrt.net/download/156894/Nell.1994.rar"
    file_download_url = "https://file0.assrt.net/download/156894/Nell.1994.rar?token=temporary"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requests.append(url)
        if url.startswith("https://api.assrt.test/v1/sub/download"):
            return httpx.Response(404, request=request)
        if url == "https://secure.assrt.net/xml/sub/156/156894.xml":
            return httpx.Response(
                200,
                text='<a id="btn_download" href="/download/156894/Nell.1994.rar">archive</a>',
                request=request,
            )
        if url == https_download_url:
            return httpx.Response(302, headers={"Location": file_download_url}, request=request)
        if url == file_download_url:
            return httpx.Response(200, content=b"Rar!\x1a\x07\x00archive", request=request)
        return httpx.Response(500, request=request)

    client = AssrtClient(
        token="secret-token",
        base_url="https://api.assrt.test/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True),
    )

    downloaded = client.download(
        result=SearchResult(provider="assrt", result_id="156894", title="Nell 1994", format=None),
        target_dir=tmp_path,
    )

    assert downloaded.path.name == "assrt_156894.rar"
    assert downloaded.path.read_bytes().startswith(b"Rar!")
    assert downloaded.source_url == https_download_url
    assert requests[-2:] == [https_download_url, file_download_url]


def test_client_download_tries_archive_after_single_file_download_fails(tmp_path: Path) -> None:
    requests: list[str] = []
    https_single_url = "https://secure.assrt.net/download/156894/-/2/Nell.1994.chs.srt"
    https_archive_url = "https://secure.assrt.net/download/156894/Nell.1994.rar"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requests.append(url)
        if url.startswith("https://api.assrt.test/v1/sub/download"):
            return httpx.Response(404, request=request)
        if url == "https://secure.assrt.net/xml/sub/156/156894.xml":
            return httpx.Response(
                200,
                text=(
                    '<div onclick=\'onthefly("156894","2","Nell.1994.chs.srt")\'>chs</div>'
                    '<a id="btn_download" href="/download/156894/Nell.1994.rar">archive</a>'
                ),
                request=request,
            )
        if url == https_single_url:
            return httpx.Response(502, request=request)
        if url == https_archive_url:
            return httpx.Response(200, content=b"Rar!\x1a\x07\x00archive", request=request)
        return httpx.Response(500, request=request)

    client = AssrtClient(
        token="secret-token",
        base_url="https://api.assrt.test/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True),
    )

    downloaded = client.download(
        result=SearchResult(provider="assrt", result_id="156894", title="Nell 1994", format=None),
        target_dir=tmp_path,
    )

    assert downloaded.path.name == "assrt_156894.rar"
    assert downloaded.source_url == https_archive_url
    assert requests[-2:] == [https_single_url, https_archive_url]


def test_client_download_tries_archive_after_single_file_connect_error(tmp_path: Path) -> None:
    https_single_url = "https://secure.assrt.net/download/156894/-/2/Nell.1994.chs.srt"
    https_archive_url = "https://secure.assrt.net/download/156894/Nell.1994.rar"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://api.assrt.test/v1/sub/download"):
            return httpx.Response(404, request=request)
        if url == "https://secure.assrt.net/xml/sub/156/156894.xml":
            return httpx.Response(
                200,
                text=(
                    '<div onclick=\'onthefly("156894","2","Nell.1994.chs.srt")\'>chs</div>'
                    '<a id="btn_download" href="/download/156894/Nell.1994.rar">archive</a>'
                ),
                request=request,
            )
        if url == https_single_url:
            raise httpx.ConnectError("[SSL: UNEXPECTED_EOF_WHILE_READING]", request=request)
        if url == https_archive_url:
            return httpx.Response(200, content=b"Rar!\x1a\x07\x00archive", request=request)
        return httpx.Response(500, request=request)

    client = AssrtClient(
        token="secret-token",
        base_url="https://api.assrt.test/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True),
    )

    downloaded = client.download(
        result=SearchResult(provider="assrt", result_id="156894", title="Nell 1994", format=None),
        target_dir=tmp_path,
    )

    assert downloaded.path.name == "assrt_156894.rar"
    assert downloaded.source_url == https_archive_url


def test_client_download_tries_archive_after_single_file_returns_html(tmp_path: Path) -> None:
    single_url = "https://secure.assrt.net/download/156894/-/2/Nell.1994.chs.srt"
    archive_url = "https://secure.assrt.net/download/156894/Nell.1994.rar"

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://api.assrt.test/v1/sub/download"):
            return httpx.Response(404, request=request)
        if url == "https://secure.assrt.net/xml/sub/156/156894.xml":
            return httpx.Response(
                200,
                text=(
                    '<div onclick=\'onthefly("156894","2","Nell.1994.chs.srt")\'>chs</div>'
                    '<a id="btn_download" href="/download/156894/Nell.1994.rar">archive</a>'
                ),
                request=request,
            )
        if url == single_url:
            return httpx.Response(200, text="<html>temporary error</html>", request=request)
        if url == archive_url:
            return httpx.Response(200, content=b"Rar!\x1a\x07\x00archive", request=request)
        return httpx.Response(500, request=request)

    client = AssrtClient(
        token="secret-token",
        base_url="https://api.assrt.test/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True),
    )

    downloaded = client.download(
        result=SearchResult(provider="assrt", result_id="156894", title="Nell 1994", format=None),
        target_dir=tmp_path,
    )

    assert downloaded.path.name == "assrt_156894.rar"
    assert downloaded.source_url == archive_url


def test_client_download_prefers_assrt_single_chinese_file_from_detail_page(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://api.assrt.test/v1/sub/download"):
            return httpx.Response(404, request=request)
        if url == "https://secure.assrt.net/xml/sub/156/156894.xml":
            return httpx.Response(
                200,
                text=(
                    '<div onclick=\'onthefly("156894","1","Nell.1994.en.srt")\'>en</div>'
                    '<div onclick=\'onthefly("156894","2","Nell.1994.chs.srt")\'>chs</div>'
                    '<a id="btn_download" href="/download/156894/Nell.1994.rar">archive</a>'
                ),
                request=request,
            )
        if url == "https://secure.assrt.net/download/156894/-/2/Nell.1994.chs.srt":
            return httpx.Response(200, content=b"1\n00:00:01,000 --> 00:00:02,000\nHi\n", request=request)
        return httpx.Response(500, request=request)

    client = AssrtClient(
        token="secret-token",
        base_url="https://api.assrt.test/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True),
    )

    downloaded = client.download(
        result=SearchResult(provider="assrt", result_id="156894", title="Nell 1994", format=None),
        target_dir=tmp_path,
    )

    assert downloaded.path.name == "assrt_156894.srt"
    assert downloaded.source_url == "https://secure.assrt.net/download/156894/-/2/Nell.1994.chs.srt"


def test_client_download_redacts_token_from_source_url(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"subtitle", request=request)

    client = AssrtClient(
        token="secret-token",
        base_url="https://api.assrt.test/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True),
    )

    downloaded = client.download(
        result=SearchResult(provider="assrt", result_id="1001", title="movie.srt", format="srt"),
        target_dir=tmp_path,
    )

    assert "secret-token" not in (downloaded.source_url or "")
    assert downloaded.source_url == "https://api.assrt.test/v1/sub/download?token=<redacted>&id=1001"


def test_client_download_rejects_external_assrt_web_fallback_links(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith("https://api.assrt.test/v1/sub/download"):
            return httpx.Response(404, request=request)
        if url == "https://secure.assrt.net/xml/sub/156/156894.xml":
            return httpx.Response(
                200,
                text='<a id="btn_download" href="https://evil.test/download/156894/Nell.1994.rar">download</a>',
                request=request,
            )
        return httpx.Response(500, request=request)

    client = AssrtClient(
        token="secret-token",
        base_url="https://api.assrt.test/v1",
        http_client=httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True),
    )

    with pytest.raises(RuntimeError, match="did not expose a download link"):
        client.download(
            result=SearchResult(provider="assrt", result_id="156894", title="Nell 1994", format=None),
            target_dir=tmp_path,
        )
