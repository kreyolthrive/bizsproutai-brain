import os
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("OPENAI_API_KEY", "test-openai-key")

import main


@pytest.fixture(autouse=True)
def reset_security_and_limits(monkeypatch):
    monkeypatch.setattr(main, "ENDPOINT_AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "ENDPOINT_API_KEY", "test-endpoint-key")
    monkeypatch.setattr(main, "AUTH_HEADER_NAME", "x-api-key")
    monkeypatch.setattr(
        main,
        "RATE_LIMITER",
        main.InMemoryRateLimiter(window_seconds=60, max_requests=50),
    )


@pytest.fixture
def client():
    return TestClient(main.app)


def _mock_openai_json(monkeypatch, *payloads):
    async def fake_create(**kwargs):
        payload = payloads[fake_create.calls]
        fake_create.calls += 1
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=payload))])

    fake_create.calls = 0
    monkeypatch.setattr(main.client.chat.completions, "create", fake_create)


def test_home(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "BizSproutAI Brain is Online"


def test_validate_success(client, monkeypatch):
    _mock_openai_json(
        monkeypatch,
        '{"score":80,"status":"GO","region":"US","business_type":"SaaS","feedback":"Promising",'
        '"risk_assessment":{"demand":{"score":70,"explanation":"ok"},"economics":{"score":75,"explanation":"ok"},'
        '"distribution":{"score":85,"explanation":"ok"},"moat":{"score":65,"explanation":"ok"}},'
        '"fixes":[{"problem":"None","fix":"Proceed"}]}',
    )

    response = client.post(
        "/api/validate",
        json={"idea": "A SaaS for local delivery routing"},
        headers={"x-api-key": "test-endpoint-key"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "GO"


def test_validate_provider_invalid_json_returns_502(client, monkeypatch):
    _mock_openai_json(monkeypatch, "not-json")

    response = client.post(
        "/api/validate",
        json={"idea": "A valid business idea text"},
        headers={"x-api-key": "test-endpoint-key"},
    )
    assert response.status_code == 502


def test_validate_provider_failure_returns_502(client, monkeypatch):
    async def fail_create(**kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(main.client.chat.completions, "create", fail_create)

    response = client.post(
        "/api/validate",
        json={"idea": "A valid business idea text"},
        headers={"x-api-key": "test-endpoint-key"},
    )
    assert response.status_code == 502


def test_generate_roadmap_success(client, monkeypatch):
    _mock_openai_json(
        monkeypatch,
        '{"phase_1_legal":{"step_name":"Register","description":"Register entity","estimated_cost":"$100"},'
        '"phase_2_infrastructure":{"step_name":"Setup","description":"Set up tools"},'
        '"phase_3_launch":{"step_name":"Launch","description":"Go live"},"warnings":["None"]}',
    )

    response = client.post(
        "/api/generate_roadmap",
        json={
            "validated_idea": "Validated business idea",
            "region": "US",
            "business_type": "SaaS",
        },
        headers={"x-api-key": "test-endpoint-key"},
    )
    assert response.status_code == 200
    assert "phase_1_legal" in response.json()


def test_generate_report_success(client, monkeypatch):
    _mock_openai_json(
        monkeypatch,
        '{"market_analysis":{"saturation_level":"Medium","market_insight":"Room to grow"},'
        '"distribution_score":{"score":65,"analysis":"Good channels"},'
        '"financial_outlook":{"rating":"Positive","reasoning":"Lean model"},'
        '"action_plan":["Do A","Do B","Do C"]}',
    )

    response = client.post(
        "/api/generate_report",
        json={
            "validated_idea": "Validated business idea",
            "region": "US",
            "business_type": "SaaS",
            "roadmap_data": {
                "phase_1_legal": {
                    "step_name": "Register",
                    "description": "Register entity",
                    "estimated_cost": "$100",
                },
                "phase_2_infrastructure": {
                    "step_name": "Setup",
                    "description": "Set up tools",
                },
                "phase_3_launch": {"step_name": "Launch", "description": "Go live"},
                "warnings": ["None"],
            },
        },
        headers={"x-api-key": "test-endpoint-key"},
    )
    assert response.status_code == 200
    assert len(response.json()["action_plan"]) == 3


def test_generate_report_invalid_schema_returns_502(client, monkeypatch):
    _mock_openai_json(
        monkeypatch,
        '{"market_analysis":{"saturation_level":"Medium"},"distribution_score":{"score":65,"analysis":"Good channels"},'
        '"financial_outlook":{"rating":"Positive","reasoning":"Lean model"},"action_plan":["Do A"]}',
    )

    response = client.post(
        "/api/generate_report",
        json={
            "validated_idea": "Validated business idea",
            "region": "US",
            "business_type": "SaaS",
            "roadmap_data": {
                "phase_1_legal": {
                    "step_name": "Register",
                    "description": "Register entity",
                    "estimated_cost": "$100",
                },
                "phase_2_infrastructure": {
                    "step_name": "Setup",
                    "description": "Set up tools",
                },
                "phase_3_launch": {"step_name": "Launch", "description": "Go live"},
                "warnings": ["None"],
            },
        },
        headers={"x-api-key": "test-endpoint-key"},
    )
    assert response.status_code == 502


def test_rate_limit_enforced(client, monkeypatch):
    monkeypatch.setattr(
        main,
        "RATE_LIMITER",
        main.InMemoryRateLimiter(window_seconds=60, max_requests=1),
    )
    _mock_openai_json(
        monkeypatch,
        '{"score":80,"status":"GO","region":"US","business_type":"SaaS","feedback":"Promising",'
        '"risk_assessment":{"demand":{"score":70,"explanation":"ok"},"economics":{"score":75,"explanation":"ok"},'
        '"distribution":{"score":85,"explanation":"ok"},"moat":{"score":65,"explanation":"ok"}},'
        '"fixes":[{"problem":"None","fix":"Proceed"}]}',
    )

    first = client.post(
        "/api/validate",
        json={"idea": "A valid business idea text"},
        headers={"x-api-key": "test-endpoint-key"},
    )
    second = client.post(
        "/api/validate",
        json={"idea": "A valid business idea text"},
        headers={"x-api-key": "test-endpoint-key"},
    )
    assert first.status_code == 200
    assert second.status_code == 429


def test_auth_fail_closed_when_expected(client, monkeypatch):
    monkeypatch.setattr(main, "ENDPOINT_AUTH_REQUIRED", True)
    monkeypatch.setattr(main, "ENDPOINT_API_KEY", "")

    response = client.post(
        "/api/validate",
        json={"idea": "A valid business idea text"},
        headers={"x-api-key": "test-endpoint-key"},
    )
    assert response.status_code == 503
