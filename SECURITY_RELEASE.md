# Brain security candidate — 30 October 2026

This candidate incorporates the endpoint authentication, trusted proxy, response validation and mocked tests proposed in PR #1, then updates the vulnerable dependency pins found during the launch audit.

## Boundary and configuration

The paid endpoints require `REQUIRE_ENDPOINT_AUTH=true` and a non-empty `ENDPOINT_API_KEY`. The key is a server-side secret: configure it on Render and on the authorized backend caller. Never put it in a `VITE_*` variable or distribute it to a browser. Render configuration declares the secret without providing a value; no deployed secret was changed. Missing protection configuration fails closed. Health GET remains public.

Proxy headers are not trusted by default. Enable them only with verified immediate proxy CIDRs. The memory limiter is per process; use a shared gateway/store for any public multi-instance workload. This branch does not claim distributed rate limiting or frontend integration verification.

## Dependencies and checks

Runtime installation uses `requirements.lock.txt`; `requirements.txt` records direct pins. Removed unused FastAPI `all` extras. Updated FastAPI/Starlette and python-dotenv; updated pytest for its advisory. The older PR #1 pins had runtime advisories and must not be merged as an audited dependency solution unchanged.

In a clean local Python 3.12 environment: 15 mocked-provider tests pass, Ruff and mypy pass, and the 28-package locked runtime has no known vulnerabilities according to pip-audit. The source CI targets Python 3.11 and must run on this exact candidate before release. The audit does not prove hosted configuration, actual provider behavior, capacity or integration compatibility. Do not run public paid endpoints without the authorization boundary and operational cost limits.

No production deployment, secret rotation, payment, or user-data mutation was performed.
