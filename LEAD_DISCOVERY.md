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

## Implemented qualification contract

`lead_discovery.py` implements the typed brief, bounded query planning, supplied-candidate triage, supporting phrase excerpts, freshness checks, explicit exclusions, URL/text deduplication and a versioned response. Service and product briefs are supported. English default exclusions are conservative heuristics; other languages require configured exclusions and evaluation. Excerpts are normalized supplied text, not independently fetched citations. Unknown dates and unconfirmed required locations cannot receive high review priority. Even high-priority results always have `status=needs_review`.

`POST /api/leads/review` is server-to-server, requires the existing endpoint secret and refuses operation if endpoint authentication is disabled. The endpoint is off unless `LEAD_DISCOVERY_ENABLED=true`. Existing rate limiting applies; its in-memory deployment limitations remain. At most 50 supplied candidates, 6,000 characters per text and bounded brief terms are accepted. URLs are validated references only; no URL is fetched. This review route performs no model call, external search, persistence, migration, scheduler, email or customer data access.

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

## Implemented discovery connector and app integration

`POST /api/leads/discover` calls the fixed Brave Web Search origin through `lead_search.py`, then runs the evidence review contract. It is additionally disabled unless `LEAD_SEARCH_ENABLED=true`; `BRAVE_SEARCH_API_KEY` stays on Brain. HTTPX is now explicitly pinned at the version already present in the runtime lock. No new resolved package or lockfile hash is introduced.

The connector allows 1–3 queries per direct trusted-server request (default 2), up to 10 results/query, no pagination, no retries, 10 seconds/request and 25 seconds/run. Responses are capped at 512 KiB, redirects are refused, errors use sanitized codes, authentication/rate failures stop subsequent calls, invalid rows are counted and partial results survive failed queries. All planned-but-budgeted-out queries appear as not searched. Completed means completion within the selected query budget, not exhaustive coverage.

Result snippets are provider-supplied evidence. Titles never establish intent. Search-result age and last-modified hints never establish publication freshness; all search candidates have an unknown publication date and cannot receive high review priority. Deduplication retains the receipt corresponding to the strongest ranked candidate. No result URLs are fetched.

Companion changes in backend/frontend feature branches provide:

- `lead-discovery` Supabase function: authenticate a user, verify the business idea or app ownership and any linked canonical parent, consume per-user (2/minute, 20/day), canonical-business (10/day) and global (200/day) run quotas before Brain work. Fail closed on quota/ownership errors. Force 2 queries and 10 results/query; reject browser budget or provider overrides. The shared Brain secret is never browser-visible. Global maximum is therefore 400 search requests/day through this gateway; failed attempts also consume run quotas.
- CRM opportunities panel: explicit search submission, founder-editable brief, coverage/partial failure reporting, source snippets/links, shortlist and dismiss. Results and decisions are in memory only and reset when changing business or leaving/reloading the view. They do not create contacts, send outreach or subscribe anyone.
- UI stays hidden unless `VITE_LEAD_DISCOVERY_ENABLED=true`; edge stays off unless its `LEAD_DISCOVERY_ENABLED=true`. Brain requires both feature flags and existing endpoint authentication. These are staged code changes; no flags, credentials or deployments are activated here.

## Staging configuration and acceptance

After separately reviewing/approving the feature PRs, configure only in staging:

| Runtime | Configuration |
|---|---|
| Brain | `REQUIRE_ENDPOINT_AUTH=true`, `ENDPOINT_API_KEY`, `LEAD_DISCOVERY_ENABLED=true`, `LEAD_SEARCH_ENABLED=true`, `BRAVE_SEARCH_API_KEY` |
| Supabase | `LEAD_DISCOVERY_ENABLED=true`, `BRAIN_API_ORIGIN` (trusted HTTPS origin only), `BRAIN_ENDPOINT_API_KEY` matching Brain's secret |
| Frontend build | `VITE_LEAD_DISCOVERY_ENABLED=true` (public feature flag only) |

The gateway sends `x-api-key`; keep Brain's `ENDPOINT_AUTH_HEADER` at that default for this integration. A custom Brain auth-header configuration must be aligned before activation. Its in-memory IP limiter remains process-local; the edge gateway's database quotas supply tenant/global budgets. Ensure no other trusted caller bypasses those budgets.

Acceptance: no/incorrect Brain secret is refused; a user cannot search a foreign business; alias app/idea IDs share the canonical quota; provider errors cannot leak keys; a partial run stays partial; web snippets remain unverified; shortlist does not create contacts; changing businesses cannot show the previous run. Configure source access/retention for the selected provider before any enabled pilot. Search API access is not blanket permission to reuse content from every indexed platform.

## Remaining implementation gates

- Add opt-in campaign/run/candidate persistence with ownership RLS and canonical business foreign keys. A background worker must use trusted job IDs, recheck tenant scope and support cancellation, retries, leases, idempotency and spend limits. No production migration is included here.
- Add explicit accepted-only CRM promotion and a supported reply workflow. Do not auto-subscribe discovered people to marketing.
- Evaluate a human-labeled dataset across service/product offers and configured languages, including seller ads, negation, quotes, old posts, fake URLs, wrong locations and adversarial instructions. Track precision, false positives and per-run cost before wider rollout.
- Keep this feature separate from launch security promotion. This is an on-demand pilot implementation, not an autonomous scheduled agent or exhaustive discovery service.

## Local verification

Brain: 69 tests pass (including 18 mocked HTTP connector cases and 5 new API cases), Ruff lint/format and mypy pass. Local Python is 3.12; hosted Python 3.11 verification remains required. One existing Starlette/httpx deprecation warning remains. The gateway has 13 provider-free handler tests and passes frozen-lock Deno typechecking. Frontend includes request/response contracts and review interaction tests; see its feature PR for full-suite counts.

No live source call, provider spend, customer-data query, production flag/secret change, merge, deployment or migration was performed.
