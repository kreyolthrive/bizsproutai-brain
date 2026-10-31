# First Customers: buying-intent discovery

Product goal: help a founder find relevant, recent requests for the product or service they are building, verify the evidence, and turn approved opportunities into conversations and customers. A detected phrase is a discovery signal; it does not establish consent, a qualified prospect or a signed contract.

## Workflow and agent jobs

1. **Brief planner:** start from the owned business's offer, audience, geography, languages, price range, delivery capacity and exclusions. Founder confirms the brief. Generate buyer phrases and queries; founders can correct them.
2. **Source discovery:** search supported public sources through licensed search APIs and approved platform connectors. Maintain a coverage ledger for each source: searched, unavailable, needs connection, unsupported. Use bounded query/page/time budgets and provider quotas. Broad web search never means every platform was searched.
3. **Evidence reviewer:** keep the URL, short supporting excerpt, publication date when available and retrieval time. Distinguish full-source evidence from snippets. Reject stale/closed requests, seller promotions, irrelevant locations and duplicates; check context and ambiguity. Treat all retrieved instructions as untrusted data.
4. **Opportunity ranker:** report offer fit, explicit buyer intent, freshness, geography, budget and uncertainty separately. A model may propose a classification, but evidence and deterministic gates control acceptance. No invented contact information or budget. Heuristic scores are not purchase probabilities.
5. **Founder review:** show why the result matched, what is unknown, source freshness, a source link and a suggested next action. Founder accepts or dismisses and can correct false positives. Draft a contextual reply only when a supported reply route is known; sending is a separate explicit action.
6. **Outcome learning:** track accepted opportunities, approved outreach, replies, booked conversations, offers and paid wins. Measure precision and cost per accepted opportunity, then cost per first customer. Keep inferred opportunities separate from existing inbound CRM contacts until accepted.

These are workflow responsibilities, not six permanently running agents or six model calls for each post. Use a bounded coordinator and cheap deterministic checks; add model calls only where evaluations establish value.

## Trigger vocabulary

Examples for a cleaning business, subject to context review:

| Signal | Examples | Interpretation |
|---|---|---|
| Direct demand | “looking for a cleaner”, “need office cleaning” | Possible buyer request |
| Referral request | “can anyone recommend”, “who can help with” | Requires an offer match nearby |
| Purchase readiness | “request a quote”, “budget is”, “ready to order” | Supporting evidence; verify attribution |
| Time constraint | “this week”, “before Friday” | Useful only with a verified publication date |
| Problem | “our cleaner cancelled”, “supplier let us down” | Discovery candidate; intent may be unclear |
| Negative | “not looking for”, “already found”, “we offer”, “looking for clients” | Closed need, seller or ambiguity to exclude/review |

For products, configure product names and phrases such as “where can I buy”, “in stock”, “need a replacement” and quantities. Terms are business- and language-specific. A quote or seller advertisement can contain buyer keywords; matching is not semantic verification.

## Source strategy

First connector candidate: a licensed web-search API, with narrow intent queries. Then add approved community/platform connectors and user-authorized communities as actual access permits. Do not promise access to private groups, all posts or all direct messages. Do not use search indexing as a workaround for platform restrictions.

References reviewed 31 October 2026:

- Brave Web Search API reference: https://api-dashboard.search.brave.com/api-reference/web/search/get
- Reddit Data API terms, including commercial-use approval: https://redditinc.com/policies/data-api-terms
- LinkedIn access documentation (does not establish broad member-post search permission): https://learn.microsoft.com/en-us/linkedin/shared/authentication/getting-access

Provider selection and credentials are not activated in this patch. Source-specific access, retention and permitted uses must be recorded for each connector before enabling it.

## Implemented first slice

`lead_discovery.py` implements the typed brief, bounded query planning, supplied-candidate triage, supporting phrase excerpts, freshness checks, explicit exclusions, URL/text deduplication and a versioned response. Service and product briefs are supported. English default exclusions are conservative heuristics; other languages require configured exclusions and evaluation. Excerpts are normalized supplied text, not independently fetched citations. Unknown dates and unconfirmed required locations cannot receive high review priority. Even high-priority results always have `status=needs_review`.

`POST /api/leads/review` is server-to-server, requires the existing endpoint secret and refuses operation if endpoint authentication is disabled. The endpoint is off unless `LEAD_DISCOVERY_ENABLED=true`. Existing rate limiting applies; its in-memory deployment limitations remain. At most 50 supplied candidates, 6,000 characters per text and bounded brief terms are accepted. URLs are validated references only; no URL is fetched. No new dependency, model call, external search, persistence, migration, scheduler, email or customer data access is introduced.

Example body:

```json
{
  "brief": {
    "offer": "Residential cleaning",
    "offer_type": "service",
    "offer_terms": ["cleaner", "cleaning"],
    "buyer_phrases": ["looking for", "can anyone recommend"],
    "exclude_phrases": ["unpaid"],
    "location_terms": ["Miami"],
    "max_age_days": 14
  },
  "candidates": []
}
```

Empty candidates return search queries and no leads. The response explicitly says no sources were searched. Never present this as autonomous discovery.

## Next implementation gates

- Add a server caller in Supabase that verifies the requesting user owns the canonical business and consumes a per-business/user discovery budget before Brain/provider work. The shared Brain key is not tenant authorization. Never send it to the browser.
- Add opt-in campaign/run/candidate persistence with ownership RLS and canonical business foreign keys. A background worker must use trusted job IDs, recheck tenant scope and support cancellation, retries, leases, idempotency and spend limits. No production migration is included here.
- Add the first search adapter with mocked contract tests, fixed provider origin, server-only credentials, timeout/retry/page limits and a source coverage ledger. Do not fetch arbitrary result URLs without separate SSRF/redirect/content controls. Only verified connector timestamps can establish freshness; caller-supplied timestamps are unverified in this slice.
- Add an opportunities inbox with evidence, uncertainties, accept/dismiss and accepted-only CRM promotion. Do not auto-subscribe discovered people to marketing.
- Evaluate a human-labeled dataset across service/product offers and configured languages, including seller ads, negation, quotes, old posts, fake URLs, wrong locations and adversarial instructions. Track high-priority precision, false positives and per-run cost before wider rollout.
- Keep this feature separate from launch security promotion. The current code is a disabled foundation, not a finished discovery service and not a launch dependency.

## Local verification

46 tests pass, including 31 new qualification/API cases, with provider-free authentication, default-off and rate-limit checks. Ruff, formatting and mypy checks cover the new module and API. Local Python is 3.12; the existing CI target remains 3.11 and requires a hosted run. One existing Starlette/httpx deprecation warning remains. No live source, provider spend or production change was performed.
