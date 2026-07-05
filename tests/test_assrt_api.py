import json
from pathlib import Path

import httpx
import pytest

from fixsub.models import MovieInfo
from fixsub.providers.assrt_api import AssrtClient, parse_search_response
from fixsub.ranking import score_search_result


def test_parse_search_response_extracts_results() -> None:
    payload = json.loads(Path("tests/fixtures/assrt_search.json").read_text(encoding="utf-8"))

    results = parse_search_response(payload)

    assert [result.result_id for result in results] == ["1001", "1002"]
    assert results[0].title == "Unforgiven 1992 WEB-DL bilingual.ass"
    assert results[0].language == "bilingual"
    assert results[0].format == "ass"
    assert results[0].download_url is not None


def test_search_result_scoring_prefers_matching_chinese_ass() -> None:
    payload = json.loads(Path("tests/fixtures/assrt_search.json").read_text(encoding="utf-8"))
    info = MovieInfo(
        path=Path("Unforgiven.1992.1080p.WEB-DL-GROUP.mkv"),
        stem="Unforgiven.1992.1080p.WEB-DL-GROUP",
        title="Unforgiven",
        year="1992",
        source="WEB-DL",
        resolution="1080p",
        release_group="GROUP",
    )
    results = parse_search_response(payload)

    scored = [score_search_result(result, info) for result in results]

    assert scored[0].pre_score > scored[1].pre_score


def test_client_requires_token() -> None:
    with pytest.raises(ValueError, match="ASSRT_TOKEN"):
        AssrtClient(token="")


def test_client_search_uses_token_and_query() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "token=secret-token" in str(request.url)
        assert "q=Unforgiven" in str(request.url)
        payload = json.loads(Path("tests/fixtures/assrt_search.json").read_text(encoding="utf-8"))
        return httpx.Response(200, json=payload)

    client = AssrtClient(token="secret-token", http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    results = client.search("Unforgiven")

    assert results[0].result_id == "1001"
