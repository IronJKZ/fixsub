from pathlib import Path

import httpx
import pytest

from fixsub.errors import FixsubError
from fixsub.providers.subhd import SubhdClient, _is_allowed_subhd_url, parse_search_response


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


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://subhd.tv/file.zip", True),
        ("https://dl.subhd.me/file.rar", True),
        ("https://cdn.subhd.one/file.7z", True),
        ("https://subhdtw.com/file.srt", True),
        ("http://dl.subhd.me/file.zip", False),
        ("https://subhd.me:444/file.zip", False),
        ("https://user:pass@subhd.me/file.zip", False),
        ("https://subhd.me.evil.example/file.zip", False),
        ("https://evil.example/file.zip", False),
    ],
)
def test_is_allowed_subhd_url(url: str, expected: bool) -> None:
    assert _is_allowed_subhd_url(url, "https://subhd.tv") is expected


def test_is_allowed_subhd_url_accepts_configured_test_host() -> None:
    assert _is_allowed_subhd_url("https://cdn.subhd.test/file.zip", "https://subhd.test") is True


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


def test_subhd_client_download_rejects_empty_final_response(tmp_path: Path) -> None:
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
            return httpx.Response(200, content=b"", request=request)
        raise AssertionError(f"Unexpected request: {request.url}")

    client = SubhdClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = parse_search_response(SEARCH_HTML, "https://subhd.tv/search/Nell%201994")[0]

    with pytest.raises(FixsubError, match="empty response"):
        client.download(result, tmp_path)


def test_subhd_client_rejects_untrusted_api_url_without_requesting_it(tmp_path: Path) -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.url.path == "/a/kAqdvK":
            return httpx.Response(200, text="<html>detail</html>", request=request)
        if request.url.path == "/down/kAqdvK":
            return httpx.Response(200, text="<html>gate</html>", request=request)
        if request.url.path == "/api/sub/down":
            return httpx.Response(
                200,
                json={"success": True, "pass": True, "url": "https://evil.example/subtitle.zip"},
                request=request,
            )
        raise AssertionError(f"Unsafe URL was requested: {request.url}")

    client = SubhdClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = parse_search_response(SEARCH_HTML, "https://subhd.tv/search/Nell%201994")[0]

    with pytest.raises(FixsubError, match="download URL is not allowed"):
        client.download(result, tmp_path)

    assert "https://evil.example/subtitle.zip" not in requested_urls


def test_subhd_client_rejects_redirect_outside_allowed_domains(tmp_path: Path) -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.url.path == "/a/kAqdvK":
            return httpx.Response(200, text="<html>detail</html>", request=request)
        if request.url.path == "/down/kAqdvK":
            return httpx.Response(200, text="<html>gate</html>", request=request)
        if request.url.path == "/api/sub/down":
            return httpx.Response(
                200,
                json={"success": True, "pass": True, "url": "https://dl.subhd.me/start.zip"},
                request=request,
            )
        if str(request.url) == "https://dl.subhd.me/start.zip":
            return httpx.Response(302, headers={"Location": "https://evil.example/final.zip"}, request=request)
        raise AssertionError(f"Unsafe redirect was requested: {request.url}")

    client = SubhdClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = parse_search_response(SEARCH_HTML, "https://subhd.tv/search/Nell%201994")[0]

    with pytest.raises(FixsubError, match="redirected outside allowed domains"):
        client.download(result, tmp_path)

    assert "https://evil.example/final.zip" not in requested_urls


@pytest.mark.parametrize(
    ("api_response", "error"),
    [
        (httpx.Response(200, text="not json"), "returned invalid JSON"),
        (httpx.Response(200, json=[]), "returned invalid JSON"),
        (
            httpx.Response(200, json={"success": False, "pass": False, "msg": "临时页面已经失效"}),
            "临时页面已经失效",
        ),
        (httpx.Response(200, json={"success": True, "pass": True, "url": None}), "omitted a download URL"),
    ],
)
def test_subhd_client_reports_download_api_errors(
    tmp_path: Path,
    api_response: httpx.Response,
    error: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/a/kAqdvK":
            return httpx.Response(200, text="<html>detail</html>", request=request)
        if request.url.path == "/down/kAqdvK":
            return httpx.Response(200, text="<html>gate</html>", request=request)
        if request.url.path == "/api/sub/down":
            return httpx.Response(
                api_response.status_code,
                content=api_response.content,
                headers=api_response.headers,
                request=request,
            )
        raise AssertionError(f"Unexpected request: {request.url}")

    client = SubhdClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = parse_search_response(SEARCH_HTML, "https://subhd.tv/search/Nell%201994")[0]

    with pytest.raises(FixsubError, match=error):
        client.download(result, tmp_path)


def test_subhd_client_rejects_empty_final_response(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/a/kAqdvK":
            return httpx.Response(200, text="<html>detail</html>", request=request)
        if request.url.path == "/down/kAqdvK":
            return httpx.Response(200, text="<html>gate</html>", request=request)
        if request.url.path == "/api/sub/down":
            return httpx.Response(
                200,
                json={"success": True, "pass": True, "url": "https://dl.subhd.me/empty.zip"},
                request=request,
            )
        if str(request.url) == "https://dl.subhd.me/empty.zip":
            return httpx.Response(200, content=b"", request=request)
        raise AssertionError(f"Unexpected request: {request.url}")

    client = SubhdClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = parse_search_response(SEARCH_HTML, "https://subhd.tv/search/Nell%201994")[0]

    with pytest.raises(FixsubError, match="empty response"):
        client.download(result, tmp_path)


def test_subhd_client_download_api_rejects_invalid_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="not JSON", request=request)

    client = SubhdClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = parse_search_response(SEARCH_HTML, "https://subhd.tv/search/Nell%201994")[0]

    with pytest.raises(FixsubError, match="invalid JSON"):
        client._api_download_url(result, "https://subhd.tv/down/kAqdvK")


def test_subhd_client_download_api_rejects_non_object_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[], request=request)

    client = SubhdClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = parse_search_response(SEARCH_HTML, "https://subhd.tv/search/Nell%201994")[0]

    with pytest.raises(FixsubError, match="invalid JSON"):
        client._api_download_url(result, "https://subhd.tv/down/kAqdvK")


@pytest.mark.parametrize(
    "payload",
    [
        {"success": False, "pass": True, "msg": "验证码失效"},
        {"success": True, "pass": False, "msg": "验证码失效"},
    ],
)
def test_subhd_client_download_api_preserves_rejection_message(payload: dict[str, object]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    client = SubhdClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = parse_search_response(SEARCH_HTML, "https://subhd.tv/search/Nell%201994")[0]

    with pytest.raises(FixsubError, match="验证码失效"):
        client._api_download_url(result, "https://subhd.tv/down/kAqdvK")


@pytest.mark.parametrize(
    "payload",
    [
        {"success": True, "pass": True},
        {"success": True, "pass": True, "url": None},
        {"success": True, "pass": True, "url": ""},
        {"success": True, "pass": True, "url": "  "},
    ],
)
def test_subhd_client_download_api_rejects_omitted_url(payload: dict[str, object]) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload, request=request)

    client = SubhdClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = parse_search_response(SEARCH_HTML, "https://subhd.tv/search/Nell%201994")[0]

    with pytest.raises(FixsubError, match="omitted a download URL"):
        client._api_download_url(result, "https://subhd.tv/down/kAqdvK")


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
