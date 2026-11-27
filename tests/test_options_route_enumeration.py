# SPDX-FileCopyrightText: Copyright contributors to the OpenAN project
# SPDX-License-Identifier: Apache-2.0

"""#204: unauthenticated OPTIONS must not enumerate protected routes.

Runs through the real application middleware stack, because the fix relies
on CORSMiddleware consuming genuine preflights before the router.
"""

import pytest
from fastapi.testclient import TestClient

from orchestrate.server.frontend_support_server import app

client = TestClient(app)

EXISTING = "/rest/v1/orchestrate/execute"
MISSING = "/rest/v1/orchestrate/nonexistent123"
PREFLIGHT = {"Origin": "https://portal.example", "Access-Control-Request-Method": "GET"}


@pytest.fixture(autouse=True)
def _auth_enabled(account_session):
    """Real middleware with account auth configured; requests stay anonymous."""


@pytest.mark.parametrize("path", [EXISTING, MISSING, "/psops", "/api/v1/executions"])
def test_plain_options_is_rejected_without_login(path):
    response = client.options(path)
    assert response.status_code == 401
    assert "allow" not in response.headers


def test_plain_options_cannot_tell_existing_from_missing_routes():
    existing, missing = client.options(EXISTING), client.options(MISSING)
    assert (existing.status_code, existing.json()) == (missing.status_code, missing.json())


def test_cors_preflight_still_answered_without_login():
    response = client.options(EXISTING, headers=PREFLIGHT)
    assert response.status_code == 200
    assert "access-control-allow-methods" in response.headers
    assert "allow" not in response.headers


def test_cors_preflight_cannot_tell_existing_from_missing_routes():
    existing = client.options(EXISTING, headers=PREFLIGHT)
    missing = client.options(MISSING, headers=PREFLIGHT)
    assert existing.status_code == missing.status_code == 200
    assert existing.content == missing.content
    assert "allow" not in missing.headers


def test_authenticated_options_behaves_as_before(account_session):
    """A logged-in caller already sees the API; routing semantics are unchanged."""
    response = client.options(EXISTING, headers=account_session)
    assert response.status_code == 405
