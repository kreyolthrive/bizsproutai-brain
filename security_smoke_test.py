from fastapi.testclient import TestClient

from main import app


client = TestClient(app)

payload = {"idea": "A neighborhood bookkeeping service for small businesses"}

missing = client.post("/api/validate", json=payload)
assert missing.status_code == 401, missing.text

wrong = client.post(
    "/api/validate",
    json=payload,
    headers={"Authorization": "Bearer definitely-not-the-service-token"},
)
assert wrong.status_code == 401, wrong.text

health = client.get("/api/health/security")
assert health.status_code == 200, health.text
body = health.json()
assert body["status"] == "active"
assert body["transport_security"] == "verified_https_ca_and_hostname"
assert body["certificate_pinning"] is False
assert body["service_auth_configured"] is True
assert body["field_encryption"] == "AES-256-GCM"
assert body["field_encryption_key_configured"] is True

legacy_health = client.get("/api/health/cert-pins")
assert legacy_health.status_code == 200
assert legacy_health.json()["certificate_pinning"] is False

print("Brain security smoke gates verified.")
