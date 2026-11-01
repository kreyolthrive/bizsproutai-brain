"""Fixed-origin web search with bounded spend and honest snippet provenance."""

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal
from urllib.parse import urlsplit

import httpx
from pydantic import Field, ValidationError

from lead_discovery import (
    Candidate,
    ContractModel,
    LeadBrief,
    LeadReview,
    LeadReviewRequest,
    build_queries,
    review_candidate,
    review_leads,
)

SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
MAX_RESPONSE_BYTES = 512 * 1024
RUN_TIMEOUT_SECONDS = 25


class LeadSearchRequest(ContractModel):
    brief: LeadBrief
    max_queries: int = Field(default=2, ge=1, le=3)
    results_per_query: int = Field(default=10, ge=1, le=10)


class QueryCoverage(ContractModel):
    query: str
    status: Literal["searched", "partial", "failed", "not_searched"]
    results_received: int = 0
    candidates_retained: int = 0
    invalid_results: int = 0
    error_code: str | None = None


class SearchEvidence(ContractModel):
    source_url: str
    title: str
    snippet: str
    retrieved_at: datetime
    evidence_kind: Literal["search_snippet"] = "search_snippet"
    publication_verified: Literal[False] = False


class LeadSearchResponse(ContractModel):
    contract_version: Literal["lead-search-v1"] = "lead-search-v1"
    run_id: str
    status: Literal["completed", "partial", "failed"]
    provider: Literal["brave_web"] = "brave_web"
    started_at: datetime
    finished_at: datetime
    queries: list[QueryCoverage]
    results: list[LeadReview]
    evidence: list[SearchEvidence]
    duplicates_removed: int
    coverage: str = (
        "Bounded web-index search only. Private groups and platform-wide coverage are not included. "
        "Snippets and source publication dates have not been independently verified."
    )


