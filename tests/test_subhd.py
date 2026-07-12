from pathlib import Path

import httpx
import pytest

from fixsub.errors import FixsubError
from fixsub.providers.subhd import SubhdClient, parse_search_response


SEARCH_HTML = """
<div class="bg-white shadow-sm rounded-3 mb-4">
  <div class="float-start f16 fw-bold">
    <a class="link-dark align-middle" href="/a/kAqdvK" target="_blank">大地的女儿</a>
  </div>
  <div class="view-text text-secondary">
    <a href="/a/kAqdvK" class="link-dark">Nell.1994.1080p.BluRay.x265-RARBG</a>
  </div>
  <div class="text-truncate py-2 f11">
    <span class="p-1 fw-bold">双语</span>
    <span class="p-1 fw-bold">繁体</span>
    <span class="p-1 fw-bold">英语</span>
    <span class="p-1 text-secondary">SRT</span>
  </div>
</div>
"""


def test_parse_search_response_extracts_subhd_results() -> None:
    results = parse_search_response(SEARCH_HTML, "https://subhd.tv/search/Nell%201994")

    assert len(results) == 1
    assert results[0].provider == "subhd"
    assert results[0].result_id == "kAqdvK"
    assert results[0].title == "大地的女儿 Nell.1994.1080p.BluRay.x265-RARBG"
    assert results[0].detail_url == "https://subhd.tv/a/kAqdvK"
    assert results[0].download_url == "https://subhd.tv/down/kAqdvK"
    assert results[0].language == "bilingual"
    assert results[0].format == "srt"
    assert results[0].raw["version"] == "Nell.1994.1080p.BluRay.x265-RARBG"


def test_subhd_client_search_uses_encoded_query() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://subhd.tv/search/Nell%201994"
        return httpx.Response(200, text=SEARCH_HTML, request=request)

    client = SubhdClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    results = client.search("Nell 1994")

    assert [result.result_id for result in results] == ["kAqdvK"]


def test_subhd_client_download_uses_session_api_and_saves_archive(tmp_path: Path) -> None:
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, str(request.url)))
        if str(request.url) == "https://subhd.tv/a/kAqdvK":
            return httpx.Response(
                200,
                text="<html>detail</html>",
                headers={"Set-Cookie": "tk_download=ready; Path=/; HttpOnly"},
                request=request,
            )
        if str(request.url) == "https://subhd.tv/down/kAqdvK":
            assert "tk_download=ready" in request.headers.get("Cookie", "")
            assert request.headers["Referer"] == "https://subhd.tv/a/kAqdvK"
            return httpx.Response(200, text="<html>download gate</html>", request=request)
        if str(request.url) == "https://subhd.tv/api/sub/down":
            assert request.method == "POST"
            assert "tk_download=ready" in request.headers.get("Cookie", "")
            assert request.headers["Referer"] == "https://subhd.tv/down/kAqdvK"
            assert request.content == b'{"sid":"kAqdvK"}'
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "msg": "验证通过",
                    "pass": True,
                    "url": "https://dl.subhd.me/subtitles/kAqdvK.zip",
                },
                request=request,
            )
        if str(request.url) == "https://dl.subhd.me/subtitles/kAqdvK.zip":
            return httpx.Response(200, content=b"PK\x03\x04archive", request=request)
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = SubhdClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = parse_search_response(SEARCH_HTML, "https://subhd.tv/search/Nell%201994")[0]

    downloaded = client.download(result, tmp_path)

    assert downloaded.path.name == "subhd_kAqdvK.zip"
    assert downloaded.path.read_bytes() == b"PK\x03\x04archive"
    assert downloaded.source_url == "https://dl.subhd.me/subtitles/kAqdvK.zip"
    assert requests == [
        ("GET", "https://subhd.tv/a/kAqdvK"),
        ("GET", "https://subhd.tv/down/kAqdvK"),
        ("POST", "https://subhd.tv/api/sub/down"),
        ("GET", "https://dl.subhd.me/subtitles/kAqdvK.zip"),
    ]


def test_subhd_client_download_accepts_legacy_direct_archive(tmp_path: Path) -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if str(request.url) == "https://subhd.tv/a/kAqdvK":
            return httpx.Response(200, text="<html>detail</html>", request=request)
        if str(request.url) == "https://subhd.tv/down/kAqdvK":
            return httpx.Response(200, content=b"PK\x03\x04legacy", request=request)
        raise AssertionError(f"Unexpected request: {request.url}")

    client = SubhdClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = parse_search_response(SEARCH_HTML, "https://subhd.tv/search/Nell%201994")[0]

    downloaded = client.download(result, tmp_path)

    assert downloaded.path.read_bytes() == b"PK\x03\x04legacy"
    assert requested_urls == [
        "https://subhd.tv/a/kAqdvK",
        "https://subhd.tv/down/kAqdvK",
    ]


@pytest.mark.parametrize(
    ("final_content", "final_headers"),
    [
        (b"<html>challenge</html>", {"Content-Type": "text/html"}),
        (b"\xef\xbb\xbf<script>challenge()</script>", {}),
    ],
)
def test_subhd_client_download_rejects_html_final_response(
    tmp_path: Path,
    final_content: bytes,
    final_headers: dict[str, str],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/a/kAqdvK":
            return httpx.Response(200, text="<html>detail</html>", request=request)
        if request.url.path == "/down/kAqdvK":
            return httpx.Response(200, text="<html>download gate</html>", request=request)
        if request.url.path == "/api/sub/down":
            return httpx.Response(
                200,
                json={"success": True, "pass": True, "url": "https://dl.subhd.me/result.srt"},
                request=request,
            )
        if str(request.url) == "https://dl.subhd.me/result.srt":
            return httpx.Response(200, content=final_content, headers=final_headers, request=request)
        raise AssertionError(f"Unexpected request: {request.url}")

    client = SubhdClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = parse_search_response(SEARCH_HTML, "https://subhd.tv/search/Nell%201994")[0]

    with pytest.raises(FixsubError, match="SubHD download returned HTML"):
        client.download(result, tmp_path)


def test_subhd_client_download_sniffs_plain_srt_content(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/a/kAqdvK":
            return httpx.Response(200, text="<html>detail</html>", request=request)
        if request.url.path == "/down/kAqdvK":
            return httpx.Response(200, content=b"1\n00:00:01,000 --> 00:00:02,000\nHi\n", request=request)
        raise AssertionError(f"Unexpected request: {request.url}")

    client = SubhdClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = parse_search_response(SEARCH_HTML.replace("SRT", "字幕"), "https://subhd.tv/search/Nell%201994")[0]

    downloaded = client.download(result, tmp_path)

    assert downloaded.path.name == "subhd_kAqdvK.srt"
