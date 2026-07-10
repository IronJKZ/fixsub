# SubHD, ASSRT Web Fallback, and Search Query Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `fixsub` beyond the ASSRT API-only path by adding ASSRT web download fallback, SubHD search/download support, safer logging, and stronger movie search query generation.

**Architecture:** Keep the existing pipeline shape: detect one video, generate queries, gather provider `SearchResult` objects, rank them, download/extract/normalize, score original vs synced subtitle, and write the final subtitle. Add focused provider modules for ASSRT web fallback and SubHD HTML parsing, then update the CLI to orchestrate multiple providers without leaking provider secrets into logs.

**Tech Stack:** Python 3.11, Typer, httpx, charset-normalizer, ffprobe, ffsubsync, unar/unrar, pytest, BeautifulSoup 4 for HTML parsing.

---

## File Structure

- Modify `pyproject.toml` and `setup.py`: add `beautifulsoup4>=4.12.0` as a runtime dependency so ASSRT/SubHD HTML parsing is not built on brittle regular expressions.
- Modify `fixsub/movie.py`: harden query generation using lessons from `douban_movie_searcher.py`: preserve year, normalize diacritics, dedupe case-insensitively, add file-name and release-name variants, and avoid unnecessary quality-only searches.
- Modify `fixsub/ranking.py`: include provider-specific raw fields such as SubHD `version`, `movie_title`, `filename`, and ASSRT `videoname` in the ranking haystack.
- Modify `fixsub/logging_utils.py`: redact `token=...` query parameters and the current `ASSRT_TOKEN` value before writing log lines.
- Modify `fixsub/providers/assrt_api.py`: keep API search/download as primary behavior, add web detail-page fallback when API download returns 404, and parse `/download/...` links from ASSRT detail HTML.
- Create `fixsub/providers/subhd.py`: implement SubHD HTML search parsing and `/down/{sid}` download handling behind the same `search()` and `download()` shape as `AssrtClient`.
- Create `fixsub/providers/registry.py`: centralize provider parsing, construction, token requirements, and provider display names.
- Modify `fixsub/providers/__init__.py`: export `AssrtClient`, `SubhdClient`, and registry helpers.
- Modify `fixsub/cli.py`: allow `--providers assrt,subhd`, skip ASSRT gracefully when token is absent and SubHD is enabled, run all active providers for each query, and download with the provider client associated with each candidate.
- Modify `README.md`: document SubHD, ASSRT web fallback, provider selection, token behavior, diagnostics, and the realistic dry-run flow.
- Add tests in `tests/test_movie.py`, `tests/test_decision_ranking_output.py`, `tests/test_logging_utils.py`, `tests/test_assrt_api.py`, `tests/test_subhd.py`, and `tests/test_cli_pipeline.py`.

## External Behavior Targets

- Default provider list becomes `assrt,subhd`.
- If `ASSRT_TOKEN` is present, `assrt` runs first and SubHD fills gaps.
- If `ASSRT_TOKEN` is missing and `subhd` is enabled, the run continues with SubHD and writes a log line saying ASSRT was skipped.
- If the user explicitly runs `--providers assrt` without `ASSRT_TOKEN`, preserve the existing hard stop: `ASSRT_TOKEN is required for ASSRT API access.`
- ASSRT API download remains the first download path. If it returns HTTP 404, the client fetches the public ASSRT detail page and downloads from the public `/download/...` link.
- SubHD search uses `https://subhd.tv/search/{quoted_query}` and parses `/a/{sid}` result cards. SubHD download uses `https://subhd.tv/down/{sid}` and treats HTML responses as a clear provider download failure rather than saving them as subtitle files.
- Logs never contain the literal ASSRT token value or a `token=<secret>` query value.
- Metadata continues using the existing top-level keys so existing consumers do not break.

## Task 1: Harden Search Query Generation

**Files:**
- Modify: `fixsub/movie.py`
- Modify: `tests/test_movie.py`
- Reference: `douban_movie_searcher.py:82-216`

- [ ] **Step 1: Write failing tests for robust query generation**

Add these tests to `tests/test_movie.py`:

```python
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
```

- [ ] **Step 2: Run query tests to verify current behavior fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_movie.py::test_generate_search_queries_adds_file_and_release_variants tests/test_movie.py::test_generate_search_queries_dedupes_case_insensitively tests/test_movie.py::test_generate_search_queries_normalizes_diacritics -v
```

Expected: at least `test_generate_search_queries_adds_file_and_release_variants` and `test_generate_search_queries_normalizes_diacritics` fail because `generate_search_queries()` currently only returns three simple variants and does not normalize diacritics.

- [ ] **Step 3: Implement minimal robust query helpers**

In `fixsub/movie.py`, add imports and helpers near the existing constants:

```python
import unicodedata
```

```python
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
        if re.fullmatch(r"\d+(?:\.\d+)?", token):
            continue
        tokens.append(token)
    return " ".join(tokens)
