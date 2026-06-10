"""Pydantic models used to validate the structured data the model returns via
strict tool calls. The raw JSON Schemas handed to the API live next to the
calls (discovery.py / research.py); these models validate what comes back.
"""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class Candidate(BaseModel):
    """One prospective company surfaced during discovery."""

    name: str
    domain: str = Field(description="Primary website domain, e.g. acme.com")
    hq_location: str = Field(default="", description="City, State/Country")
    industry: str = ""
    why_fit: str = Field(description="Why this company could use Open Numerics")
    suggested_applications: List[str] = Field(
        default_factory=list,
        description="Concrete ON applications for this company's work",
    )
    fit_score: int = Field(description="0-10 fit score")
    is_service_provider: bool = Field(
        default=False,
        description=(
            "True if this company itself SELLS numerical simulation / UQ / "
            "scientific-ML / HPC services or software (a peer or competitor of "
            "Open Numerics, not a potential client). Such companies are excluded."
        ),
    )
    source_urls: List[str] = Field(default_factory=list)


class DiscoveryResult(BaseModel):
    candidates: List[Candidate] = Field(default_factory=list)


class Person(BaseModel):
    """A senior individual at a target company."""

    name: str
    title: str = ""
    public_email: Optional[str] = Field(
        default=None,
        description="Email only if found published publicly; else null",
    )


class OutreachResult(BaseModel):
    """Research + drafted initial email for a single winning company."""

    refined_applications: List[str] = Field(default_factory=list)
    public_emails: List[str] = Field(
        default_factory=list,
        description="Generic public inboxes found (e.g. info@, contact@)",
    )
    people: List[Person] = Field(default_factory=list)
    email_subject: str
    email_body: str
    draft_notes: str = Field(
        default="", description="Anything the sender should know before sending"
    )


class FollowUpResult(BaseModel):
    email_subject: str
    email_body: str
