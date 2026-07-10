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
