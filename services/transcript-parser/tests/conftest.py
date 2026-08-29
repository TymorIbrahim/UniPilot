"""Keep the suite hermetic against whatever the environment happens to set.

`Settings` reads `INTERNAL_SERVICE_TOKEN` from the process environment, and the
service image sets one. So the route tests passed on a developer machine, where
nothing exports it and `require_internal_service_token` returns early, and
failed inside the container with 401 on five tests that assert 200/400/422 --
the same suite disagreeing with itself depending on where it ran.

Clearing it here makes the auth path an explicit choice: a test that wants to
exercise the token sets one itself.
"""

from __future__ import annotations

import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def unset_internal_service_token(monkeypatch):
    monkeypatch.delenv("INTERNAL_SERVICE_TOKEN", raising=False)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
