"""The API must outlast a MongoDB that isn't listening yet."""

from __future__ import annotations

import pytest

from app.db.startup import DatabaseUnavailableError, wait_for_database


class _FakeDatabase:
    """Fails `command("ping")` for the first `failures` calls, then succeeds."""

    def __init__(self, failures: int) -> None:
        self.failures = failures
        self.ping_count = 0

    async def command(self, name: str):
        assert name == "ping"
        self.ping_count += 1
        if self.ping_count <= self.failures:
            raise ConnectionError("mongo is not listening yet")
        return {"ok": 1}


@pytest.fixture
def no_sleep(monkeypatch):
    """Collect the backoff delays instead of actually waiting them out."""
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr("app.db.startup.asyncio.sleep", fake_sleep)
    return slept


async def test_a_database_that_is_already_up_is_not_waited_on(no_sleep):
    database = _FakeDatabase(failures=0)

    await wait_for_database(database, attempts=5, delay_seconds=2.0)

    assert database.ping_count == 1
    assert no_sleep == []


async def test_a_database_that_starts_late_is_waited_for(no_sleep):
    database = _FakeDatabase(failures=3)

    await wait_for_database(database, attempts=5, delay_seconds=2.0)

    assert database.ping_count == 4
    assert no_sleep == [2.0, 2.0, 2.0]


async def test_a_database_that_never_comes_up_raises_after_the_last_attempt(no_sleep):
    database = _FakeDatabase(failures=99)

    with pytest.raises(DatabaseUnavailableError) as excinfo:
        await wait_for_database(database, attempts=3, delay_seconds=0.5)

    assert database.ping_count == 3
    # Two sleeps, not three: nothing waits after the final attempt fails.
    assert no_sleep == [0.5, 0.5]
    assert "3 attempts" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, ConnectionError)


async def test_the_underlying_error_is_reported_not_swallowed(no_sleep):
    database = _FakeDatabase(failures=99)

    with pytest.raises(DatabaseUnavailableError) as excinfo:
        await wait_for_database(database, attempts=1, delay_seconds=0.5)

    assert "mongo is not listening yet" in str(excinfo.value.__cause__)
