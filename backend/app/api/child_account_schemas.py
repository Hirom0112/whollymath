"""Wire schemas for the child-account endpoints (Slice auth/parent-child, S3).

Own module (navigability §7) and ``extra="forbid"`` on every request (mass-assignment
defense — a client cannot set ``parent_id``/``role``/``public_id``; those are server-set).
``locale`` is a ``Literal`` of the two rendered help-languages so an unknown value is a 422.
A child's ``public_id`` (opaque UUID) is the ONLY id that crosses the wire — never the
sequential learner id (IDOR defense).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# The two rendered help-languages (matches Learner.locale / the tts vocabulary).
Locale = Literal["en", "es-MX"]


class CreateChildRequest(BaseModel):
    """Fields a parent supplies to create one child profile."""

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=64)
    grade_level: int = Field(default=6, ge=1, le=12)
    locale: Locale = "en"
    username: str = Field(min_length=3, max_length=32)
    pin: str = Field(min_length=4, max_length=4)


class ResetPinRequest(BaseModel):
    """A parent setting a new PIN for one child."""

    model_config = ConfigDict(extra="forbid")

    pin: str = Field(min_length=4, max_length=4)


class ChildLoginRequest(BaseModel):
    """Independent child login (school/shared device): household email + username + PIN."""

    model_config = ConfigDict(extra="forbid")

    parent_email: str = Field(min_length=3, max_length=320)
    username: str = Field(min_length=3, max_length=32)
    pin: str = Field(min_length=4, max_length=4)


class ChildSummary(BaseModel):
    """One child as the parent dashboard / profile picker sees them (no secrets)."""

    model_config = ConfigDict(extra="forbid")

    public_id: str
    display_name: str | None
    grade_level: int | None
    locale: str


class ChildCredentialResponse(BaseModel):
    """Returned right after create: the username to share + the child's opaque id."""

    model_config = ConfigDict(extra="forbid")

    public_id: str
    username: str


class ChildSessionResponse(BaseModel):
    """Returned when a child session is opened (profile-pick or independent login)."""

    model_config = ConfigDict(extra="forbid")

    public_id: str
    display_name: str | None
