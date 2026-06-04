"""Outbound notifications (email). The ONLY place that sends mail.

Used for the COPPA parental-email verification (Slice auth/parent-child). Real
delivery via AWS SES (boto3); a logging no-op fallback when SES is unconfigured
(local dev/test). Nothing here is on the turn loop (invariant 8).
"""
