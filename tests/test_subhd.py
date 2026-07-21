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


def test_request_allowed_follows_exactly_five_redirects() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        hop = int(request.url.path.rsplit("/", 1)[-1])
        if hop < 5:
            return httpx.Response(302, headers={"Location": f"/hop/{hop + 1}"}, request=request)
        return httpx.Response(200, content=b"done", request=request)

    client = SubhdClient(
        base_url="https://subhd.test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client._request_allowed("GET", "https://subhd.test/hop/0")

    assert response.content == b"done"
    assert requested_paths == [f"/hop/{hop}" for hop in range(6)]


def test_request_allowed_rejects_sixth_redirect() -> None:
    requested_paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_paths.append(request.url.path)
        hop = int(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(302, headers={"Location": f"/hop/{hop + 1}"}, request=request)

    client = SubhdClient(
        base_url="https://subhd.test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(FixsubError, match="exceeded 5 redirects"):
        client._request_allowed("GET", "https://subhd.test/hop/0")

    assert requested_paths == [f"/hop/{hop}" for hop in range(6)]


def test_request_allowed_rejects_redirect_without_location() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, request=request)

    client = SubhdClient(
        base_url="https://subhd.test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(FixsubError, match="redirect omitted Location"):
        client._request_allowed("GET", "https://subhd.test/start")


def test_request_allowed_resolves_relative_redirect_location() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if request.url.path == "/files/start":
            return httpx.Response(302, headers={"Location": "../final.zip"}, request=request)
        return httpx.Response(200, content=b"done", request=request)

    client = SubhdClient(
        base_url="https://subhd.test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client._request_allowed("GET", "https://subhd.test/files/start")

    assert response.content == b"done"
    assert requested_urls == [
        "https://subhd.test/files/start",
        "https://subhd.test/final.zip",
    ]


@pytest.mark.parametrize("status_code", [301, 302, 303])
def test_request_allowed_rewrites_post_redirect_to_bodyless_get(status_code: int) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/start":
            return httpx.Response(status_code, headers={"Location": "/final"}, request=request)
        return httpx.Response(200, content=b"done", request=request)

    client = SubhdClient(
        base_url="https://subhd.test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client._request_allowed(
        "POST",
        "https://subhd.test/start",
        json={"sid": "abc"},
        headers={"Content-Type": "application/json", "Content-Length": "13"},
    )

    assert response.content == b"done"
    assert [(request.method, request.url.path, request.content) for request in requests] == [
        ("POST", "/start", b'{"sid":"abc"}'),
        ("GET", "/final", b""),
    ]
    assert "Content-Type" not in requests[1].headers
    assert "Content-Length" not in requests[1].headers


def test_request_allowed_preserves_put_and_body_on_301_redirect() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/start":
            return httpx.Response(301, headers={"Location": "/final"}, request=request)
        return httpx.Response(200, content=b"done", request=request)

    client = SubhdClient(
        base_url="https://subhd.test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client._request_allowed(
        "PUT",
        "https://subhd.test/start",
        content=b"payload",
        headers={"Content-Type": "application/octet-stream", "Content-Length": "7"},
    )

    assert response.content == b"done"
    assert [(request.method, request.url.path, request.content) for request in requests] == [
        ("PUT", "/start", b"payload"),
        ("PUT", "/final", b"payload"),
    ]
    assert requests[1].headers["Content-Type"] == "application/octet-stream"
    assert requests[1].headers["Content-Length"] == "7"


@pytest.mark.parametrize("status_code", [302, 303])
def test_request_allowed_rewrites_put_to_get_for_browser_compatible_redirects(status_code: int) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/start":
            return httpx.Response(status_code, headers={"Location": "/final"}, request=request)
        return httpx.Response(200, content=b"done", request=request)

    client = SubhdClient(
        base_url="https://subhd.test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client._request_allowed(
        "PUT",
        "https://subhd.test/start",
        content=b"payload",
        headers={"Content-Type": "application/octet-stream", "Content-Length": "7"},
    )

    assert response.content == b"done"
    assert [(request.method, request.url.path, request.content) for request in requests] == [
        ("PUT", "/start", b"payload"),
        ("GET", "/final", b""),
    ]
    assert "Content-Type" not in requests[1].headers
    assert "Content-Length" not in requests[1].headers


def test_request_allowed_discards_multipart_body_when_rewriting_to_get() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/start":
            return httpx.Response(303, headers={"Location": "/final"}, request=request)
        return httpx.Response(200, content=b"done", request=request)

    client = SubhdClient(
        base_url="https://subhd.test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client._request_allowed(
        "POST",
        "https://subhd.test/start",
        files={"subtitle": ("subtitle.srt", b"payload")},
    )

    assert response.content == b"done"
    assert [(request.method, request.url.path) for request in requests] == [
        ("POST", "/start"),
        ("GET", "/final"),
    ]
    assert requests[0].content
    assert requests[1].content == b""
    assert "Content-Type" not in requests[1].headers
    assert "Content-Length" not in requests[1].headers


@pytest.mark.parametrize("status_code", [307, 308])
def test_request_allowed_preserves_post_and_json_body(status_code: int) -> None:
    requests: list[tuple[str, str, bytes]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path, request.content))
        if request.url.path == "/start":
            return httpx.Response(status_code, headers={"Location": "/final"}, request=request)
        return httpx.Response(200, content=b"done", request=request)

    client = SubhdClient(
        base_url="https://subhd.test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    response = client._request_allowed(
        "POST",
        "https://subhd.test/start",
        json={"sid": "abc"},
    )

    assert response.content == b"done"
    assert requests == [
        ("POST", "/start", b'{"sid":"abc"}'),
        ("POST", "/final", b'{"sid":"abc"}'),
    ]


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


def test_subhd_client_prepares_download_page_before_opening_gate(tmp_path: Path) -> None:
    requests: list[tuple[str, str, bytes, str | None]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, str(request.url), request.content, request.headers.get("Referer")))
        if request.url.path == "/a/kAqdvK":
            return httpx.Response(200, text="<html>detail</html>", request=request)
        if request.url.path == "/api/sub/prepare-download":
            return httpx.Response(200, json={"success": True, "url": "/down/kAqdvK"}, request=request)
        if request.url.path == "/down/kAqdvK":
            return httpx.Response(200, text="<html>gate</html>", request=request)
        if request.url.path == "/api/sub/down":
            return httpx.Response(
                200,
                json={"success": True, "pass": True, "url": "https://dl.subhd.me/result.zip"},
                request=request,
            )
        if str(request.url) == "https://dl.subhd.me/result.zip":
            return httpx.Response(200, content=b"PK\x03\x04archive", request=request)
        raise AssertionError(f"Unexpected request: {request.method} {request.url}")

    client = SubhdClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = parse_search_response(SEARCH_HTML, "https://subhd.tv/search/Nell%201994")[0]

    downloaded = client.download(result, tmp_path)

    assert downloaded.path.read_bytes() == b"PK\x03\x04archive"
    assert [(method, url) for method, url, _body, _referer in requests] == [
        ("GET", "https://subhd.tv/a/kAqdvK"),
        ("POST", "https://subhd.tv/api/sub/prepare-download"),
        ("GET", "https://subhd.tv/down/kAqdvK"),
        ("POST", "https://subhd.tv/api/sub/down"),
        ("GET", "https://dl.subhd.me/result.zip"),
    ]
    assert requests[1][2] == b'{"sid":"kAqdvK"}'
    assert requests[1][3] == "https://subhd.tv/a/kAqdvK"
    assert requests[2][3] == "https://subhd.tv/a/kAqdvK"


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (None, "invalid JSON"),
        ([], "invalid JSON"),
        ({"success": False, "msg": "准备失败"}, "准备失败"),
        ({"success": True}, "omitted a prepared download URL"),
        ({"success": True, "url": "https://evil.example/down/kAqdvK"}, "prepared download URL is not allowed"),
        ({"success": True, "url": "/down/other"}, "prepared download URL does not match subtitle"),
        ({"success": True, "url": "/down/kAqdvK?token=x"}, "prepared download URL does not match subtitle"),
    ],
)
def test_subhd_prepare_download_rejects_invalid_responses(payload: object, message: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if payload is None:
            return httpx.Response(200, text="not json", request=request)
        return httpx.Response(200, json=payload, request=request)

    client = SubhdClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = parse_search_response(SEARCH_HTML, "https://subhd.tv/search/Nell%201994")[0]

    with pytest.raises(FixsubError, match=message):
        client._prepare_download_url(result, "https://subhd.tv/a/kAqdvK")


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
        if str(request.url) == "https://subhd.tv/api/sub/prepare-download":
            assert request.method == "POST"
            assert "tk_download=ready" in request.headers.get("Cookie", "")
            assert request.headers["Referer"] == "https://subhd.tv/a/kAqdvK"
            assert request.content == b'{"sid":"kAqdvK"}'
            return httpx.Response(200, json={"success": True, "url": "/down/kAqdvK"}, request=request)
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
            assert "tk_download=ready" not in request.headers.get("Cookie", "")
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
        ("POST", "https://subhd.tv/api/sub/prepare-download"),
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
        if request.url.path == "/api/sub/prepare-download":
            return httpx.Response(200, json={"success": True, "url": "/down/kAqdvK"}, request=request)
        if str(request.url) == "https://subhd.tv/down/kAqdvK":
            return httpx.Response(200, content=b"PK\x03\x04legacy", request=request)
        raise AssertionError(f"Unexpected request: {request.url}")

    client = SubhdClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = parse_search_response(SEARCH_HTML, "https://subhd.tv/search/Nell%201994")[0]

    downloaded = client.download(result, tmp_path)

    assert downloaded.path.read_bytes() == b"PK\x03\x04legacy"
    assert requested_urls == [
        "https://subhd.tv/a/kAqdvK",
        "https://subhd.tv/api/sub/prepare-download",
        "https://subhd.tv/down/kAqdvK",
    ]


def test_subhd_client_download_rejects_empty_final_response(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/a/kAqdvK":
            return httpx.Response(200, text="<html>detail</html>", request=request)
        if request.url.path == "/api/sub/prepare-download":
            return httpx.Response(200, json={"success": True, "url": "/down/kAqdvK"}, request=request)
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
        if request.url.path == "/api/sub/prepare-download":
            return httpx.Response(200, json={"success": True, "url": "/down/kAqdvK"}, request=request)
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
        if request.url.path == "/api/sub/prepare-download":
            return httpx.Response(200, json={"success": True, "url": "/down/kAqdvK"}, request=request)
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
    ("failed_stage", "expected_message"),
    [
        ("detail", "SubHD detail request failed"),
        ("prepare", "SubHD download preparation request failed"),
        ("gate", "SubHD download page request failed"),
        ("api", "SubHD download API request failed"),
        ("file", "SubHD subtitle file request failed"),
    ],
)
@pytest.mark.parametrize("failure_kind", ["status", "transport"])
def test_subhd_client_reports_stage_specific_network_errors(
    tmp_path: Path,
    failed_stage: str,
    expected_message: str,
    failure_kind: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/a/kAqdvK":
            stage = "detail"
            response = httpx.Response(200, text="<html>detail</html>", request=request)
        elif request.url.path == "/api/sub/prepare-download":
            stage = "prepare"
            response = httpx.Response(200, json={"success": True, "url": "/down/kAqdvK"}, request=request)
        elif request.url.path == "/down/kAqdvK":
            stage = "gate"
            response = httpx.Response(200, text="<html>gate</html>", request=request)
        elif request.url.path == "/api/sub/down":
            stage = "api"
            response = httpx.Response(
                200,
                json={"success": True, "pass": True, "url": "https://dl.subhd.me/result.srt"},
                request=request,
            )
        elif str(request.url) == "https://dl.subhd.me/result.srt":
            stage = "file"
            response = httpx.Response(200, content=b"subtitle", request=request)
        else:
            raise AssertionError(f"Unexpected request: {request.url}")

        if stage != failed_stage:
            return response
        if failure_kind == "transport":
            raise httpx.ConnectError("connection failed", request=request)
        return httpx.Response(503, request=request)

    client = SubhdClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = parse_search_response(SEARCH_HTML, "https://subhd.tv/search/Nell%201994")[0]

    with pytest.raises(FixsubError, match=expected_message) as exc_info:
        client.download(result, tmp_path)

    expected_cause = httpx.ConnectError if failure_kind == "transport" else httpx.HTTPStatusError
    assert isinstance(exc_info.value.__cause__, expected_cause)


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
        if request.url.path == "/api/sub/prepare-download":
            return httpx.Response(200, json={"success": True, "url": "/down/kAqdvK"}, request=request)
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
    ("message", "expected"),
    [
        ("  challenge\n\t\x00failed\r\nretry  ", "challenge failed retry"),
        ("x" * 250, "x" * 200),
        (123, "request rejected"),
        ("\n\t\x00", "request rejected"),
    ],
)
def test_subhd_client_download_api_sanitizes_rejection_message(message: object, expected: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"success": False, "pass": False, "msg": message},
            request=request,
        )

    client = SubhdClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = parse_search_response(SEARCH_HTML, "https://subhd.tv/search/Nell%201994")[0]

    with pytest.raises(FixsubError) as exc_info:
        client._api_download_url(result, "https://subhd.tv/down/kAqdvK")

    assert str(exc_info.value) == f"SubHD download API rejected the request: {expected}"


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
        if request.url.path == "/api/sub/prepare-download":
            return httpx.Response(200, json={"success": True, "url": "/down/kAqdvK"}, request=request)
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
        if request.url.path == "/api/sub/prepare-download":
            return httpx.Response(200, json={"success": True, "url": "/down/kAqdvK"}, request=request)
        if request.url.path == "/down/kAqdvK":
            return httpx.Response(200, content=b"1\n00:00:01,000 --> 00:00:02,000\nHi\n", request=request)
        raise AssertionError(f"Unexpected request: {request.url}")

    client = SubhdClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = parse_search_response(SEARCH_HTML.replace("SRT", "字幕"), "https://subhd.tv/search/Nell%201994")[0]

    downloaded = client.download(result, tmp_path)

    assert downloaded.path.name == "subhd_kAqdvK.srt"
