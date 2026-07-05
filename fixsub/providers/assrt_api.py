from __future__ import annotations

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
    text = " ".join(str(part) for part in [item.get("subtype"), item.get("native_name"), item.get("filename")] if part)
    lowered = text.lower()
    for ext in ("ass", "ssa", "srt"):
        if ext in lowered:
            return ext
    return None


def parse_search_response(payload: dict[str, Any]) -> list[SearchResult]:
    raw_items = payload.get("sub", {}).get("subs", [])
    results: list[SearchResult] = []
    for item in raw_items:
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
                detail_url=f"{ASSRT_API_BASE}/sub/detail",
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
        suffix = "." + (result.format or "bin")
        target_path = target_dir / f"assrt_{result.result_id}{suffix}"
        target_path.write_bytes(response.content)
        return DownloadedFile(candidate_id=f"assrt_{result.result_id}", provider="assrt", path=target_path, source_url=url)
