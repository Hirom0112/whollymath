"""Send the COPPA parental-email verification — the ONLY place we send mail (S3).

Owner decision 2026-06-03: email/password parents must verify their email, because a
verified parent email is the COPPA consent anchor (RESEARCH.md). Delivery is via AWS SES
(``boto3``) in prod; when SES is not configured (local dev / tests) we fall back to a
logging no-op so the flow still runs end-to-end without standing up email.

Sending is BEST-EFFORT: a delivery failure must NOT 500 the signup (the parent row is
already created; they can request a resend). The sender logs and swallows transport
errors. Nothing here touches the turn loop (invariant 8).

Config (env): ``SES_SENDER`` (a verified SES "From" identity, e.g. no-reply@whollymath.app)
and ``AWS_REGION``. With ``SES_SENDER`` unset, :func:`default_email_sender` returns the
logging fallback. In prod the Fargate task authenticates to SES via its IAM role — no
static credentials in code (CLAUDE.md §10).
"""

from __future__ import annotations

import logging
import os
from typing import Protocol

_log = logging.getLogger(__name__)


class EmailSender(Protocol):
    """The one operation the auth layer needs: deliver a verification link."""

    def send_verification_email(self, *, to_email: str, verify_url: str) -> None: ...


class LoggingEmailSender:
    """Dev/test fallback: log the verification link instead of sending it. Never raises."""

    def send_verification_email(self, *, to_email: str, verify_url: str) -> None:
        _log.info("[email:dev] verification link for %s -> %s", to_email, verify_url)


class SesEmailSender:
    """Send the verification email through AWS SES (boto3). Best-effort: logs on failure."""

    def __init__(self, *, sender: str, region: str | None = None) -> None:
        self._sender = sender
        self._region = region
        self._client = None  # lazily created so import/boot needs no AWS round-trip

    def _ses(self) -> object:
        if self._client is None:
            import boto3  # local import: only the SES path pays the boto3 import cost

            self._client = boto3.client("ses", region_name=self._region)
        return self._client

    def send_verification_email(self, *, to_email: str, verify_url: str) -> None:
        subject = "Verify your WhollyMath parent account"
        body_text = (
            "Welcome to WhollyMath!\n\n"
            "Please confirm this email to activate your children's accounts:\n"
            f"{verify_url}\n\n"
            "If you didn't create this account, you can ignore this email."
        )
        try:
            self._ses().send_email(  # type: ignore[attr-defined]
                Source=self._sender,
                Destination={"ToAddresses": [to_email]},
                Message={
                    "Subject": {"Data": subject},
                    "Body": {"Text": {"Data": body_text}},
                },
            )
        except Exception:  # noqa: BLE001 — delivery is best-effort; never break signup.
            _log.warning(
                "SES verification email to %s failed; parent can request a resend", to_email
            )


def default_email_sender() -> EmailSender:
    """Return the SES sender when ``SES_SENDER`` is configured, else the logging fallback."""
    sender = os.environ.get("SES_SENDER", "").strip()
    if sender:
        return SesEmailSender(sender=sender, region=os.environ.get("AWS_REGION") or None)
    return LoggingEmailSender()
