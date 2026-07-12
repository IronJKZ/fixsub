# SubHD Download API Compatibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make SubHD downloads work with its current session-backed JSON API while retaining legacy direct downloads, ASSRT behavior, and strict URL/payload safety.

**Architecture:** Keep all changes inside `SubhdClient` and its focused tests. The client first establishes the per-subtitle session, accepts a legacy direct file when present, otherwise requests the current JSON API and downloads its validated URL through a bounded, allowlisted redirect helper.

**Tech Stack:** Python 3.11+, httpx, BeautifulSoup, pytest

## Global Constraints

- Preserve ASSRT unchanged.
- Preserve default aggregate search across `assrt,subhd`.
- Keep `--max-candidates` semantics unchanged.
- Do not use browser automation, CAPTCHA solving, or SubHD login.
- Only HTTPS SubHD-owned download URLs and configured test hosts may be requested.
- Reject HTML, empty payloads, unsafe URLs, and unsafe redirects.
- Write tests before every production behavior change and observe the expected failure.

---

## File Structure

- Modify `fixsub/providers/subhd.py`: session flow, JSON API parsing, URL allowlist, bounded redirects, and payload persistence.
- Modify `tests/test_subhd.py`: regression tests for current API, legacy compatibility, session cookies, error responses, URL validation, redirects, and payload rejection.
- No ASSRT, registry, ranking, CLI, or model file changes are required.

### Task 1: Current API Flow and Legacy Compatibility

**Files:**
- Modify: `tests/test_subhd.py`
- Modify: `fixsub/providers/subhd.py:14-168`

**Interfaces:**
- Consumes: existing `SearchResult`, `DownloadedFile`, `FixsubError`, and the injected `httpx.Client` session.
- Produces: `SubhdClient.download(result, target_dir) -> DownloadedFile` with both legacy and current SubHD download support.
- Produces internal helpers `_api_download_url(self, result: SearchResult, gate_url: str) -> str` and `_save_download(self, response: httpx.Response, result: SearchResult, target_dir) -> DownloadedFile`.

- [ ] **Step 1: Replace the legacy-only happy-path test with a failing current-API test**

Add this test to `tests/test_subhd.py`, leaving the existing production code unchanged:

```python
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
```

