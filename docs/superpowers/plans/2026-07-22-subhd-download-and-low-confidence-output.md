# SubHD Download and Low-Confidence Output Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore SubHD downloads through its prepared-page protocol and always deliver the best usable Chinese subtitle, using a forced second `ffsubsync` pass when conservative synchronization explicitly refuses a low-quality alignment.

**Architecture:** Keep provider protocol handling in `fixsub/providers/subhd.py`, synchronization policy in `fixsub/sync.py`, confidence metadata in `fixsub/models.py` and `fixsub/decision.py`, and final-output policy in `fixsub/cli.py`. Each task follows red-green-refactor and commits an independently testable behavior before the next task begins.

**Tech Stack:** Python 3.11+, httpx, BeautifulSoup, Typer, pytest, ffsubsync CLI integration.

## Global Constraints

- Do not add a runtime dependency.
- A normal run writes a final subtitle whenever at least one downloaded, extracted, normalized, parseable Chinese candidate exists.
- `--dry-run` never writes a final subtitle.
- Conservative `ffsubsync` runs first with `--skip-sync-on-low-quality`; only its explicit low-quality diagnostic triggers one retry without that flag.
- A forced-pass failure falls back to the best original Chinese subtitle.
- Low confidence remains visible in console output and metadata; it is never presented as high confidence.
- High-confidence decisions remain ranked ahead of low-confidence decisions.
- Existing downloads, normalized candidates, synchronized files, logs, metadata, URL validation, and final-subtitle backup behavior remain intact.
- SubHD preparation URLs must use HTTPS, belong to an allowed SubHD domain or configured test host, have the exact path `/down/{sid}`, and contain no credentials, non-default port, query, or fragment.

---

### Task 1: Support SubHD Prepared Downloads

**Files:**
- Modify: `fixsub/providers/subhd.py:260-303`
- Test: `tests/test_subhd.py:303-680`

**Interfaces:**
- Consumes: `SubhdClient._request_stage(method, url, error_message, **kwargs) -> httpx.Response`, `_is_allowed_subhd_url(url, base_url) -> bool`, and `SearchResult.result_id`.
- Produces: `SubhdClient._prepare_download_url(result: SearchResult, detail_url: str) -> str`; `SubhdClient.download()` uses the returned prepared page URL before the existing download API.

- [ ] **Step 1: Write failing preparation and request-order tests**

Add a focused integration test whose transport handles the current five-stage request sequence:

```python
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
```

Add validation coverage for preparation payloads and URLs:

```python
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
```

Extend the existing stage-specific network test with:

```python
("prepare", "SubHD download preparation request failed")
```

Every existing `client.download(...)` MockTransport handler must respond to preparation before the gate. Insert this exact branch after its detail-page branch, using that test's configured base host:

```python
if request.url.path == "/api/sub/prepare-download":
    return httpx.Response(
        200,
        json={"success": True, "url": "/down/kAqdvK"},
        request=request,
    )
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_subhd.py::test_subhd_client_prepares_download_page_before_opening_gate \
  tests/test_subhd.py::test_subhd_prepare_download_rejects_invalid_responses \
  -v
```

Expected: FAIL because `SubhdClient` has no `_prepare_download_url`, and the integration sequence still goes directly from detail to gate.

- [ ] **Step 3: Implement preparation parsing and URL validation**

Add this method beside `_api_download_url`:

