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
ALLOWED_DOWNLOAD_SUFFIXES = {".zip", ".rar", ".7z", ".srt", ".ass", ".ssa"}
HTML_PREFIXES = (b"<!doctype html", b"<html", b"<head", b"<script", b"<!--")


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
    stripped = content.lstrip(b"\xef\xbb\xbf\r\n\t ")
    if re.match(rb"\d+\s*\r?\n\d{2}:\d{2}:\d{2}[,.]\d{3}\s*-->", stripped):
        return ".srt"
    if stripped.startswith(b"[Script Info]") or stripped.startswith(b"[V4+ Styles]") or b"\nDialogue:" in stripped[:2048]:
        return ".ass"
    format_suffix = _allowed_suffix(f".{result.format.lstrip('.')}") if result.format else None
    return format_suffix or ".bin"


def _looks_like_html(content: bytes, content_type: str) -> bool:
    if "html" in content_type.lower():
        return True
    content_start = content[:512].lstrip(b"\xef\xbb\xbf\r\n\t ").lower()
    return content_start.startswith(HTML_PREFIXES)


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
        response = self._request_allowed(
            "POST",
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
        resolved_url = urljoin(api_url, download_url.strip())
        if not _is_allowed_subhd_url(resolved_url, self.base_url):
            raise FixsubError(f"SubHD download URL is not allowed: {resolved_url}")
        return resolved_url

    def download(self, result: SearchResult, target_dir) -> DownloadedFile:
        detail_url = result.detail_url or f"{self.base_url}/a/{result.result_id}"
        detail_response = self._request_allowed("GET", detail_url)
        detail_response.raise_for_status()

        gate_url = result.download_url or f"{self.base_url}/down/{result.result_id}"
        gate_response = self._request_allowed("GET", gate_url, headers={"Referer": detail_url})
        gate_response.raise_for_status()
        gate_content_type = gate_response.headers.get("Content-Type", "").lower()
        if not _looks_like_html(gate_response.content, gate_content_type):
            return self._save_download(gate_response, result, target_dir)

        download_url = self._api_download_url(result, gate_url)
        download_response = self._request_allowed("GET", download_url)
        download_response.raise_for_status()
        return self._save_download(download_response, result, target_dir)