- [ ] **Step 2: Run the current-API test and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_subhd.py::test_subhd_client_download_uses_session_api_and_saves_archive -v
```

Expected: FAIL because the current client requests `/down/kAqdvK` first and rejects the HTML gate without visiting the detail page or calling `/api/sub/down`.

- [ ] **Step 3: Add a failing legacy-direct compatibility test**

Add:

```python
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
```

- [ ] **Step 4: Implement the minimal session/API flow**

In `fixsub/providers/subhd.py`, add these methods to `SubhdClient` and replace `download()` with the following behavior. Do not add redirect hardening yet; Task 2 adds it test-first.

```python
    def _save_download(self, response: httpx.Response, result: SearchResult, target_dir) -> DownloadedFile:
        content_type = response.headers.get("Content-Type", "").lower()
        if not response.content:
            raise FixsubError(f"SubHD download returned an empty response: {response.request.url}")
        if _looks_like_html(response.content, content_type):
            raise FixsubError(f"SubHD download returned HTML instead of a subtitle file: {response.request.url}")
        suffix = _download_suffix(response.content, result, response)
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_id = _safe_id(result.result_id)
        target_path = target_dir / f"subhd_{safe_id}{suffix}"
        target_path.write_bytes(response.content)
        return DownloadedFile(
            candidate_id=f"subhd_{safe_id}",
            provider="subhd",
            path=target_path,
            source_url=str(response.request.url),
        )

    def _api_download_url(self, result: SearchResult, gate_url: str) -> str:
        api_url = f"{self.base_url}/api/sub/down"
        response = self.http_client.post(
            api_url,
            json={"sid": result.result_id},
            headers={"Referer": gate_url},
        )
        response.raise_for_status()
        try:
            payload = response.json()
        except ValueError as exc:
            raise FixsubError("SubHD download API returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise FixsubError("SubHD download API returned invalid JSON")
        if payload.get("success") is not True or payload.get("pass") is not True:
            message = str(payload.get("msg") or "request rejected")
            raise FixsubError(f"SubHD download API rejected the request: {message}")
        download_url = payload.get("url")
        if not isinstance(download_url, str) or not download_url.strip():
            raise FixsubError("SubHD download API omitted a download URL")
        return urljoin(api_url, download_url.strip())

    def download(self, result: SearchResult, target_dir) -> DownloadedFile:
        detail_url = result.detail_url or f"{self.base_url}/a/{result.result_id}"
        detail_response = self.http_client.get(detail_url)
        detail_response.raise_for_status()

        gate_url = result.download_url or f"{self.base_url}/down/{result.result_id}"
        gate_response = self.http_client.get(gate_url, headers={"Referer": detail_url})
        gate_response.raise_for_status()
        gate_content_type = gate_response.headers.get("Content-Type", "").lower()
        if not _looks_like_html(gate_response.content, gate_content_type):
            return self._save_download(gate_response, result, target_dir)

        download_url = self._api_download_url(result, gate_url)
        download_response = self.http_client.get(download_url)
        download_response.raise_for_status()
        return self._save_download(download_response, result, target_dir)
```

- [ ] **Step 5: Update existing payload tests to model detail and gate requests**

Replace the two HTML rejection tests with one parameterized test that reaches the final API-provided payload:

```python
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
```

Update the plain-SRT test to exercise the legacy direct response:

```python
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
```

- [ ] **Step 6: Run focused tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_subhd.py -v
```

Expected: all SubHD tests PASS.

- [ ] **Step 7: Commit Task 1**

```bash
git add fixsub/providers/subhd.py tests/test_subhd.py
git commit -m "fix: support current SubHD download API"
```

### Task 2: Download URL and Redirect Hardening

**Files:**
- Modify: `tests/test_subhd.py`
- Modify: `fixsub/providers/subhd.py`

**Interfaces:**
- Consumes: Task 1's `_api_download_url()`, `_save_download()`, and dual-flow `download()`.
- Produces: `_is_allowed_subhd_url(url: str, base_url: str) -> bool`.
- Produces: `SubhdClient._request_allowed(method: str, url: str, **kwargs) -> httpx.Response` with bounded, validated redirects.

- [ ] **Step 1: Add failing URL allowlist tests**

Import `_is_allowed_subhd_url` in `tests/test_subhd.py` and add:

```python
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
```

- [ ] **Step 2: Run the allowlist tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_subhd.py::test_is_allowed_subhd_url tests/test_subhd.py::test_is_allowed_subhd_url_accepts_configured_test_host -v
```

Expected: collection ERROR because `_is_allowed_subhd_url` does not exist.

- [ ] **Step 3: Implement URL allowlist validation**

Add constants and helper to `fixsub/providers/subhd.py`:

```python
SUBHD_OWNED_DOMAINS = frozenset(
    {
        "subhd.tv",
        "subhd.me",
        "subhd.one",
        "subhd.top",
        "subhd.cc",
        "subhdtw.com",
        "subhd.com",
    }
)
MAX_SUBHD_REDIRECTS = 5


def _hostname_matches(hostname: str, domain: str) -> bool:
    return hostname == domain or hostname.endswith(f".{domain}")


def _is_allowed_subhd_url(url: str, base_url: str) -> bool:
    try:
        parsed = urlparse(url)
        base = urlparse(base_url)
        port = parsed.port
    except ValueError:
        return False
    hostname = (parsed.hostname or "").lower().rstrip(".")
    base_hostname = (base.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not hostname:
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    if port not in {None, 443}:
        return False
    allowed_domains = set(SUBHD_OWNED_DOMAINS)
    if base_hostname:
        allowed_domains.add(base_hostname)
    return any(_hostname_matches(hostname, domain) for domain in allowed_domains)
```

- [ ] **Step 4: Add failing unsafe API URL and redirect tests**

Add:

```python
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
```

- [ ] **Step 5: Run unsafe URL tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest tests/test_subhd.py::test_subhd_client_rejects_untrusted_api_url_without_requesting_it tests/test_subhd.py::test_subhd_client_rejects_redirect_outside_allowed_domains -v
```

Expected: FAIL because Task 1 follows the API URL using the injected client's redirect behavior.

- [ ] **Step 6: Implement bounded validated requests**

Add this method to `SubhdClient`:

```python
    def _request_allowed(self, method: str, url: str, **kwargs) -> httpx.Response:
        current_method = method.upper()
        current_url = url
        current_kwargs = dict(kwargs)
        for redirect_count in range(MAX_SUBHD_REDIRECTS + 1):
            if not _is_allowed_subhd_url(current_url, self.base_url):
                if redirect_count:
                    raise FixsubError(f"SubHD download redirected outside allowed domains: {current_url}")
                raise FixsubError(f"SubHD download URL is not allowed: {current_url}")
            response = self.http_client.request(
                current_method,
                current_url,
                follow_redirects=False,
                **current_kwargs,
            )
            if not response.is_redirect:
                response.raise_for_status()
                return response
            location = response.headers.get("Location")
            if not location:
                raise FixsubError(f"SubHD download redirect omitted Location: {current_url}")
            current_url = urljoin(current_url, location)
            if response.status_code in {301, 302, 303} and current_method != "HEAD":
                current_method = "GET"
                current_kwargs.pop("json", None)
                current_kwargs.pop("data", None)
                current_kwargs.pop("content", None)
        raise FixsubError(f"SubHD download exceeded {MAX_SUBHD_REDIRECTS} redirects: {url}")
```

Use `_request_allowed()` for the detail request, gate request, JSON API request, and final payload request. In `_api_download_url()`, validate the resolved URL before returning it:

```python
        resolved_url = urljoin(api_url, download_url.strip())
        if not _is_allowed_subhd_url(resolved_url, self.base_url):
            raise FixsubError(f"SubHD download URL is not allowed: {resolved_url}")
        return resolved_url
```

- [ ] **Step 7: Add API validation and empty-payload tests**

Add parameterized API rejection cases:

```python
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
```

Add a successful API response whose final URL returns an empty payload:

```python
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
```

- [ ] **Step 8: Run all focused SubHD tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_subhd.py -v
```

Expected: all SubHD tests PASS with no warnings or unexpected output.

- [ ] **Step 9: Commit Task 2**

```bash
git add fixsub/providers/subhd.py tests/test_subhd.py
git commit -m "fix: harden SubHD download redirects"
```

### Task 3: Regression and Real-Movie Acceptance

**Files:**
- Verify only: entire repository
- Runtime artifacts outside git: `/Volumes/Media/movies/Fried.Green.Tomatoes.1991.EXTENDED.1080p.BluRay.X264-AMIABLE [PublicHD]/.fixsub/`

**Interfaces:**
- Consumes: completed `SubhdClient` behavior from Tasks 1 and 2.
- Produces: fresh verification evidence for the full suite and the original failing movie.

- [ ] **Step 1: Run formatting/diff checks**

Run:

```bash
git diff --check
```

Expected: exit 0 with no output.

- [ ] **Step 2: Run the complete automated test suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests PASS with zero failures.

- [ ] **Step 3: Run the original real-movie scenario without writing a final subtitle**

Run from the movie directory:

```bash
fixsub --dry-run --providers subhd --max-candidates 20
```

Expected:

- The exact AMIABLE candidate downloads and extracts.
- The run does not end with `No downloadable or extractable subtitle candidates.`
- The log does not record `SubHD download returned HTML instead of a subtitle file` for the AMIABLE candidate.
- Because this is a dry run, no final `<video-stem>.zh.*` subtitle is written.

- [ ] **Step 4: Inspect acceptance metadata**

Run:

```bash
jq '{downloaded: (.downloaded | length), candidates: (.candidates | length), decisions: (.decisions | length), message}' .fixsub/metadata/results.json
```

Expected: `downloaded >= 1`, `candidates >= 1`, and `decisions >= 1`. The message may report a dry-run best candidate or low-confidence audio alignment, but must not report a download/extraction failure.

- [ ] **Step 5: Review the final diff and repository state**

Run:

```bash
git diff HEAD~2 -- fixsub/providers/subhd.py tests/test_subhd.py
git status --short
```

Expected: only the intended provider/tests changes are present and the working tree is clean after the task commits.