```python
def _prepare_download_url(self, result: SearchResult, detail_url: str) -> str:
    prepare_url = f"{self.base_url}/api/sub/prepare-download"
    response = self._request_stage(
        "POST",
        prepare_url,
        "SubHD download preparation request failed",
        json={"sid": result.result_id},
        headers={"Referer": detail_url},
    )
    try:
        payload = response.json()
    except ValueError as exc:
        raise FixsubError("SubHD download preparation returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise FixsubError("SubHD download preparation returned invalid JSON")
    if payload.get("success") is not True:
        message = _sanitize_rejection_message(payload.get("msg"))
        raise FixsubError(f"SubHD download preparation rejected the request: {message}")
    prepared_url = payload.get("url")
    if not isinstance(prepared_url, str) or not prepared_url.strip():
        raise FixsubError("SubHD download preparation omitted a prepared download URL")
    resolved_url = urljoin(prepare_url, prepared_url.strip())
    if not _is_allowed_subhd_url(resolved_url, self.base_url):
        raise FixsubError(f"SubHD prepared download URL is not allowed: {resolved_url}")
    parsed = urlparse(resolved_url)
    expected_path = f"/down/{quote(result.result_id, safe='')}"
    if parsed.path != expected_path or parsed.query or parsed.fragment:
        raise FixsubError(f"SubHD prepared download URL does not match subtitle: {resolved_url}")
    return resolved_url
```

Change `download()` so the detail request is followed by preparation and then the prepared gate:

```python
def download(self, result: SearchResult, target_dir) -> DownloadedFile:
    detail_url = result.detail_url or f"{self.base_url}/a/{result.result_id}"
    self._request_stage("GET", detail_url, "SubHD detail request failed")

    gate_url = self._prepare_download_url(result, detail_url)
    gate_response = self._request_stage(
        "GET",
        gate_url,
        "SubHD download page request failed",
        headers={"Referer": detail_url},
    )
    gate_content_type = gate_response.headers.get("Content-Type", "").lower()
    if not _looks_like_html(gate_response.content, gate_content_type):
        return self._save_download(gate_response, result, target_dir)

    download_url = self._api_download_url(result, gate_url)
    download_response = self._request_stage("GET", download_url, "SubHD subtitle file request failed")
    return self._save_download(download_response, result, target_dir)
```

