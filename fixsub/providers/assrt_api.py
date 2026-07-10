from __future__ import annotations

import re
from pathlib import PurePath
from typing import Any
from urllib.parse import unquote, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from httpx import HTTPStatusError

from fixsub.models import DownloadedFile, SearchResult

ASSRT_API_BASE = "https://api.assrt.net/v1"
ASSRT_WEB_BASE = "https://secure.assrt.net"
ALLOWED_DOWNLOAD_SUFFIXES = {".zip", ".rar", ".7z", ".srt", ".ass", ".ssa"}


def _detect_language(item: dict[str, Any]) -> str | None:
    text = " ".join(
        str(part)
        for part in [
            item.get("native_name"),
            item.get("videoname"),
            item.get("lang", {}).get("desc") if isinstance(item.get("lang"), dict) else item.get("lang"),
        ]
        if part
    )
    if any(token in text for token in ["简英", "双语", "中英", "简体&英文"]):
        return "bilingual"
    if any(token in text for token in ["简体", "简中", "中文字幕", "中文"]):
        return "zh-Hans"
    if any(token in text for token in ["繁体", "繁中"]):
        return "zh-Hant"
    return None


def _detect_format(item: dict[str, Any]) -> str | None:
    subtype = item.get("subtype")
    if isinstance(subtype, str) and subtype.lower() in {"ass", "ssa", "srt"}:
        return subtype.lower()
    text = " ".join(str(part) for part in [item.get("native_name"), item.get("filename")] if part)
    match = re.search(r"\.(ass|ssa|srt)(?:$|[?#])", text, re.IGNORECASE)
    if match:
        return match.group(1).lower()
    return None


def _sanitize_result_id(result_id: str) -> str:
    name = PurePath(result_id).name
    sanitized = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("._")
    return sanitized or "subtitle"


def _allowed_suffix(value: str | None) -> str | None:
    if not value:
        return None
    suffix = PurePath(unquote(value)).suffix.lower()
    return suffix if suffix in ALLOWED_DOWNLOAD_SUFFIXES else None


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


def _download_suffix(content: bytes, result: SearchResult, response: httpx.Response) -> str:
    if content.startswith(b"PK\x03\x04"):
        return ".zip"
    if content.startswith(b"Rar!\x1a\x07"):
        return ".rar"
    if content.startswith(b"7z\xbc\xaf\x27\x1c"):
        return ".7z"
    header_filename = _content_disposition_filename(response.headers.get("Content-Disposition"))
    for value in [
        header_filename,
        urlparse(result.download_url or str(response.request.url)).path,
        result.title,
        result.raw.get("filename") if isinstance(result.raw, dict) else None,
        result.raw.get("native_name") if isinstance(result.raw, dict) else None,
    ]:
        suffix = _allowed_suffix(str(value) if value else None)
        if suffix:
            return suffix
    format_suffix = _allowed_suffix(f".{result.format.lstrip('.')}") if result.format else None
    return format_suffix or ".bin"


def _iter_sub_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    sub = payload.get("sub")
    if not isinstance(sub, dict):
        return []
    subs = sub.get("subs")
    if not isinstance(subs, list):
        return []
    return [item for item in subs if isinstance(item, dict)]


def _detail_url(item: dict[str, Any]) -> str | None:
    detail_url = item.get("detail_url") or item.get("detailUrl")
    if detail_url:
        return str(detail_url)
    return None


def parse_search_response(payload: dict[str, Any]) -> list[SearchResult]:
    results: list[SearchResult] = []
    for item in _iter_sub_items(payload):
        result_id = str(item.get("id") or item.get("subid") or "")
        title = str(item.get("native_name") or item.get("videoname") or result_id)
        if not result_id or not title:
            continue
        download_url = item.get("download_url") or item.get("downloadUrl")
        results.append(
            SearchResult(
                provider="assrt",
                result_id=result_id,
                title=title,
                download_url=str(download_url) if download_url else None,
                detail_url=_detail_url(item),
                language=_detect_language(item),
                format=_detect_format(item),
                raw=item,
            )
        )
    return results


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
    candidates: list[tuple[int, str]] = []
    for url in _single_file_downloads(detail_html):
        candidates.append((0 if _is_chinese_download(url) else 1, url))
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        if "/download/" in href:
            candidates.append((2 if _is_chinese_download(href) else 3, href))

    deduped: list[str] = []
    seen: set[str] = set()
    for _, url in sorted(candidates, key=lambda candidate: candidate[0]):
        if url in seen:
            continue
        deduped.append(url)
        seen.add(url)
    return [urljoin(ASSRT_WEB_BASE, url) for url in deduped]


class AssrtClient:
    def __init__(self, token: str, http_client: httpx.Client | None = None, base_url: str = ASSRT_API_BASE) -> None:
        if not token:
            raise ValueError("ASSRT_TOKEN is required for ASSRT API access")
        self.token = token
        self.http_client = http_client or httpx.Client(timeout=20.0, follow_redirects=True)
        self.base_url = base_url.rstrip("/")

    def search(self, query: str) -> list[SearchResult]:
        response = self.http_client.get(f"{self.base_url}/sub/search", params={"token": self.token, "q": query})
        response.raise_for_status()
        return parse_search_response(response.json())

    def _download_response(self, url: str, params: dict[str, str] | None = None) -> httpx.Response:
        response = self.http_client.get(url, params=params)
        response.raise_for_status()
        return response

    def _is_api_download_url(self, url: str) -> bool:
        parsed = urlparse(url)
        base = urlparse(self.base_url)
        return parsed.netloc == base.netloc and parsed.path.startswith(f"{base.path.rstrip('/')}/sub/download")

    def _download_from_assrt_web(self, result: SearchResult) -> tuple[httpx.Response, str]:
        detail_url = _assrt_detail_url(result)
        detail_response = self._download_response(detail_url)
        for download_url in _assrt_web_download_urls(detail_response.text):
            response = self._download_response(download_url)
            return response, download_url
        raise RuntimeError(f"ASSRT detail page did not expose a download link: {detail_url}")

    def download(self, result: SearchResult, target_dir) -> DownloadedFile:
        url = result.download_url or f"{self.base_url}/sub/download"
        params = {"token": self.token}
        if not result.download_url:
            params["id"] = result.result_id
        try:
            response = self._download_response(url, params=params)
            source_url = str(response.request.url)
        except HTTPStatusError as exc:
            if exc.response.status_code != 404 or not self._is_api_download_url(url):
                raise
            response, source_url = self._download_from_assrt_web(result)
        suffix = _download_suffix(response.content, result, response)
        safe_id = _sanitize_result_id(result.result_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"assrt_{safe_id}{suffix}"
        target_path.write_bytes(response.content)
        return DownloadedFile(candidate_id=f"assrt_{safe_id}", provider="assrt", path=target_path, source_url=source_url)