```

Replace `generate_search_queries()` in `fixsub/movie.py` with:

```python
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
```

- [ ] **Step 4: Run query tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_movie.py -v
```

Expected: all tests in `tests/test_movie.py` pass.

- [ ] **Step 5: Commit**

```bash
git add fixsub/movie.py tests/test_movie.py
git commit -m "feat: harden subtitle search queries"
```

## Task 2: Redact Secrets from Logs

**Files:**
- Modify: `fixsub/logging_utils.py`
- Create: `tests/test_logging_utils.py`

- [ ] **Step 1: Write failing tests for token redaction**

Create `tests/test_logging_utils.py`:

```python
from pathlib import Path

from fixsub.logging_utils import append_log, redact_log_message


def test_redact_log_message_removes_token_query_value(monkeypatch) -> None:
    monkeypatch.setenv("ASSRT_TOKEN", "secret-token")

    message = (
        "Client error for url "
        "'https://api.assrt.net/v1/sub/download?token=secret-token&id=156894'"
    )

    assert redact_log_message(message) == (
        "Client error for url "
        "'https://api.assrt.net/v1/sub/download?token=<redacted>&id=156894'"
    )


def test_append_log_redacts_current_assrt_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ASSRT_TOKEN", "secret-token")
    log_path = tmp_path / "fixsub.log"

    append_log(log_path, "failed with secret-token")

    assert log_path.read_text(encoding="utf-8") == "failed with <redacted>\n"
```

- [ ] **Step 2: Run redaction tests to verify current behavior fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_logging_utils.py -v
```

Expected: fail with `ModuleNotFoundError` for the new test file before creation, then fail with `ImportError` or assertion failures after the test file exists because `redact_log_message()` does not exist and `append_log()` writes raw messages.

- [ ] **Step 3: Implement redaction**

Replace `fixsub/logging_utils.py` with this version:

```python
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


TOKEN_QUERY_RE = re.compile(r"([?&]token=)[^&'\"\\s]+", re.IGNORECASE)


def _json_ready(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_ready(item) for key, item in value.items()}
    return value


def redact_log_message(message: str) -> str:
    redacted = TOKEN_QUERY_RE.sub(r"\1<redacted>", message)
    token = os.environ.get("ASSRT_TOKEN", "").strip()
    if token:
        redacted = redacted.replace(token, "<redacted>")
    return redacted


