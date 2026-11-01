"""Bounded lead-review engine. Inputs are evidence, never agent instructions.

This first slice plans searches and triages supplied candidates; it does not crawl,
contact people, verify source claims, or declare anyone a qualified customer.
"""

import hashlib
import ipaddress
import re
import unicodedata
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

DEFAULT_EXCLUSIONS = [
    "not looking for",
    "no longer looking",
    "already found",
    "position filled",
    "i offer",
    "we offer",
    "looking for clients",
    "looking for work",
    "seeking clients",
]


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class LeadBrief(ContractModel):
    offer: str = Field(min_length=3, max_length=500)
    offer_type: Literal["service", "product"]
    offer_terms: list[str] = Field(min_length=1, max_length=15)
    buyer_phrases: list[str] = Field(min_length=1, max_length=15)
    exclude_phrases: list[str] = Field(default_factory=list, max_length=20)
    location_terms: list[str] = Field(default_factory=list, max_length=10)
    max_age_days: int = Field(default=14, ge=1, le=90)

    @field_validator("offer_terms", "buyer_phrases", "exclude_phrases", "location_terms")
    @classmethod
    def validate_terms(cls, terms: list[str]) -> list[str]:
        cleaned = list(dict.fromkeys(term.strip() for term in terms))
        if any(not term or len(term) > 100 for term in cleaned):
            raise ValueError("Terms must contain 1–100 characters")
        return cleaned


