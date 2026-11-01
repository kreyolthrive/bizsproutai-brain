import asyncio
import json

import httpx
import pytest

from lead_discovery import LeadBrief
from lead_search import MAX_RESPONSE_BYTES, LeadSearchRequest, discover_leads


def request(**overrides):
    return LeadSearchRequest(
        brief=LeadBrief(
            offer="Cleaning services",
            offer_type="service",
            offer_terms=["cleaner", "cleaning"],
            buyer_phrases=["looking for", "need"],
            location_terms=["Miami"],
        ),
        **overrides,
    )


def row(**overrides):
    return {
        "url": "https://community.example/posts/1",
        "title": "Recommendation request",
        "description": "Looking for a cleaner in Miami",
        "age": "1 hour ago",
        **overrides,
    }


def search(handler, **overrides):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await discover_leads(request(**overrides), "private-test-key", client)

    return asyncio.run(run())


def test_fixed_origin_secret_header_and_bounded_queries():
    calls = []

    def handler(req):
        calls.append(req)
        assert str(req.url).startswith("https://api.search.brave.com/res/v1/web/search?")
        assert req.headers["X-Subscription-Token"] == "private-test-key"
        assert "private-test-key" not in str(req.url)
        assert req.url.params["count"] == "10"
        assert req.url.params["spellcheck"] == "false"
        return httpx.Response(200, json={"web": {"results": [row()]}})

    result = search(handler)
    assert len(calls) == 2
    assert result.status == "completed"
    assert len(result.results) == 1
    assert result.duplicates_removed == 1
    assert result.results[0].priority == "normal"  # relative age is not a verified date
    assert result.results[0].published_at is None
    assert result.evidence[0].publication_verified is False
    assert result.evidence[0].evidence_kind == "search_snippet"
    assert sum(q.error_code == "query_budget" for q in result.queries) == 2


@pytest.mark.parametrize(
    "status,code", [(401, "provider_auth"), (403, "provider_auth"), (429, "provider_rate_limited")]
)
def test_auth_and_rate_failure_stop_remaining_spend(status, code):
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(status, text="secret provider details")

    result = search(handler, max_queries=3)
    assert len(calls) == 1
    assert result.status == "failed"
    assert result.results == []
    assert result.queries[0].error_code == code
    assert result.queries[1].status == "not_searched"
    assert "secret provider details" not in result.model_dump_json()


def test_redirect_is_not_followed():
    calls = []

    def handler(req):
        calls.append(req)
        return httpx.Response(302, headers={"location": "http://169.254.169.254/metadata"})

    assert search(handler, max_queries=1).status == "failed"
    assert len(calls) == 1


def test_partial_success_survives_one_provider_failure():
    calls = []

    def handler(req):
        calls.append(req)
        if len(calls) == 1:
            return httpx.Response(200, json={"web": {"results": [row()]}})
        return httpx.Response(503, text="private diagnostics")

    result = search(handler)
    assert result.status == "partial"
    assert len(result.results) == 1
    assert result.queries[1].error_code == "provider_unavailable"


def test_invalid_rows_not_hidden_as_clean_success():
    result = search(
        lambda req: httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        row(),
                        row(url="http://localhost/x"),
                        row(description=123),
                        "bad row",
                    ]
                }
            },
        ),
        max_queries=1,
    )
    assert result.status == "partial"
    assert result.queries[0].invalid_results == 3
    assert len(result.results) == 1


@pytest.mark.parametrize("body", ["not json", "[]", '{"web": {"results": "bad"}}'])
def test_malformed_provider_payload(body):
    result = search(lambda req: httpx.Response(200, text=body), max_queries=1)
    assert result.status == "failed"
    assert result.queries[0].error_code == "provider_invalid_response"


def test_oversized_response_refused():
    result = search(
        lambda req: httpx.Response(200, content=b" " * (MAX_RESPONSE_BYTES + 1)), max_queries=1
    )
    assert result.queries[0].error_code == "provider_response_too_large"


def test_timeout_reported_without_exception_detail():
    def handler(req):
        raise httpx.ReadTimeout("private-test-key", request=req)

    result = search(handler, max_queries=1)
    assert result.queries[0].error_code == "provider_timeout"
    assert "private-test-key" not in result.model_dump_json()


def test_empty_web_results_are_not_an_error_or_fake_leads():
    result = search(lambda req: httpx.Response(200, json={"type": "search"}), max_queries=1)
    assert result.status == "completed"
    assert result.results == []
    assert result.evidence == []


def test_receipt_matches_best_ranked_duplicate():
    result = search(
        lambda req: httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        row(description="Cleaning tips", title="Generic article"),
                        row(title="Actual request"),
                    ]
                }
            },
        ),
        max_queries=1,
    )
    assert len(result.results) == 1
    assert result.results[0].score == 85
    assert result.evidence[0].title == "Actual request"
    assert result.evidence[0].snippet == "Looking for a cleaner in Miami"


def test_titles_cannot_manufacture_buying_intent():
    result = search(
        lambda req: httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        row(
                            title="Looking for a cleaner in Miami",
                            description="Our company sells cleaning supplies",
                        ),
                    ]
                }
            },
        ),
        max_queries=1,
    )
    assert result.results[0].score == 0


def test_provider_result_count_is_capped_even_if_provider_ignores_it():
    result = search(
        lambda req: httpx.Response(
            200,
            json={
                "web": {
                    "results": [
                        row(
                            url=f"https://community.example/{i}",
                            description=f"Looking for cleaner in Miami {i}",
                        )
                        for i in range(50)
                    ]
                }
            },
        ),
        max_queries=1,
        results_per_query=2,
    )
    assert len(result.results) == 2


def test_query_limits_checked_before_provider_call():
    query_request = request(max_queries=1)
    query_request.brief.offer_terms = [" ".join(["word"] * 76)]
    calls = []

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda req: calls.append(req))
        ) as client:
            return await discover_leads(query_request, "test", client)

    result = asyncio.run(run())
    assert calls == []
    assert result.queries[0].status == "not_searched"


def test_receipts_and_outcomes_serialize_without_provider_secret():
    result = search(
        lambda req: httpx.Response(200, json={"web": {"results": [row()]}}), max_queries=1
    )
    assert "private-test-key" not in json.dumps(result.model_dump(mode="json"))
