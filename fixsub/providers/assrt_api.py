from __future__ import annotations

import re
from pathlib import PurePath
from typing import Any

import httpx

from fixsub.models import DownloadedFile, SearchResult

ASSRT_API_BASE = "https://api.assrt.net/v1"


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


def _download_suffix(content: bytes, result_format: str | None) -> str:
    if content.startswith(b"PK\x03\x04"):
        return ".zip"
    if content.startswith(b"Rar!\x1a\x07"):
        return ".rar"
    if content.startswith(b"7z\xbc\xaf\x27\x1c"):
        return ".7z"
    return "." + (result_format or "bin").lstrip(".")


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

    def download(self, result: SearchResult, target_dir) -> DownloadedFile:
        url = result.download_url or f"{self.base_url}/sub/download"
        params = {"token": self.token}
        if not result.download_url:
            params["id"] = result.result_id
        response = self.http_client.get(url, params=params)
        response.raise_for_status()
        suffix = _download_suffix(response.content, result.format)
        safe_id = _sanitize_result_id(result.result_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"assrt_{safe_id}{suffix}"
        target_path.write_bytes(response.content)
        return DownloadedFile(candidate_id=f"assrt_{safe_id}", provider="assrt", path=target_path, source_url=url)
