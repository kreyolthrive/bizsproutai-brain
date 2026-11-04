from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import main


@pytest.fixture(autouse=True)
def reset_rate_limit_state(monkeypatch):
    main.REQUEST_HISTORY.clear()
    monkeypatch.setattr(main, "MAX_REQUESTS_PER_WINDOW", 10)
    monkeypatch.setattr(main, "LAST_CLEANUP_TIME", main.time.time())


@pytest.fixture
def client():
    return TestClient(main.app)


def mock_openai_json(monkeypatch, *payloads):
    async def fake_create(**kwargs):
        payload = payloads[fake_create.calls]
        fake_create.calls += 1
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=payload))])

    fake_create.calls = 0
    monkeypatch.setattr(main.client.chat.completions, "create", fake_create)


def test_home_returns_online_status(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["status"] == "BizSproutAI Brain is Online"


def test_validate_returns_provider_json(client, monkeypatch):
    mock_openai_json(monkeypatch, '{"score": 80, "status": "GO"}')

    response = client.post(
        "/api/validate",
        json={"idea": "A SaaS for local delivery routing"},
    )

    assert response.status_code == 200
    assert response.json() == {"score": 80, "status": "GO"}


def test_validate_rejects_short_idea(client):
    response = client.post("/api/validate", json={"idea": "tiny"})

    assert response.status_code == 422


def test_validate_returns_500_for_invalid_provider_json(client, monkeypatch):
    mock_openai_json(monkeypatch, "not-json")

    response = client.post(
        "/api/validate",
        json={"idea": "A valid business idea text"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == ("Failed to validate business idea. Please try again.")


def test_validate_returns_500_when_provider_fails(client, monkeypatch):
    async def fail_create(**kwargs):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(main.client.chat.completions, "create", fail_create)

    response = client.post(
        "/api/validate",
        json={"idea": "A valid business idea text"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == ("Failed to validate business idea. Please try again.")


def test_generate_roadmap_returns_provider_json(client, monkeypatch):
    mock_openai_json(
        monkeypatch,
        '{"phase_1_legal":{"step_name":"Register","description":"Register entity"},'
        '"phase_2_infrastructure":{"step_name":"Setup","description":"Set up tools"},'
        '"phase_3_launch":{"step_name":"Launch","description":"Go live"},'
        '"warnings":[]}',
    )

    response = client.post(
        "/api/generate_roadmap",
        json={
            "validated_idea": "Validated business idea",
            "region": "US",
            "business_type": "SaaS",
        },
    )

    assert response.status_code == 200
    assert response.json()["phase_1_legal"]["step_name"] == "Register"


def test_generate_roadmap_returns_500_when_generation_fails(client, monkeypatch):
    async def fail_roadmap(*args, **kwargs):
        return None

    monkeypatch.setattr(main, "internal_generate_roadmap", fail_roadmap)

    response = client.post(
        "/api/generate_roadmap",
        json={
            "validated_idea": "Validated business idea",
            "region": "US",
            "business_type": "SaaS",
        },
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to generate localized roadmap."


def test_generate_report_uses_supplied_roadmap(client, monkeypatch):
    mock_openai_json(
        monkeypatch,
        '{"market_analysis":{"saturation_level":"Medium","market_insight":"Room to grow"},'
        '"distribution_score":{"score":65,"analysis":"Good channels"},'
        '"financial_outlook":{"rating":"Positive","reasoning":"Lean model"},'
        '"action_plan":["Register","Set up tools","Launch"]}',
    )

    response = client.post(
        "/api/generate_report",
        json={
            "validated_idea": "Validated business idea",
            "region": "US",
            "business_type": "SaaS",
            "roadmap_data": {
                "phase_1_legal": {"step_name": "Register"},
                "phase_2_infrastructure": {"step_name": "Set up tools"},
                "phase_3_launch": {"step_name": "Launch"},
            },
        },
    )

    assert response.status_code == 200
    assert len(response.json()["action_plan"]) == 3


def test_generate_report_builds_missing_roadmap(client, monkeypatch):
    roadmap = {
        "phase_1_legal": {"step_name": "Register"},
        "phase_2_infrastructure": {"step_name": "Set up tools"},
        "phase_3_launch": {"step_name": "Launch"},
    }

    async def fake_roadmap(*args, **kwargs):
        return roadmap

    monkeypatch.setattr(main, "internal_generate_roadmap", fake_roadmap)
    mock_openai_json(
        monkeypatch,
        '{"market_analysis":{"saturation_level":"Medium","market_insight":"Room to grow"},'
        '"distribution_score":{"score":65,"analysis":"Good channels"},'
        '"financial_outlook":{"rating":"Positive","reasoning":"Lean model"},'
        '"action_plan":["Register","Set up tools","Launch"]}',
    )

    response = client.post(
        "/api/generate_report",
        json={
            "validated_idea": "Validated business idea",
            "region": "US",
            "business_type": "SaaS",
        },
    )

    assert response.status_code == 200
    assert response.json()["action_plan"][0] == "Register"


def test_generate_report_returns_500_for_invalid_provider_json(client, monkeypatch):
    mock_openai_json(monkeypatch, "not-json")

    response = client.post(
        "/api/generate_report",
        json={
            "validated_idea": "Validated business idea",
            "region": "US",
            "business_type": "SaaS",
            "roadmap_data": {"phase_1_legal": {"step_name": "Register"}},
        },
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Failed to generate diligence report."


def test_rate_limit_is_enforced_per_client_ip(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_REQUESTS_PER_WINDOW", 1)
    mock_openai_json(monkeypatch, '{"score": 80, "status": "GO"}')

    payload = {"idea": "A valid business idea text"}
    first = client.post("/api/validate", json=payload)
    second = client.post("/api/validate", json=payload)

    assert first.status_code == 200
    assert second.status_code == 429
    assert second.json()["detail"] == (
        "Rate limit exceeded. Please wait a moment before trying again."
    )
