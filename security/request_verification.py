import hashlib
import hmac
import os
import re
import time
from fastapi import HTTPException, Request

TOKEN_TTL_SECONDS = 120
NONCE_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
AGENT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9._:-]{2,119}$")


def _signing_key() -> bytes:
    key = os.getenv("BRAIN_REQUEST_SIGNING_KEY", "").strip()
    if len(key) < 32:
        raise HTTPException(status_code=503, detail="request_signing_not_configured")
    return key.encode("utf-8")


def canonical_request_message(
    *, timestamp: str, nonce: str, method: str, path: str, agent_id: str, session_id: str
) -> str:
    return "\n".join(
        [timestamp, nonce, method.upper(), path, agent_id, session_id]
    )


def build_request_token(
    *, timestamp: str, nonce: str, method: str, path: str, agent_id: str, session_id: str
) -> str:
    message = canonical_request_message(
        timestamp=timestamp,
        nonce=nonce,
        method=method,
        path=path,
        agent_id=agent_id,
        session_id=session_id,
    )
    return hmac.new(_signing_key(), message.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_mutation_request(req: Request) -> tuple[str, str]:
    timestamp = req.headers.get("x-bizsprout-timestamp", "").strip()
    nonce = req.headers.get("x-bizsprout-nonce", "").strip()
    presented = req.headers.get("x-bizsprout-request-token", "").strip()
    agent_id = req.headers.get("x-agent-id", "").strip().lower()
    session_id = req.headers.get("x-agent-session-id", "").strip()

    if not timestamp or not nonce or not presented or not agent_id or not session_id:
        raise HTTPException(status_code=403, detail="request_verification_required")
    if not NONCE_RE.fullmatch(nonce) or not NONCE_RE.fullmatch(session_id):
        raise HTTPException(status_code=403, detail="request_verification_invalid")
    if not AGENT_ID_RE.fullmatch(agent_id):
        raise HTTPException(status_code=403, detail="agent_identity_invalid")

    try:
        issued_at = int(timestamp)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="request_verification_invalid") from exc

    now = int(time.time())
    if abs(now - issued_at) > TOKEN_TTL_SECONDS:
        raise HTTPException(status_code=403, detail="request_verification_expired")

    expected = build_request_token(
        timestamp=timestamp,
        nonce=nonce,
        method=req.method,
        path=req.url.path,
        agent_id=agent_id,
        session_id=session_id,
    )
    if not hmac.compare_digest(presented, expected):
        raise HTTPException(status_code=403, detail="request_verification_invalid")

    return agent_id, session_id
