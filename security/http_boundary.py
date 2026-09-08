import json
import logging
import re
import traceback
import uuid
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
logger = logging.getLogger("bizsproutai.private")
logger.setLevel(logging.INFO)

PUBLIC_STATUS_MESSAGES = {
    400: ("bad_request", "Please check the request and try again."),
    401: ("unauthorized", "Authentication is required."),
    403: ("forbidden", "This request was not accepted."),
    404: ("not_found", "The requested resource was not found."),
    405: ("method_not_allowed", "That request method is not supported."),
    413: ("payload_too_large", "The request is too large."),
    422: ("validation_failed", "Some request fields are invalid."),
    429: ("rate_limited", "Too many requests were received. Please try again shortly."),
    502: ("upstream_error", "The AI service could not complete the request. Please try again."),
    503: ("service_unavailable", "This service is temporarily unavailable. Please try again shortly."),
}


def get_request_id(request: Request) -> str:
    incoming = request.headers.get("x-request-id", "").strip()
    if REQUEST_ID_RE.fullmatch(incoming):
        return incoming
    return str(uuid.uuid4())


def private_log(request: Request, exc: Exception, *, status_code: int) -> None:
    request_id = getattr(request.state, "request_id", "unknown")
    record = {
        "level": "error",
        "event": "application_error",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "request_id": request_id,
        "method": request.method,
        "path": request.url.path,
        "agent_id": request.headers.get("x-agent-id"),
        "agent_session_id": request.headers.get("x-agent-session-id"),
        "status_code": status_code,
        "error": {
            "type": exc.__class__.__name__,
            "message": str(exc),
            "traceback": "".join(traceback.format_exception(exc)),
        },
    }
    # Structured stderr/private runtime logs only. Authorization, cookies and request bodies are intentionally excluded.
    logger.error(json.dumps(record, ensure_ascii=False))


def public_error(status_code: int, request_id: str) -> JSONResponse:
    code, message = PUBLIC_STATUS_MESSAGES.get(
        status_code,
        (
            "internal_error",
            "We could not complete that request. Please try again. If it continues, use the reference ID when contacting support.",
        ),
    )
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "requestId": request_id,
            }
        },
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Request-Id": request_id,
            "X-BizSprout-API-Version": "1",
        },
    )


def install_error_boundaries(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = get_request_id(request)
        try:
            response = await call_next(request)
        except Exception as exc:  # final application boundary
            private_log(request, exc, status_code=500)
            return public_error(500, request.state.request_id)

        response.headers["X-Request-Id"] = request.state.request_id
        response.headers["X-BizSprout-API-Version"] = "1"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        if request.url.path in {
            "/api/validate",
            "/api/generate_roadmap",
            "/api/generate_report",
        }:
            response.headers["Deprecation"] = "true"
            response.headers["Link"] = f'<{request.url.path.replace("/api/", "/api/v1/")}>; rel="successor-version"'
        return response

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        # HTTP exceptions can contain provider/configuration details. Keep the detail private.
        private_log(request, exc, status_code=exc.status_code)
        response = public_error(exc.status_code, request.state.request_id)
        if exc.status_code == 429:
            response.headers["Retry-After"] = "60"
        return response

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        private_log(request, exc, status_code=500)
        return public_error(500, request.state.request_id)
