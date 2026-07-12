# SubHD Download API Compatibility Design

**Date:** 2026-07-13

## Goal

Restore reliable SubHD subtitle downloads after SubHD changed its public download flow, while preserving ASSRT support, the existing multi-provider search behavior, and strict download safety checks.

## Confirmed Root Cause

SubHD search still returns valid subtitle results, including an exact match for the tested release:

```text
Fried.Green.Tomatoes.1991.EXTENDED.1080p.BluRay.X264-AMIABLE
```

The existing provider performs a direct `GET /down/{sid}` and expects a subtitle file. SubHD now returns an HTML download page instead. That page establishes a temporary per-subtitle session and uses JavaScript to call:

```http
POST /api/sub/down
Content-Type: application/json

{"sid":"DzZLfP"}
```

A successful response has this shape:

```json
{
  "success": true,
  "msg": "验证通过",
  "pass": true,
  "url": "https://dl.subhd.me/2016/08/147239601922742.rar"
}
```

The current client rejects the HTML page correctly, but never performs the new API step, so every SubHD download fails before extraction.

## Scope

### In scope

- Support SubHD's current session-backed JSON download API.
- Preserve compatibility with the legacy direct-file `/down/{sid}` response.
- Preserve ASSRT unchanged.
- Preserve default aggregate search across `assrt,subhd`.
- Validate every API response, download URL, redirect, and downloaded payload.
- Produce actionable provider errors that are recorded in the existing log.
- Cover the behavior with focused automated tests and a real-movie dry run.

### Out of scope

- Browser automation or CAPTCHA solving.
- Login to SubHD.
- Scraping unrelated subtitle providers.
- Refactoring search ranking, ffsubsync scoring, or ASSRT behavior.
- Changing the meaning of `--max-candidates`.

## Search Behavior

The provider orchestration remains unchanged:

1. Generate queries from the full release name and parsed movie metadata.
2. Send every query to every enabled provider.
3. Merge results and deduplicate by `(provider, result_id)`.
4. Rank all results together.
5. Attempt at most `--max-candidates` results from the combined ranking.

With the default `--providers assrt,subhd`:

- ASSRT is queried when a token is available.
- SubHD is always queried.
- A failure from one provider is logged and does not prevent the other provider from continuing.
- If no ASSRT token is available, ASSRT is skipped and SubHD continues.

## SubHD Download Flow

`SubhdClient.download()` will use one persistent `httpx.Client` session and perform the following steps:

1. Validate and request the result detail URL, normally `/a/{sid}`. This establishes the temporary SubHD session cookie.
2. Request `/down/{sid}` with the detail page as the referrer.
3. If the response is a non-HTML subtitle/archive payload, treat it as a legacy direct download and continue to payload validation.
4. If the response is HTML, call `POST /api/sub/down` with `{"sid": sid}` in the same session.
5. Require a JSON object with `success is true`, `pass is true`, and a non-empty string `url`.
6. Validate the returned URL before requesting it.
7. Download the payload without forwarding SubHD session cookies to an unrelated host.
8. Validate every redirect target before following it.
9. Reject empty or HTML payloads.
10. Detect the file type using magic bytes first, then trusted filename/header metadata.
11. Save the file under `.fixsub/downloads/` using the existing safe candidate ID scheme.

The legacy response check comes before the API call so older SubHD deployments remain compatible without an extra API request.

## URL and Redirect Safety

The client must not fetch arbitrary URLs supplied by a remote API.

A URL is eligible only when all conditions are true:

- The scheme is HTTPS.
- The URL has no embedded username or password.
- The port is absent or is the default HTTPS port.
- The hostname is the configured SubHD host, one of the known SubHD-owned registrable domains, or a subdomain of one of those domains.

Initial known domains:

```text
subhd.tv
subhd.me
subhd.one
subhd.top
subhd.cc
subhdtw.com
subhd.com
```

The same validation is applied to each redirect hop, with a small fixed redirect limit. A redirect outside the allowlist fails before the destination is requested.

Tests using a custom `base_url` may download from that configured host so the production allowlist does not make the client untestable.

## Error Handling

Provider failures remain isolated to the affected candidate. Errors must identify the failing stage and include SubHD's safe human-readable message when available.

Examples include:

- `SubHD detail request failed`
- `SubHD download session page expired`
- `SubHD download API returned invalid JSON`
- `SubHD download API rejected the request: 时间过长本临时页面已经失效`
- `SubHD download API omitted a download URL`
- `SubHD download URL is not allowed`
- `SubHD download redirected outside allowed domains`
- `SubHD download returned HTML instead of a subtitle file`

The existing CLI continues trying other candidates and providers. If none succeeds, the existing final message remains stable and the detailed reasons remain available in `.fixsub/logs/fixsub.log`.

## Tests

Automated tests will be written before production changes and will cover:

1. New API flow: detail request, session page, JSON API call, and archive download.
2. Cookie continuity across detail, gate, and API requests.
3. Legacy direct archive response without an API call.
4. API `success: false` with the server message preserved.
5. Invalid or non-object JSON.
6. Missing or invalid `url`.
7. Non-HTTPS and non-SubHD download URLs rejected before request.
8. Allowed SubHD CDN subdomain accepted.
9. Redirect to a disallowed domain rejected before request.
10. Empty and HTML final responses rejected.
11. Existing filename and content-sniffing behavior remains green.
12. Full project test suite remains green.

After automated verification, run this against the real movie directory:

```bash
fixsub --dry-run --providers subhd --max-candidates 20
```

The acceptance run must show at least one downloaded/extracted candidate and must no longer fail with `SubHD download returned HTML instead of a subtitle file` for the exact AMIABLE result. A final subtitle is not written during the dry run.

## Acceptance Criteria

- ASSRT behavior and defaults are unchanged.
- The exact Extended AMIABLE SubHD candidate downloads through the current API.
- Legacy direct-file responses still work.
- Untrusted API URLs and redirects are never requested.
- HTML and empty downloads are never saved as subtitles.
- Provider failures remain isolated and actionable in logs.
- Focused tests, the complete test suite, and the real-movie dry run all pass.
