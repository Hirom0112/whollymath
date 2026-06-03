"""Shared fixtures for the API contract tests (Slice auth/parent-child S3).

The auth routes (parent signup/login, child login) carry a per-IP rate limiter whose
counters are PROCESS-GLOBAL. The in-process ASGI test client always presents the same
client host ("testclient"), so without a reset every test in the process would share one
bucket and later tests would spuriously 429. This autouse fixture clears all limiter state
before each test, keeping tests independent (the limiter itself is covered directly in
test_rate_limit.py).
"""

from __future__ import annotations

import pytest
from app.api.rate_limit import reset_all


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    reset_all()