class Candidate(ContractModel):
    source_url: str = Field(min_length=10, max_length=2000)
    source_name: str = Field(min_length=1, max_length=100)
    text: str = Field(min_length=3, max_length=6000)
    published_at: AwareDatetime | None = None
    # No inferred email, phone, wealth, identity or sensitive personal traits.

    @field_validator("source_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        return canonical_url(value)


class LeadReviewRequest(ContractModel):
    brief: LeadBrief
    candidates: list[Candidate] = Field(default_factory=list, max_length=50)


class EvidenceMatch(ContractModel):
    kind: Literal["offer", "intent", "location", "exclusion"]
    phrase: str
    excerpt: str


class LeadReview(ContractModel):
    source_url: str
    source_name: str
    published_at: AwareDatetime | None
    score: int
    priority: Literal["high", "normal", "reject"]
    status: Literal["needs_review"] = "needs_review"
    reasons: list[str]
    evidence: list[EvidenceMatch]
    next_action: str


class LeadReviewResponse(ContractModel):
    contract_version: Literal["lead-review-v1"] = "lead-review-v1"
    mode: Literal["supplied_candidates_only"] = "supplied_candidates_only"
    search_queries: list[str]
    results: list[LeadReview]
    duplicates_removed: int
    coverage: str = (
        "No sources searched. Results triage supplied text; source claims are unverified."
    )


def canonical_url(value: str) -> str:
    """Validate references only. This module never fetches these URLs."""
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
        if parsed.scheme not in {"https", "http"} or parsed.username or parsed.password:
            raise ValueError("Expected a public HTTP(S) source URL")
        if not host or "." not in host or host.endswith((".local", ".localhost", ".internal")):
            raise ValueError("Expected a public source hostname")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError("Private source addresses are unsupported")
        if port not in {None, 80, 443}:
            raise ValueError("Nonstandard source ports are unsupported")
        query = urlencode(
            sorted(
                (key, val)
                for key, val in parse_qsl(parsed.query, keep_blank_values=True)
                if not key.lower().startswith("utm_") and key.lower() not in {"fbclid", "gclid"}
            )
        )
        return urlunsplit(
            (parsed.scheme.lower(), parsed.netloc.lower(), parsed.path or "/", query, "")
        )
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Invalid public source URL") from exc


def normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def phrase_pattern(phrase: str) -> re.Pattern[str]:
    # Literal phrases, not regexes. Unicode boundaries avoid 'spa' matching 'space'.
    return re.compile(r"(?<!\w)" + re.escape(normalize(phrase)) + r"(?!\w)")


def evidence_for(
    text: str, phrases: list[str], kind: Literal["offer", "intent", "location", "exclusion"]
) -> list[EvidenceMatch]:
    normalized = normalize(text)
    evidence = []
    for phrase in phrases:
        match = phrase_pattern(phrase).search(normalized)
        if match:
            evidence.append(
                EvidenceMatch(
                    kind=kind,
                    phrase=phrase,
                    excerpt=normalized[
                        max(0, match.start() - 60) : min(len(normalized), match.end() + 100)
                    ],
                )
            )
    return evidence


def build_queries(brief: LeadBrief) -> list[str]:
    # Quote literals; strip operator syntax so a user term cannot add site:/OR clauses.
    def quote(term: str) -> str:
        cleaned = " ".join(re.findall(r"[\w'-]+", term, flags=re.UNICODE))
        return f'"{cleaned}"'

    locations = " ".join(quote(term) for term in brief.location_terms[:1])
    return [
        " ".join(part for part in [quote(offer), quote(intent), locations] if part)
        for offer in brief.offer_terms[:3]
        for intent in brief.buyer_phrases[:3]
    ]


def review_candidate(brief: LeadBrief, candidate: Candidate, now: datetime) -> LeadReview:
    offer = evidence_for(candidate.text, brief.offer_terms, "offer")
    intent = evidence_for(candidate.text, brief.buyer_phrases, "intent")
    location = evidence_for(candidate.text, brief.location_terms, "location")
    exclusion = evidence_for(
        candidate.text, DEFAULT_EXCLUSIONS + brief.exclude_phrases, "exclusion"
    )
    reasons = []
    blocked = False
    if not offer:
        reasons.append("No offer match in supplied text")
        blocked = True
    if not intent:
        reasons.append("No configured buying-intent phrase in supplied text")
        blocked = True
    if exclusion:
        reasons.append("Configured exclusion phrase matched")
        blocked = True
    fresh = False
    if candidate.published_at is None:
        reasons.append("Publication date unknown; freshness needs verification")
    else:
        age = (now - candidate.published_at).total_seconds()
        if age < 0:
            reasons.append("Publication date is in the future")
            blocked = True
        elif age > brief.max_age_days * 86400:
            reasons.append("Outside the configured freshness window")
            blocked = True
        else:
            fresh = True
    if brief.location_terms and not location:
        reasons.append("Target location is unconfirmed")
    score = (35 if offer else 0) + (35 if intent else 0) + (15 if fresh else 0)
    score += 15 if location or not brief.location_terms else 0
    if blocked:
        score = 0
    priority: Literal["high", "normal", "reject"] = "reject" if blocked else "normal"
    if not blocked and fresh and (location or not brief.location_terms):
        priority = "high"
    reasons.append(
        "Rule-based relevance score; not a purchase probability or verified qualification"
    )
    return LeadReview(
        source_url=candidate.source_url,
        source_name=candidate.source_name,
        published_at=candidate.published_at,
        score=score,
        priority=priority,
        reasons=reasons,
        evidence=offer + intent + location + exclusion,
        next_action="Open the source and verify buyer intent, availability, fit and permitted reply route before outreach.",
    )


def review_leads(request: LeadReviewRequest, now: datetime | None = None) -> LeadReviewResponse:
    current_time = now or datetime.now(UTC)
    if current_time.utcoffset() is None:
        raise ValueError("Review time must have a timezone")
    ranked = sorted(
        (
            (review_candidate(request.brief, candidate, current_time), candidate)
            for candidate in request.candidates
        ),
        key=lambda item: item[0].score,
        reverse=True,
    )
    urls: set[str] = set()
    texts: set[str] = set()
    results = []
    for review, candidate in ranked:
        text_hash = hashlib.sha256(normalize(candidate.text).encode()).hexdigest()
        if review.source_url in urls or text_hash in texts:
            continue
        urls.add(review.source_url)
        texts.add(text_hash)
        results.append(review)
    return LeadReviewResponse(
        search_queries=build_queries(request.brief),
        results=results,
        duplicates_removed=len(request.candidates) - len(results),
    )
