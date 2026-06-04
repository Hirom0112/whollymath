"""Wire schemas for the parent-auth endpoints (Slice auth/parent-child, S3).

Kept in their OWN module (not the shared schemas.py) so this slice does not collide with
concurrent work there. Every REQUEST model is ``extra="forbid"`` — the OWASP
mass-assignment / BOPLA defense: a client cannot smuggle extra fields (``role``,
``parent_id``, ``email_verified``) into the create path; those are set SERVER-side only.
Email is a plain ``str`` (validated/normalized in the service) to avoid pulling in the
email-validator dependency for a single field.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ParentSignupRequest(BaseModel):
    """Email/password parent signup. Only the two fields a client may supply."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class ParentLoginRequest(BaseModel):
    """Email/password parent login."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)


class GoogleParentRequest(BaseModel):
    """Google sign-in for a parent: the GIS-issued ID token the frontend obtained."""

    model_config = ConfigDict(extra="forbid")

    id_token: str = Field(min_length=1)


class ParentMeResponse(BaseModel):
    """The parent's own minimal profile — no internal ids, no PII beyond their email."""

    model_config = ConfigDict(extra="forbid")

    email: str | None
    email_verified: bool