def write_results_json(target: Path, payload: dict[str, Any]) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(_json_ready(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def append_log(log_path: Path, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as file:
        file.write(f"{redact_log_message(message).rstrip()}\n")
```

- [ ] **Step 4: Run redaction tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/test_logging_utils.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add fixsub/logging_utils.py tests/test_logging_utils.py
git commit -m "fix: redact provider secrets from logs"
```

## Task 3: Add ASSRT Web Download Fallback

**Files:**
- Modify: `pyproject.toml`
- Modify: `setup.py`
- Modify: `fixsub/providers/assrt_api.py`
- Modify: `tests/test_assrt_api.py`

- [ ] **Step 1: Write failing tests for ASSRT web fallback**

Append these tests to `tests/test_assrt_api.py`:

```python
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
        if str(request.url) == "https://secure.assrt.net/download/156894/%E5%A6%AE%E5%84%BF%E7%9A%84%E8%8A%B3%E5%BF%83.Nell.1994.rar":
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
    assert downloaded.source_url == "https://secure.assrt.net/download/156894/%E5%A6%AE%E5%84%BF%E7%9A%84%E8%8A%B3%E5%BF%83.Nell.1994.rar"
    assert requests[1] == "https://secure.assrt.net/xml/sub/156/156894.xml"


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
```

- [ ] **Step 2: Run ASSRT fallback tests to verify current behavior fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_assrt_api.py::test_client_download_falls_back_to_assrt_detail_page_on_api_404 tests/test_assrt_api.py::test_client_download_prefers_assrt_single_chinese_file_from_detail_page -v
```

Expected: both tests fail because `AssrtClient.download()` currently raises the 404 from the API download endpoint and does not fetch the public detail page.

- [ ] **Step 3: Add BeautifulSoup dependency**

In `pyproject.toml`, add this dependency to `[project].dependencies`:

```toml
  "beautifulsoup4>=4.12.0",
```

In `setup.py`, if `install_requires` exists, add the same package:

```python
"beautifulsoup4>=4.12.0",
```

- [ ] **Step 4: Implement ASSRT detail parsing and fallback**

In `fixsub/providers/assrt_api.py`, add imports:

```python
from bs4 import BeautifulSoup
from httpx import HTTPStatusError
from urllib.parse import urljoin
```

Add constants below `ASSRT_API_BASE`:

```python
ASSRT_WEB_BASE = "https://secure.assrt.net"
```

Add these helpers before `class AssrtClient`:

```python
def _assrt_detail_url(result: SearchResult) -> str:
    if result.detail_url:
        return urljoin(ASSRT_WEB_BASE, result.detail_url)
    prefix = result.result_id[:3]
    return f"{ASSRT_WEB_BASE}/xml/sub/{prefix}/{result.result_id}.xml"


def _single_file_downloads(detail_html: str) -> list[str]:
    matches = re.findall(
        r"""onthefly\(["']([^"']+)["']\s*,\s*["']([^"']+)["']\s*,\s*["']([^"']+)["']\)""",
        detail_html,
    )
    urls = []
    for subtitle_id, file_index, filename in matches:
        urls.append(f"/download/{subtitle_id}/-/{file_index}/{filename}")
    return urls


def _is_chinese_download(url: str) -> bool:
    lowered = unquote(url).lower()
    return any(token in lowered for token in ["chs", "cht", "zh", "简", "繁"])


def _assrt_web_download_urls(detail_html: str) -> list[str]:
    soup = BeautifulSoup(detail_html, "html.parser")
    urls = _single_file_downloads(detail_html)
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        if "/download/" in href:
            urls.append(href)
    deduped: list[str] = []
    seen: set[str] = set()
    for url in sorted(urls, key=lambda value: 0 if _is_chinese_download(value) else 1):
        if url in seen:
            continue
        deduped.append(url)
        seen.add(url)
    return [urljoin(ASSRT_WEB_BASE, url) for url in deduped]
```

Inside `AssrtClient`, add:

```python
    def _download_response(self, url: str, params: dict[str, str] | None = None) -> httpx.Response:
        response = self.http_client.get(url, params=params)
        response.raise_for_status()
        return response

    def _download_from_assrt_web(self, result: SearchResult) -> tuple[httpx.Response, str]:
        detail_url = _assrt_detail_url(result)
        detail_response = self._download_response(detail_url)
        for download_url in _assrt_web_download_urls(detail_response.text):
            response = self._download_response(download_url)
            return response, download_url
        raise RuntimeError(f"ASSRT detail page did not expose a download link: {detail_url}")
```

Replace `download()` with:

```python
    def download(self, result: SearchResult, target_dir) -> DownloadedFile:
        url = result.download_url or f"{self.base_url}/sub/download"
        params = {"token": self.token}
        if not result.download_url:
            params["id"] = result.result_id
        try:
            response = self._download_response(url, params=params)
            source_url = str(response.request.url)
        except HTTPStatusError as exc:
            if exc.response.status_code != 404:
                raise
            response, source_url = self._download_from_assrt_web(result)
        suffix = _download_suffix(response.content, result, response)
        safe_id = _sanitize_result_id(result.result_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"assrt_{safe_id}{suffix}"
        target_path.write_bytes(response.content)
        return DownloadedFile(candidate_id=f"assrt_{safe_id}", provider="assrt", path=target_path, source_url=source_url)
```

- [ ] **Step 5: Run ASSRT provider tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_assrt_api.py -v
```

Expected: all ASSRT tests pass.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml setup.py fixsub/providers/assrt_api.py tests/test_assrt_api.py
git commit -m "feat: add assrt web download fallback"
```

## Task 4: Add SubHD Provider

**Files:**
- Create: `fixsub/providers/subhd.py`
- Create: `tests/test_subhd.py`
- Modify: `fixsub/providers/__init__.py`

- [ ] **Step 1: Write failing tests for SubHD search parsing**

Create `tests/test_subhd.py`:

```python
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
```

- [ ] **Step 2: Run search tests to verify current behavior fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_subhd.py::test_parse_search_response_extracts_subhd_results tests/test_subhd.py::test_subhd_client_search_uses_encoded_query -v
```

Expected: fail because `fixsub.providers.subhd` does not exist.

- [ ] **Step 3: Implement SubHD search parser**

Create `fixsub/providers/subhd.py`:

```python
from __future__ import annotations

import re
from pathlib import PurePath
from typing import Any
from urllib.parse import quote, unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from fixsub.errors import FixsubError
from fixsub.models import DownloadedFile, SearchResult

SUBHD_BASE = "https://subhd.tv"
ALLOWED_DOWNLOAD_SUFFIXES = {".zip", ".rar", ".7z", ".srt", ".ass", ".ssa"}


def _text(node: Any) -> str:
    return node.get_text(" ", strip=True) if node else ""


def _detect_language(labels: list[str]) -> str | None:
    joined = " ".join(labels)
    if "双语" in joined:
        return "bilingual"
    if "简体" in joined or "简中" in joined:
        return "zh-Hans"
    if "繁体" in joined or "繁中" in joined:
        return "zh-Hant"
    return None


def _detect_format(labels: list[str]) -> str | None:
    for label in labels:
        lowered = label.lower()
        if lowered in {"ass", "ssa", "srt"}:
            return lowered
    return None


def _safe_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return safe or "subtitle"


def _content_disposition_filename(value: str | None) -> str | None:
    if not value:
        return None
    filename_star = re.search(r"""filename\*\s*=\s*(?:UTF-8'')?("?)([^";]+)\1""", value, re.IGNORECASE)
    if filename_star:
        return unquote(filename_star.group(2).strip())
    filename = re.search(r"""filename\s*=\s*("?)([^";]+)\1""", value, re.IGNORECASE)
    if filename:
        return filename.group(2).strip()
    return None


def _allowed_suffix(value: str | None) -> str | None:
    if not value:
        return None
    suffix = PurePath(unquote(value)).suffix.lower()
    return suffix if suffix in ALLOWED_DOWNLOAD_SUFFIXES else None


def _download_suffix(content: bytes, result: SearchResult, response: httpx.Response) -> str:
    if content.startswith(b"PK\x03\x04"):
        return ".zip"
    if content.startswith(b"Rar!\x1a\x07"):
        return ".rar"
    if content.startswith(b"7z\xbc\xaf\x27\x1c"):
        return ".7z"
    header_filename = _content_disposition_filename(response.headers.get("Content-Disposition"))
    for value in [header_filename, urlparse(str(response.request.url)).path, result.title]:
        suffix = _allowed_suffix(value)
        if suffix:
            return suffix
    format_suffix = _allowed_suffix(f".{result.format.lstrip('.')}") if result.format else None
    return format_suffix or ".bin"


def parse_search_response(html: str, search_url: str = SUBHD_BASE) -> list[SearchResult]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[SearchResult] = []
    for detail_anchor in soup.select('a[href^="/a/"]'):
        href = str(detail_anchor.get("href") or "")
        match = re.fullmatch(r"/a/([^/?#]+)", href)
        if not match:
            continue
        result_id = match.group(1)
        card = detail_anchor.find_parent("div", class_=lambda value: value and "bg-white" in value)
        if card is None:
            continue
        movie_title = _text(card.select_one(".float-start.f16 a")) or _text(detail_anchor)
        version = _text(card.select_one(".view-text a"))
        labels = [_text(label) for label in card.select(".text-truncate span")]
        labels = [label for label in labels if label]
        title = " ".join(part for part in [movie_title, version] if part).strip()
        if not title:
            continue
        detail_url = urljoin(search_url, href)
        results.append(
            SearchResult(
                provider="subhd",
                result_id=result_id,
                title=title,
                download_url=urljoin(search_url, f"/down/{result_id}"),
                detail_url=detail_url,
                language=_detect_language(labels),
                format=_detect_format(labels),
                raw={"movie_title": movie_title, "version": version, "labels": labels},
            )
        )
    deduped: list[SearchResult] = []
    seen: set[str] = set()
    for result in results:
        if result.result_id in seen:
            continue
        deduped.append(result)
        seen.add(result.result_id)
    return deduped


class SubhdClient:
    def __init__(self, http_client: httpx.Client | None = None, base_url: str = SUBHD_BASE) -> None:
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client or httpx.Client(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"},
        )

    def search(self, query: str) -> list[SearchResult]:
        url = f"{self.base_url}/search/{quote(query)}"
        response = self.http_client.get(url)
        response.raise_for_status()
        return parse_search_response(response.text, url)

    def download(self, result: SearchResult, target_dir) -> DownloadedFile:
        url = result.download_url or f"{self.base_url}/down/{result.result_id}"
        headers = {"Referer": result.detail_url or f"{self.base_url}/a/{result.result_id}"}
        response = self.http_client.get(url, headers=headers)
        response.raise_for_status()
        content_type = response.headers.get("Content-Type", "").lower()
        content_start = response.content[:200].lstrip().lower()
        if "text/html" in content_type or content_start.startswith(b"<!doctype html") or content_start.startswith(b"<html"):
            raise FixsubError(f"SubHD download returned HTML instead of a subtitle file: {url}")
        suffix = _download_suffix(response.content, result, response)
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_id = _safe_id(result.result_id)
        target_path = target_dir / f"subhd_{safe_id}{suffix}"
        target_path.write_bytes(response.content)
        return DownloadedFile(candidate_id=f"subhd_{safe_id}", provider="subhd", path=target_path, source_url=str(response.request.url))
```

- [ ] **Step 4: Add SubHD download tests**

Append to `tests/test_subhd.py`:

```python
def test_subhd_client_download_saves_archive(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://subhd.tv/down/kAqdvK"
        assert request.headers["Referer"] == "https://subhd.tv/a/kAqdvK"
        return httpx.Response(200, content=b"PK\x03\x04archive", request=request)

    client = SubhdClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = parse_search_response(SEARCH_HTML, "https://subhd.tv/search/Nell%201994")[0]

    downloaded = client.download(result, tmp_path)

    assert downloaded.path.name == "subhd_kAqdvK.zip"
    assert downloaded.path.read_bytes().startswith(b"PK")


def test_subhd_client_download_rejects_html_response(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>challenge</html>", headers={"Content-Type": "text/html"}, request=request)

    client = SubhdClient(http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    result = parse_search_response(SEARCH_HTML, "https://subhd.tv/search/Nell%201994")[0]

    with pytest.raises(FixsubError, match="SubHD download returned HTML"):
        client.download(result, tmp_path)
```

- [ ] **Step 5: Export SubHD provider**

Replace `fixsub/providers/__init__.py` with:

```python
from fixsub.providers.assrt_api import AssrtClient, parse_search_response as parse_assrt_search_response
from fixsub.providers.subhd import SubhdClient, parse_search_response as parse_subhd_search_response

__all__ = [
    "AssrtClient",
    "SubhdClient",
    "parse_assrt_search_response",
    "parse_subhd_search_response",
]
```

- [ ] **Step 6: Run SubHD tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_subhd.py -v
```

Expected: all SubHD tests pass.

- [ ] **Step 7: Commit**

```bash
git add fixsub/providers/subhd.py fixsub/providers/__init__.py tests/test_subhd.py
git commit -m "feat: add subhd provider"
```

## Task 5: Add Provider Registry and Multi-Provider CLI Orchestration

**Files:**
- Create: `fixsub/providers/registry.py`
- Modify: `fixsub/cli.py`
- Modify: `tests/test_cli_pipeline.py`

- [ ] **Step 1: Write failing tests for provider parsing and token behavior**

Add these tests to `tests/test_cli_pipeline.py`:

```python
def test_cli_accepts_subhd_provider_without_assrt_token(tmp_path: Path, monkeypatch) -> None:
    _write_video(tmp_path)
    subtitle = tmp_path / ".fixsub" / "candidates" / "subhd_kAqdvK.srt"
    subtitle.parent.mkdir(parents=True)
    subtitle.write_text("1\n00:02:00,000 --> 00:02:03,000\nHi\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ASSRT_TOKEN", raising=False)

    class FakeSubhdClient:
        def search(self, query: str) -> list[SearchResult]:
            return [
                SearchResult(
                    provider="subhd",
                    result_id="kAqdvK",
                    title="大地的女儿 Nell.1994.1080p.BluRay.x265-RARBG",
                    download_url="https://subhd.tv/down/kAqdvK",
                    detail_url="https://subhd.tv/a/kAqdvK",
                    language="bilingual",
                    format="srt",
                    raw={"version": "Nell.1994.1080p.BluRay.x265-RARBG"},
                )
            ]

        def download(self, result: SearchResult, target_dir: Path) -> DownloadedFile:
            return DownloadedFile(candidate_id="subhd_kAqdvK", provider="subhd", path=subtitle, source_url=result.download_url)

    monkeypatch.setattr("fixsub.providers.registry.SubhdClient", FakeSubhdClient)
    monkeypatch.setattr("fixsub.cli.extract_archive", lambda path, out_dir: [subtitle])
    monkeypatch.setattr(
        "fixsub.cli.normalize_to_utf8",
        lambda source, target: target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8") or target,
    )
    monkeypatch.setattr(
        "fixsub.cli.probe_video",
        lambda path: ProbeResult(duration_seconds=7200, audio_streams=[AudioStream(1, 0, "ac3", "eng", 6, True)], raw={}),
    )
    monkeypatch.setattr("fixsub.cli.score_alignment", lambda path, duration_seconds: AlignmentScore(0.92, []))

    result = CliRunner().invoke(app, ["--dry-run", "--providers", "subhd"])

    assert result.exit_code == 0
    assert "Dry run complete" in result.output
    metadata = _read_metadata(tmp_path)
    assert metadata["downloaded"][0]["provider"] == "subhd"


def test_cli_default_skips_assrt_when_token_missing_and_subhd_is_available(tmp_path: Path, monkeypatch) -> None:
    _write_video(tmp_path)
    subtitle = tmp_path / ".fixsub" / "candidates" / "subhd_kAqdvK.srt"
    subtitle.parent.mkdir(parents=True)
    subtitle.write_text("1\n00:02:00,000 --> 00:02:03,000\nHi\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ASSRT_TOKEN", raising=False)

    class FakeSubhdClient:
        def search(self, query: str) -> list[SearchResult]:
            return [
                SearchResult(
                    provider="subhd",
                    result_id="kAqdvK",
                    title="Nell.1994.1080p.BluRay.x265-RARBG",
                    language="bilingual",
                    format="srt",
                    raw={"version": "Nell.1994.1080p.BluRay.x265-RARBG"},
                )
            ]

        def download(self, result: SearchResult, target_dir: Path) -> DownloadedFile:
            return DownloadedFile(candidate_id="subhd_kAqdvK", provider="subhd", path=subtitle, source_url=result.download_url)

    monkeypatch.setattr("fixsub.providers.registry.SubhdClient", FakeSubhdClient)
    monkeypatch.setattr("fixsub.cli.extract_archive", lambda path, out_dir: [subtitle])
    monkeypatch.setattr(
        "fixsub.cli.normalize_to_utf8",
        lambda source, target: target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8") or target,
    )
    monkeypatch.setattr(
        "fixsub.cli.probe_video",
        lambda path: ProbeResult(duration_seconds=7200, audio_streams=[AudioStream(1, 0, "ac3", "eng", 6, True)], raw={}),
    )
    monkeypatch.setattr("fixsub.cli.score_alignment", lambda path, duration_seconds: AlignmentScore(0.92, []))

    result = CliRunner().invoke(app, ["--dry-run"])

    assert result.exit_code == 0
    assert "Dry run complete" in result.output
    assert "ASSRT skipped: ASSRT_TOKEN is required for ASSRT API access." in (tmp_path / ".fixsub" / "logs" / "fixsub.log").read_text(encoding="utf-8")
```

- [ ] **Step 2: Update the old unimplemented-provider test expectation**

Replace `test_cli_rejects_unimplemented_provider()` in `tests/test_cli_pipeline.py` with:

```python
def test_cli_rejects_unknown_provider(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(app, ["--providers", "opensubtitles"])

    assert result.exit_code != 0
    assert "Unsupported provider: opensubtitles" in result.output
```

- [ ] **Step 3: Run CLI provider tests to verify current behavior fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_cli_pipeline.py::test_cli_accepts_subhd_provider_without_assrt_token tests/test_cli_pipeline.py::test_cli_default_skips_assrt_when_token_missing_and_subhd_is_available tests/test_cli_pipeline.py::test_cli_rejects_unknown_provider -v
```

Expected: fail because `--providers subhd` is rejected and the CLI still hard-stops on missing `ASSRT_TOKEN`.

- [ ] **Step 4: Implement provider registry**

Create `fixsub/providers/registry.py`:

```python
from __future__ import annotations

import os
from typing import Protocol

from fixsub.errors import ProviderConfigError
from fixsub.models import DownloadedFile, SearchResult
from fixsub.providers.assrt_api import AssrtClient
from fixsub.providers.subhd import SubhdClient

SUPPORTED_PROVIDERS = {"assrt", "subhd"}
DEFAULT_PROVIDERS = ("assrt", "subhd")


class ProviderClient(Protocol):
    def search(self, query: str) -> list[SearchResult]:
        ...

    def download(self, result: SearchResult, target_dir) -> DownloadedFile:
        ...


def parse_providers(value: str) -> tuple[str, ...]:
    providers: list[str] = []
    for raw_provider in value.split(","):
        provider = raw_provider.strip().lower()
        if not provider:
            continue
        if provider not in SUPPORTED_PROVIDERS:
            raise ProviderConfigError(f"Unsupported provider: {provider}")
        if provider not in providers:
            providers.append(provider)
    return tuple(providers) or DEFAULT_PROVIDERS


def build_provider_clients(providers: tuple[str, ...]) -> tuple[dict[str, ProviderClient], list[str]]:
    clients: dict[str, ProviderClient] = {}
    warnings: list[str] = []
    if "assrt" in providers:
        token = os.environ.get("ASSRT_TOKEN", "").strip()
        if token:
            clients["assrt"] = AssrtClient(token=token)
        elif providers == ("assrt",):
            raise ProviderConfigError("ASSRT_TOKEN is required for ASSRT API access.")
        else:
            warnings.append("ASSRT skipped: ASSRT_TOKEN is required for ASSRT API access.")
    if "subhd" in providers:
        clients["subhd"] = SubhdClient()
    if not clients:
        raise ProviderConfigError("No subtitle providers are available.")
    return clients, warnings
```

- [ ] **Step 5: Wire registry into CLI**

In `fixsub/cli.py`, remove:

```python
import os
```

Replace:

```python
from fixsub.providers.assrt_api import AssrtClient
```

with:

```python
from fixsub.providers.registry import DEFAULT_PROVIDERS, ProviderClient, build_provider_clients, parse_providers
```

Delete `_parse_providers()` from `fixsub/cli.py`.

Change `_download_candidates()` signature and client lookup:

```python
def _download_candidates(
    clients: dict[str, ProviderClient],
    ranked_results: list[SearchResult],
    base_dir: Path,
    max_candidates: int,
) -> tuple[list[DownloadedFile], list[SubtitleCandidate]]:
```

Inside `_download_candidates()`, replace:

```python
            downloaded_file = client.download(result, workdirs.downloads)
```

with:

```python
            client = clients[result.provider]
            downloaded_file = client.download(result, workdirs.downloads)
```

In `run_pipeline()`, replace the token/client block:

```python
    token = os.environ.get("ASSRT_TOKEN", "").strip()
    if not token:
        message = "ASSRT_TOKEN is required for ASSRT API access."
        _write_pipeline_metadata(metadata_path, movie=movie, options=options, message=message)
        raise ProviderConfigError(message)
    client = AssrtClient(token=token)
```

with:

```python
    try:
        clients, provider_warnings = build_provider_clients(options.providers)
    except ProviderConfigError as exc:
        message = str(exc)
        _write_pipeline_metadata(metadata_path, movie=movie, options=options, message=message)
        raise
    for warning in provider_warnings:
        append_log(log_path, warning)
```

Replace the search loop:

```python
    for query in queries:
        try:
            search_results.extend(client.search(query))
            successful_searches += 1
        except Exception as exc:
            append_log(log_path, f"Search failed for {query}: {exc}")
```

with:

```python
    seen_results: set[tuple[str, str]] = set()
    for query in queries:
        for provider_name, client in clients.items():
            try:
                provider_results = client.search(query)
                successful_searches += 1
            except Exception as exc:
                append_log(log_path, f"Search failed for {provider_name}:{query}: {exc}")
                continue
            for result in provider_results:
                key = (result.provider, result.result_id)
                if key in seen_results:
                    continue
                search_results.append(result)
                seen_results.add(key)
```

Replace:

```python
        message = "ASSRT search failed for all queries."
```

with:

```python
        message = "Subtitle search failed for all providers and queries."
```

Replace:

```python
        message = "No ASSRT candidates found."
```

with:

```python
        message = "No subtitle candidates found."
```

Replace:

```python
    downloaded, candidates = _download_candidates(client, ranked_results, base_dir, options.max_candidates)
```

with:

```python
    downloaded, candidates = _download_candidates(clients, ranked_results, base_dir, options.max_candidates)
```

Replace:

```python
        message = "No downloadable or extractable ASSRT candidates."
```

with:

```python
        message = "No downloadable or extractable subtitle candidates."
```

In the Typer option for `providers`, replace:

```python
    providers: str = typer.Option("assrt", "--providers", help="Comma-separated providers. M1 supports assrt only."),
```

with:

```python
    providers: str = typer.Option(",".join(DEFAULT_PROVIDERS), "--providers", help="Comma-separated providers: assrt,subhd."),
```

In `RunOptions(...)`, replace:

```python
            providers=_parse_providers(providers),
```

with:

```python
            providers=parse_providers(providers),
```

- [ ] **Step 6: Update existing CLI tests for new messages**

In `tests/test_cli_pipeline.py`, update these assertions:

```python
assert "No subtitle candidates found." in result.output
assert metadata["message"] == "No subtitle candidates found."
```

```python
assert "Subtitle search failed" in result.output
assert metadata["message"] == "Subtitle search failed for all providers and queries."
```

```python
assert "No downloadable or extractable subtitle candidates." in result.output
assert metadata["message"] == "No downloadable or extractable subtitle candidates."
```

For tests that monkeypatch `fixsub.cli.AssrtClient`, replace the patch target with:

```python
monkeypatch.setattr("fixsub.providers.registry.AssrtClient", FakeClient)
```

- [ ] **Step 7: Run CLI pipeline tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_cli_pipeline.py -v
```

Expected: all CLI pipeline tests pass.

- [ ] **Step 8: Commit**

```bash
git add fixsub/providers/registry.py fixsub/cli.py tests/test_cli_pipeline.py
git commit -m "feat: orchestrate multiple subtitle providers"
```

## Task 6: Rank Provider Results with Provider-Specific Raw Fields

**Files:**
- Modify: `fixsub/ranking.py`
- Modify: `tests/test_decision_ranking_output.py`

- [ ] **Step 1: Write failing ranking test for SubHD version fields**

In `tests/test_decision_ranking_output.py`, extend the model and ranking imports:

```python
from fixsub.models import AlignmentScore, MovieInfo, SearchResult, SubtitleCandidate, SyncResult
from fixsub.ranking import rank_decisions, score_search_result
```

Append this test to `tests/test_decision_ranking_output.py`:

```python
def test_search_result_scoring_uses_subhd_version_raw_field() -> None:
    info = MovieInfo(
        path=Path("Nell.1994.WEB-DL.1080p.mkv"),
        stem="Nell.1994.WEB-DL.1080p",
        title="Nell",
        year="1994",
        source="WEB-DL",
        resolution="1080p",
        release_group=None,
    )
    result = SearchResult(
        provider="subhd",
        result_id="kAqdvK",
        title="大地的女儿",
        language="bilingual",
        format="srt",
        raw={"version": "Nell.1994.1080p.BluRay.x265-RARBG", "movie_title": "大地的女儿"},
    )

    scored = score_search_result(result, info)

    assert scored.pre_score >= 63
```

- [ ] **Step 2: Run ranking test to verify current behavior fails**

Run:

```bash
.venv/bin/python -m pytest tests/test_decision_ranking_output.py::test_search_result_scoring_uses_subhd_version_raw_field -v
```

Expected: fail because `ranking.py` currently only adds `raw["videoname"]` to the haystack, so the English title/year/resolution inside SubHD `version` are ignored.

- [ ] **Step 3: Implement raw field haystack helper**

In `fixsub/ranking.py`, add:

```python
RAW_HAYSTACK_FIELDS = ("videoname", "version", "movie_title", "filename", "native_name")


def _raw_haystack(result: SearchResult) -> str:
    parts = []
    for field in RAW_HAYSTACK_FIELDS:
        value = result.raw.get(field)
        if value:
            parts.append(str(value))
    return " ".join(parts)
```

Replace:

```python
    haystack = " ".join([result.title, str(result.raw.get("videoname") or "")]).lower()
```

with:

```python
    haystack = " ".join([result.title, _raw_haystack(result)]).lower()
```

- [ ] **Step 4: Run ranking tests**

Run:

```bash
.venv/bin/python -m pytest tests/test_decision_ranking_output.py -v
```

Expected: all ranking/output tests pass.

- [ ] **Step 5: Commit**

```bash
git add fixsub/ranking.py tests/test_decision_ranking_output.py
git commit -m "feat: score provider-specific release fields"
```

## Task 7: Documentation and Real Dry-Run Guidance

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README support matrix**

In `README.md`, replace the M1 support section with:

```markdown
## Provider Support

`fixsub` supports these subtitle sources:

- ASSRT API search with `ASSRT_TOKEN`
- ASSRT public web download fallback when the API search result downloads return 404
- SubHD public search through `https://subhd.tv/search/<query>`

The default provider list is:

```bash
fixsub --providers assrt,subhd
```

If `ASSRT_TOKEN` is missing, ASSRT is skipped when another provider is enabled. If you explicitly run `fixsub --providers assrt` without `ASSRT_TOKEN`, the command stops and asks for the token.
```

- [ ] **Step 2: Update usage examples**

In `README.md`, replace the provider usage example:

```markdown
Use only SubHD:

```bash
fixsub --providers subhd
```

Use ASSRT and SubHD:

```bash
fixsub --providers assrt,subhd
```

Preview a real movie folder:

```bash
export ASSRT_TOKEN="your-token"
fixsub --dry-run --max-candidates 20
```
```

- [ ] **Step 3: Add diagnostics note**

In `README.md`, add this under the output artifact list:

```markdown
Provider failures are recorded in `.fixsub/logs/fixsub.log`. ASSRT tokens are redacted before log lines are written.
```

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document subtitle providers"
```

## Task 8: Full Verification and Manual Acceptance

**Files:**
- Test-only task, no production files modified.

- [ ] **Step 1: Install dependencies in editable mode**

Run:

```bash
.venv/bin/python -m pip install -e ".[dev]"
```

Expected: command succeeds and installs `beautifulsoup4`.

- [ ] **Step 2: Run the full test suite**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -v
```

Expected: all tests pass.

- [ ] **Step 3: Verify CLI help includes both providers**

Run:

```bash
.venv/bin/fixsub --help
```

Expected: help text includes `--providers` with `assrt,subhd`.

- [ ] **Step 4: Verify SubHD-only dry run on the Nell folder**

From the real movie folder, run:

```bash
unset ASSRT_TOKEN
".venv/bin/fixsub" --dry-run --providers subhd --max-candidates 20
```

Expected: the command searches SubHD, selects audio through ffprobe, downloads at least one SubHD candidate if SubHD allows the current session to download, and either reports `Dry run complete` or logs a clear `SubHD download returned HTML instead of a subtitle file` provider failure.

- [ ] **Step 5: Verify combined provider dry run on the Nell folder**

From the real movie folder, run:

```bash
export ASSRT_TOKEN="your-rotated-token"
".venv/bin/fixsub" --dry-run --providers assrt,subhd --max-candidates 20
```

Expected: ASSRT search results that return API 404 try the public web fallback, SubHD candidates are also searched, and `.fixsub/logs/fixsub.log` contains no literal token value.

- [ ] **Step 6: Inspect metadata and logs**

Run from the movie folder:

```bash
python3 -m json.tool .fixsub/metadata/results.json
cat .fixsub/logs/fixsub.log
find .fixsub -maxdepth 3 -type f
```

Expected: `downloaded` contains `provider` values such as `assrt` or `subhd` when downloads succeed; `candidates` contains normalized subtitle paths when extraction succeeds; no log line exposes the ASSRT token.

## Self-Review

- Spec coverage: this plan covers ASSRT web fallback, SubHD source support, robust query generation informed by `movie_searcher`, token-safe logging, CLI multi-provider orchestration, docs, and real dry-run verification.
- Placeholder scan: no deferred implementation markers remain; each code-changing task includes concrete code snippets and commands.
- Type consistency: provider clients share `search(query) -> list[SearchResult]` and `download(result, target_dir) -> DownloadedFile`; `SearchResult.provider` is used as the client lookup key; new registry helpers are imported consistently into `fixsub/cli.py`.