- [ ] **Step 4: Run all SubHD tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_subhd.py -v
```

Expected: all SubHD tests PASS, including preparation-stage errors, URL rejection, legacy direct-archive response after a prepared gate, redirects, and final content validation.

- [ ] **Step 5: Commit Task 1**

```bash
git add fixsub/providers/subhd.py tests/test_subhd.py
git commit -m "fix: prepare current SubHD downloads"
```

---

### Task 2: Retry Explicit Low-Quality Synchronization

**Files:**
- Modify: `fixsub/models.py:104-112`
- Modify: `fixsub/sync.py:22-80`
- Modify: `fixsub/decision.py:10-52`
- Test: `tests/test_sync.py`
- Test: `tests/test_decision_ranking_output.py:21-160`
- Test: `tests/test_paths_models.py:95-126`

**Interfaces:**
- Consumes: `run_ffsubsync(video_path, subtitle_path, output_path, audio_stream) -> SyncResult` and the existing ffsubsync diagnostic strings.
- Produces: `SyncResult.forced_low_quality: bool = False`; `run_ffsubsync` performs at most two subprocess calls; `decide_candidate_version` preserves forced synchronization as selected but marks it low-confidence.

- [ ] **Step 1: Write failing forced-retry tests**

Replace the existing test that expects a low-quality result to fail with a two-call success test:

```python
def test_run_ffsubsync_retries_low_quality_without_skip_flag(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("fixsub.sync.shutil.which", lambda command: "/usr/bin/ffs")
    output = tmp_path / "synced" / "candidate.srt"
    calls: list[list[str]] = []

    def fake_run(command: list[str], capture_output: bool, text: bool) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        output.write_text("forced subtitle", encoding="utf-8")
        diagnostics = "score: 12.0\noffset seconds: 31.730\nframerate scale factor: 1.043\n"
        if "--skip-sync-on-low-quality" in command:
            diagnostics += "low-quality alignment; leaving subtitles unmodified\n"
        return subprocess.CompletedProcess(command, 0, stdout=diagnostics, stderr="")

    monkeypatch.setattr("fixsub.sync.subprocess.run", fake_run)

    result = run_ffsubsync(
        video_path=tmp_path / "movie.mkv",
        subtitle_path=tmp_path / "candidate.srt",
        output_path=output,
        audio_stream="a:4",
    )

    assert len(calls) == 2
    assert "--skip-sync-on-low-quality" in calls[0]
    assert "--skip-sync-on-low-quality" not in calls[1]
    assert result.succeeded is True
    assert result.output_path == output
    assert result.forced_low_quality is True
    assert result.offset_seconds == 31.73
```

Add a forced-pass failure test:

```python
def test_run_ffsubsync_forced_retry_failure_removes_output(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("fixsub.sync.shutil.which", lambda command: "/usr/bin/ffs")
    output = tmp_path / "synced" / "candidate.srt"
    calls = 0

    def fake_run(command: list[str], capture_output: bool, text: bool) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        output.write_text("temporary", encoding="utf-8")
        if calls == 1:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=(
                    "score: 12.0\noffset seconds: 3.0\nframerate scale factor: 1.0\n"
                    "low-quality alignment; leaving subtitles unmodified\n"
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="forced failure")

    monkeypatch.setattr("fixsub.sync.subprocess.run", fake_run)

    result = run_ffsubsync(tmp_path / "movie.mkv", tmp_path / "candidate.srt", output, "a:0")

    assert calls == 2
    assert result.succeeded is False
    assert result.error == "forced failure"
    assert result.forced_low_quality is True
    assert not output.exists()
```

Add decision coverage:

```python
def test_decision_selects_forced_sync_and_marks_it_low_confidence(tmp_path: Path) -> None:
    candidate = make_candidate(tmp_path)
    synced = tmp_path / "candidate.synced.ass"
    synced.write_text("[Events]\n", encoding="utf-8")

    decision = decide_candidate_version(
        candidate=candidate,
        original_score=AlignmentScore(0.90, []),
        sync_result=SyncResult(
            attempted=True,
            succeeded=True,
            output_path=synced,
            forced_low_quality=True,
        ),
        synced_score=AlignmentScore(0.90, []),
    )

    assert decision.selected_version == "synced"
    assert decision.selected_path == synced
    assert decision.is_poor is True
    assert decision.decision_reason == "ffsubsync forced a low-quality audio alignment."
```

- [ ] **Step 2: Run focused tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_sync.py::test_run_ffsubsync_retries_low_quality_without_skip_flag \
  tests/test_sync.py::test_run_ffsubsync_forced_retry_failure_removes_output \
  tests/test_decision_ranking_output.py::test_decision_selects_forced_sync_and_marks_it_low_confidence \
  -v
```

Expected: FAIL because `SyncResult` has no `forced_low_quality` field and `run_ffsubsync` does not retry.

- [ ] **Step 3: Extend synchronization metadata without breaking positional callers**

Append the field at the end of `SyncResult` so existing positional construction retains its meaning:

```python
@dataclass(frozen=True)
class SyncResult:
    attempted: bool
    succeeded: bool
    output_path: Path | None = None
    error: str | None = None
    ffsubsync_score: float | None = None
    offset_seconds: float | None = None
    framerate_scale: float | None = None
    forced_low_quality: bool = False
```

- [ ] **Step 4: Implement a narrowly triggered two-pass subprocess loop**

Build the conservative command once, run it, and only remove the skip flag after the existing low-quality diagnostic:

```python
LOW_QUALITY_MARKERS = ("low-quality alignment", "leaving subtitles unmodified")


def _is_low_quality(diagnostics: str) -> bool:
    lowered = diagnostics.lower()
    return any(marker in lowered for marker in LOW_QUALITY_MARKERS)
```

Within `run_ffsubsync`, use this control flow while preserving the existing nonzero-exit, missing-output, metric, and `OSError` result shapes:

```python
conservative_command = [
    "ffs",
    str(video_path),
    "--reference-stream",
    audio_stream,
    "--skip-sync-on-low-quality",
    "-i",
    str(subtitle_path),
    "-o",
    str(output_path),
]
commands = [conservative_command]
forced_low_quality = False

for command in commands:
    output_path.unlink(missing_ok=True)
    try:
        result = subprocess.run(command, capture_output=True, text=True)
    except OSError as exc:
        return SyncResult(
            attempted=True,
            succeeded=False,
            output_path=None,
            error=str(exc),
            forced_low_quality=forced_low_quality,
        )
    diagnostics = "\n".join(part for part in [result.stdout, result.stderr] if part)
    metrics = {
        "ffsubsync_score": _metric(diagnostics, "score"),
        "offset_seconds": _metric(diagnostics, "offset seconds"),
        "framerate_scale": _metric(diagnostics, "framerate scale factor"),
    }
    if not forced_low_quality and result.returncode == 0 and _is_low_quality(diagnostics):
        output_path.unlink(missing_ok=True)
        forced_low_quality = True
        commands.append([part for part in conservative_command if part != "--skip-sync-on-low-quality"])
        continue
    if result.returncode != 0:
        output_path.unlink(missing_ok=True)
        return SyncResult(
            attempted=True,
            succeeded=False,
            output_path=None,
            error=result.stderr.strip() or result.stdout.strip(),
            forced_low_quality=forced_low_quality,
            **metrics,
        )
    if not output_path.exists():
        return SyncResult(
            attempted=True,
            succeeded=False,
            output_path=None,
            error="ffsubsync exited successfully without writing an output file",
            forced_low_quality=forced_low_quality,
            **metrics,
        )
    if any(value is None for value in metrics.values()):
        output_path.unlink(missing_ok=True)
        return SyncResult(
            attempted=True,
            succeeded=False,
            output_path=None,
            error="ffsubsync output did not include complete alignment metrics",
            forced_low_quality=forced_low_quality,
            **metrics,
        )
    return SyncResult(
        attempted=True,
        succeeded=True,
        output_path=output_path,
        error=None,
        forced_low_quality=forced_low_quality,
        **metrics,
    )
```

- [ ] **Step 5: Preserve forced synchronization as selected but low-confidence**

In `decide_candidate_version`, use a distinct reason and include the forced flag in confidence classification:

```python
if synced_is_usable:
    selected_version = "synced"
    selected_path = sync_result.output_path
    selected_score = synced_score.score
    if sync_result.forced_low_quality:
        reason = "ffsubsync forced a low-quality audio alignment."
    else:
        reason = "ffsubsync audio alignment succeeded."
```

Replace the final confidence expression with:

```python
is_poor = (
    sync_result.forced_low_quality
    or usable_score < POOR_ALIGNMENT
    or (sync_result.attempted and not synced_is_usable)
)
```

- [ ] **Step 6: Run synchronization, decision, and model tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_sync.py \
  tests/test_decision_ranking_output.py \
  tests/test_paths_models.py \
  -v
```

Expected: all selected tests PASS. Normal successful synchronization still performs one subprocess call and has `forced_low_quality=False`; only explicit low-quality diagnostics perform two calls.

- [ ] **Step 7: Commit Task 2**

```bash
git add fixsub/models.py fixsub/sync.py fixsub/decision.py tests/test_sync.py tests/test_decision_ranking_output.py tests/test_paths_models.py
git commit -m "fix: force low-confidence subtitle synchronization"
```

---

### Task 3: Deliver the Best Usable Candidate and Document Warnings

**Files:**
- Modify: `fixsub/cli.py:236-270`
- Test: `tests/test_cli_pipeline.py`
- Modify: `README.md:70-105,135-165`
- Modify: `README.zh-CN.md:70-105,135-165`

**Interfaces:**
- Consumes: ranked `CandidateDecision` values with `is_poor`, `selected_version`, `selected_score`, and `sync_result.forced_low_quality` from Task 2.
- Produces: low-confidence normal runs write `final_output`; low-confidence dry runs do not; console and metadata clearly report forced synchronization or original fallback.

- [ ] **Step 1: Write failing low-confidence output tests**

Add a pipeline test following the existing fake-client setup that forces a poor synchronized decision and asserts final output is written:

```python
def test_cli_applies_forced_low_confidence_synced_candidate(tmp_path: Path, monkeypatch) -> None:
    video = _write_video(tmp_path)
    subtitle = tmp_path / ".fixsub" / "candidates" / "subhd_forced.srt"
    subtitle.parent.mkdir(parents=True)
    subtitle.write_text("1\n00:00:01,000 --> 00:00:02,000\n字幕\n", encoding="utf-8")
    synced = tmp_path / ".fixsub" / "synced" / "subhd_forced.synced.srt"
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ASSRT_TOKEN", raising=False)

    class FakeSubhdClient:
        def search(self, query: str) -> list[SearchResult]:
            return [SearchResult(provider="subhd", result_id="forced", title="Movie 1992 中文字幕", language="zh-Hans", format="srt")]

        def download(self, result: SearchResult, target_dir: Path) -> DownloadedFile:
            return DownloadedFile("subhd_forced", "subhd", subtitle, result.download_url)

    monkeypatch.setattr("fixsub.providers.registry.SubhdClient", FakeSubhdClient)
    monkeypatch.setattr("fixsub.cli.extract_archive", lambda path, out_dir: [subtitle])
    monkeypatch.setattr("fixsub.cli.normalize_to_utf8", lambda source, target: target)
    monkeypatch.setattr(
        "fixsub.cli.probe_video",
        lambda path: ProbeResult(7200, [AudioStream(1, 0, "ac3", "eng", 6, True)], {}),
    )
    monkeypatch.setattr("fixsub.cli.score_alignment", lambda path, duration: AlignmentScore(0.40, ["low timeline coverage"]))

    def fake_sync(video_path: Path, subtitle_path: Path, output_path: Path, audio_stream: str) -> SyncResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(subtitle_path.read_text(encoding="utf-8"), encoding="utf-8")
        return SyncResult(
            attempted=True,
            succeeded=True,
            output_path=output_path,
            ffsubsync_score=12.0,
            offset_seconds=8.4,
            framerate_scale=1.0,
            forced_low_quality=True,
        )

    monkeypatch.setattr("fixsub.cli.run_ffsubsync", fake_sync)

    result = CliRunner().invoke(app, ["--providers", "subhd"])

    final_path = video.with_name(f"{video.stem}.zh.srt")
    assert result.exit_code == 0
    assert final_path.exists()
    assert "Applied low-confidence subtitle" in result.output
    assert "forced synchronization" in result.output
    metadata = _read_metadata(tmp_path)
    assert metadata["final_output"] == str(final_path)
    assert metadata["decisions"][0]["is_poor"] is True
    assert metadata["decisions"][0]["sync_result"]["forced_low_quality"] is True
```

Add an original-fallback test using `SyncResult(attempted=True, succeeded=False, error="sync failed")`, asserting that the normalized candidate is written and output contains `original fallback`.

Add a dry-run variant with the same forced synchronization result:

```python
result = CliRunner().invoke(app, ["--dry-run", "--providers", "subhd"])
assert result.exit_code == 0
assert "Dry run complete" in result.output
assert "low-confidence" in result.output.lower()
assert "forced synchronization" in result.output
assert not video.with_name(f"{video.stem}.zh.srt").exists()
assert _read_metadata(tmp_path)["final_output"] is None
```

Keep the existing test for zero decisions unchanged: it must still produce `No downloadable or extractable subtitle candidates.` and no final subtitle.

- [ ] **Step 2: Run the focused CLI tests and verify RED**

Run:

```bash
.venv/bin/python -m pytest \
  tests/test_cli_pipeline.py::test_cli_applies_forced_low_confidence_synced_candidate \
  tests/test_cli_pipeline.py::test_cli_applies_original_when_sync_fails \
  tests/test_cli_pipeline.py::test_cli_dry_run_reports_forced_low_confidence_without_writing \
  -v
```

Expected: FAIL because `run_pipeline` still blocks every `best.is_poor` result from `write_final_subtitle`.

- [ ] **Step 3: Replace the low-confidence veto with warned output**

Add a small outcome label helper above `run_pipeline`:

```python
def _selection_label(decision: CandidateDecision) -> str:
    if decision.sync_result.forced_low_quality and decision.selected_version == "synced":
        return "forced synchronization"
    if decision.selected_version == "original" and decision.sync_result.attempted:
        return "original fallback"
    if decision.selected_version == "synced":
        return "synchronization"
    return "original subtitle"
```

Replace the final output branch with:

```python
selection_label = _selection_label(best)
final_output = None
if options.dry_run:
    confidence = "Low-confidence " if best.is_poor else ""
    message = (
        f"Dry run complete. {confidence}best candidate: {best.candidate.candidate_id} "
        f"({selection_label}, timeline {best.selected_score:.2f})."
    )
else:
    final_output = write_final_subtitle(best.selected_path, video_path, options.lang, workdirs.original)
    if best.is_poor:
        message = (
            f"Applied low-confidence subtitle ({selection_label}, timeline {best.selected_score:.2f}): "
            f"{final_output}"
        )
    else:
        message = f"Applied subtitle: {final_output}"
```

Do not change the preceding `if not decisions` hard stop or ranking order.

- [ ] **Step 4: Run all CLI pipeline tests and verify GREEN**

Run:

```bash
.venv/bin/python -m pytest tests/test_cli_pipeline.py -v
```

Expected: all CLI pipeline tests PASS. Update only old assertions that intentionally encoded the removed low-confidence veto; retain every no-candidate and dry-run safety assertion.

- [ ] **Step 5: Update English and Chinese documentation**

Replace statements that say poor synchronization prevents output with the new best-effort contract. The English text must state:

```markdown
`fixsub` first asks `ffsubsync` to skip low-quality alignments. If that conservative pass explicitly refuses the alignment, `fixsub` retries once in forced mode. When at least one usable Chinese candidate exists, the best candidate is written even if confidence remains low; the console and metadata identify forced synchronization or original fallback. A hard stop remains when no candidate can be downloaded, extracted, parsed, or accepted as Chinese.
```

The Chinese text must state:

```markdown
`fixsub` 会先要求 `ffsubsync` 跳过低质量对齐；如果保守同步明确拒绝该对齐，则自动以强制模式重试一次。只要至少存在一个可用的中文字幕候选项，即使置信度仍然较低，也会写入排名最高的候选项；控制台和元数据会明确标记强制同步或原字幕回退。只有在没有候选项能够下载、解压、解析或通过中文内容检查时才会停止且不写入字幕。
```

Document that SubHD now uses its prepared-download flow and retain the artifact paths under `.fixsub/`.

- [ ] **Step 6: Run the complete test suite and documentation checks**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests PASS with zero failures.

Run:

```bash
git diff --check
python3 -m build
```

Expected: `git diff --check` exits 0 and both source distribution and wheel build successfully.

- [ ] **Step 7: Commit Task 3**

```bash
git add fixsub/cli.py tests/test_cli_pipeline.py README.md README.zh-CN.md
git commit -m "fix: deliver low-confidence subtitle repairs"
```

---

## Final Verification

After all three task reviews are clean:

1. Run `.venv/bin/python -m pytest -q` and confirm zero failures.
2. Run `python3 -m build` and confirm both distribution formats are produced.
3. Run `git diff --check` and confirm no whitespace errors.
4. Perform a live SubHD protocol probe for a current public subtitle result: detail `GET`, preparation `POST`, gate `GET`, download API `POST`, final file `GET`. Save any downloaded file only under `/tmp`.
5. Run a full `fixsub --dry-run --providers subhd` inside an available movie folder if its path is available; otherwise report that the deterministic protocol probe and automated pipeline tests cover the behavior.