class SearchFailure(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


async def fetch_search(
    client: httpx.AsyncClient, key: str, query: str, freshness: str, count: int
) -> list[object]:
    """No redirects, URL overrides, retries, result-page fetches or raw error leakage."""
    try:
        async with client.stream(
            "GET",
            SEARCH_URL,
            headers={"X-Subscription-Token": key, "Accept": "application/json"},
            params={
                "q": query,
                "count": count,
                "freshness": freshness,
                "result_filter": "web",
                "text_decorations": "false",
                "spellcheck": "false",
            },
            follow_redirects=False,
            timeout=httpx.Timeout(10),
        ) as response:
            if response.status_code != 200:
                code = {
                    401: "provider_auth",
                    403: "provider_auth",
                    429: "provider_rate_limited",
                }.get(
                    response.status_code,
                    "provider_unavailable",
                )
                raise SearchFailure(code)
            content = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
                content.extend(chunk)
                if len(content) > MAX_RESPONSE_BYTES:
                    raise SearchFailure("provider_response_too_large")
            try:
                body = json.loads(content)
            except (ValueError, UnicodeError):
                raise SearchFailure("provider_invalid_response") from None
            if not isinstance(body, dict):
                raise SearchFailure("provider_invalid_response")
            web = body.get("web")
            # An omitted web field can legitimately mean no web matches.
            if web is None:
                if body.get("type") == "search":
                    return []
                raise SearchFailure("provider_invalid_response")
            if not isinstance(web, dict) or not isinstance(web.get("results"), list):
                raise SearchFailure("provider_invalid_response")
            return list(web["results"][:count])
    except httpx.TimeoutException:
        raise SearchFailure("provider_timeout") from None
    except httpx.HTTPError:
        raise SearchFailure("provider_unavailable") from None


def parse_result(raw: object, retrieved_at: datetime) -> tuple[Candidate, SearchEvidence] | None:
    if not isinstance(raw, dict):
        return None
    url, title, snippet = raw.get("url"), raw.get("title", ""), raw.get("description")
    if not isinstance(url, str) or not isinstance(title, str) or not isinstance(snippet, str):
        return None
    # Do not use titles as evidence of intent; titles are often generic or commercial.
    try:
        candidate = Candidate(
            source_url=url,
            source_name=(urlsplit(url).hostname or "Web result")[:100],
            text=snippet,
            published_at=None,
        )
    except (ValidationError, ValueError):
        return None
    return candidate, SearchEvidence(
        source_url=candidate.source_url,
        title=title[:500],
        snippet=candidate.text,
        retrieved_at=retrieved_at,
    )


async def discover_leads(
    request: LeadSearchRequest, api_key: str, client: httpx.AsyncClient
) -> LeadSearchResponse:
    if not api_key.strip():
        raise ValueError("Search provider is not configured")
    started = datetime.now(UTC)
    freshness = f"{(started - timedelta(days=request.brief.max_age_days)).date()}to{started.date()}"
    plan = build_queries(request.brief)
    selected = list(dict.fromkeys(plan))[: request.max_queries]
    ledger: list[QueryCoverage] = []
    candidates: list[Candidate] = []
    evidence: list[SearchEvidence] = []
    abort_code: str | None = None
    deadline = asyncio.get_running_loop().time() + RUN_TIMEOUT_SECONDS
    for query in selected:
        # Brave's documented query limit is 600 characters / 75 words.
        if len(query) > 600 or len(query.split()) > 75 or not query.strip(' "'):
            ledger.append(
                QueryCoverage(
                    query=query, status="not_searched", error_code="query_too_large_or_empty"
                )
            )
            continue
        remaining = deadline - asyncio.get_running_loop().time()
        if abort_code or remaining <= 0:
            ledger.append(
                QueryCoverage(
                    query=query, status="not_searched", error_code=abort_code or "run_timeout"
                )
            )
            continue
        try:
            rows = await asyncio.wait_for(
                fetch_search(client, api_key, query, freshness, request.results_per_query),
                timeout=remaining,
            )
            invalid = 0
            for row in rows:
                parsed = parse_result(row, datetime.now(UTC))
                if parsed is None:
                    invalid += 1
                    continue
                candidate, receipt = parsed
                candidates.append(candidate)
                evidence.append(receipt)
            ledger.append(
                QueryCoverage(
                    query=query,
                    status="partial" if invalid else "searched",
                    results_received=len(rows),
                    candidates_retained=len(rows) - invalid,
                    invalid_results=invalid,
                    error_code="invalid_results" if invalid else None,
                )
            )
        except (SearchFailure, TimeoutError) as exc:
            code = exc.code if isinstance(exc, SearchFailure) else "run_timeout"
            ledger.append(QueryCoverage(query=query, status="failed", error_code=code))
            if code in {"provider_auth", "provider_rate_limited", "run_timeout"}:
                abort_code = code
    # Include planned-but-budgeted-out queries explicitly, rather than implying full coverage.
    for query in dict.fromkeys(plan):
        if query not in selected:
            ledger.append(
                QueryCoverage(query=query, status="not_searched", error_code="query_budget")
            )
    reviewed = review_leads(LeadReviewRequest(brief=request.brief, candidates=candidates))
    retained_urls = {result.source_url for result in reviewed.results}
    receipts: dict[str, SearchEvidence] = {}
    ranked_receipts = sorted(
        zip(candidates, evidence, strict=True),
        key=lambda pair: review_candidate(request.brief, pair[0], started).score,
        reverse=True,
    )
    for _, receipt in ranked_receipts:
        if receipt.source_url in retained_urls:
            receipts.setdefault(receipt.source_url, receipt)
    any_success = any(entry.status in {"searched", "partial"} for entry in ledger)
    all_selected_succeeded = all(entry.status == "searched" for entry in ledger[: len(selected)])
    status: Literal["completed", "partial", "failed"] = "failed"
    if all_selected_succeeded and selected:
        status = "completed"
    elif any_success:
        status = "partial"
    return LeadSearchResponse(
        run_id=str(uuid.uuid4()),
        status=status,
        started_at=started,
        finished_at=datetime.now(UTC),
        queries=ledger,
        results=reviewed.results,
        evidence=list(receipts.values()),
        duplicates_removed=reviewed.duplicates_removed,
    )
