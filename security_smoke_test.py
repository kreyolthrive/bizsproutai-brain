import time
from fastapi.testclient import TestClient
from starlette.requests import Request

from main import app
from security.request_verification import build_request_token, verify_mutation_request

client = TestClient(app)
payload = {"idea": "A neighborhood bookkeeping service for small businesses"}

missing = client.post("/api/v1/validate", json=payload)
assert missing.status_code == 401, missing.text
assert "missing_bearer_token" not in missing.text
assert missing.json()["error"]["code"] == "unauthorized"
assert missing.json()["error"]["requestId"]

wrong = client.post(
    "/api/v1/validate",
    json=payload,
    headers={"Authorization": "Bearer definitely-not-the-service-token"},
)
assert wrong.status_code == 401, wrong.text
assert "invalid_bearer_token" not in wrong.text

unsigned = client.post(
    "/api/v1/validate",
    json=payload,
    headers={"Authorization": "Bearer mock-service-token-for-ci"},
)
assert unsigned.status_code == 403, unsigned.text
assert "request_verification_required" not in unsigned.text
assert unsigned.json()["error"]["code"] == "forbidden"

method_restricted = client.get("/api/v1/validate")
assert method_restricted.status_code == 405, method_restricted.text

# Verify the request-signing primitive without calling an external AI provider.
timestamp = str(int(time.time()))
nonce = "nonce-12345678"
agent_id = "brain.validation"
session_id = "session-12345678"
token = build_request_token(
    timestamp=timestamp,
    nonce=nonce,
    method="POST",
    path="/api/v1/validate",
    agent_id=agent_id,
    session_id=session_id,
)
scope = {
    "type": "http",
    "method": "POST",
    "path": "/api/v1/validate",
    "headers": [
        (b"x-bizsprout-timestamp", timestamp.encode()),
        (b"x-bizsprout-nonce", nonce.encode()),
        (b"x-bizsprout-request-token", token.encode()),
        (b"x-agent-id", agent_id.encode()),
        (b"x-agent-session-id", session_id.encode()),
    ],
    "query_string": b"",
    "server": ("testserver", 80),
    "client": ("127.0.0.1", 12345),
    "scheme": "http",
}
verified_agent, verified_session = verify_mutation_request(Request(scope))
assert verified_agent == agent_id
assert verified_session == session_id

health = client.get("/api/v1/health/security")
assert health.status_code == 200, health.text
body = health.json()
assert body["status"] == "active"
assert body["api_version"] == "1"
assert body["transport_security"] == "verified_https_ca_and_hostname"
assert body["certificate_pinning"] is False
assert body["service_auth_configured"] is True
assert body["request_signing_configured"] is True
assert body["field_encryption"] == "AES-256-GCM"
assert body["field_encryption_key_configured"] is True
assert body["browser_cookie_auth"] is False

legacy_health = client.get("/api/health/cert-pins")
assert legacy_health.status_code == 200
assert legacy_health.json()["certificate_pinning"] is False

print("Brain security smoke gates verified.")
