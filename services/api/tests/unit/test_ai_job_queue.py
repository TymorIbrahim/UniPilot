"""Unit tests for app/services/ai_job_queue.py — targets 100% branch coverage."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import app.services.ai_job_queue as queue_module
from app.config import Settings
from app.services.ai_job_queue import (
    InMemoryAiJobQueueStore,
    RedisAiJobQueueStore,
    get_in_memory_ai_job_queue_store,
    reset_in_memory_ai_job_queue_store,
    resolve_ai_job_queue_store,
    set_ai_job_queue_store,
)


def _settings(**kwargs) -> Settings:
    defaults = dict(environment="development", jwt_secret="test-secret")
    defaults.update(kwargs)
    return Settings(**defaults)


# ---------------------------------------------------------------------------
# InMemoryAiJobQueueStore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_memory_store_records_enqueued_job_id() -> None:
    store = InMemoryAiJobQueueStore()
    await store.enqueue("job-1")
    await store.enqueue("job-2")
    assert store.enqueued == ["job-1", "job-2"]


def test_in_memory_store_reset_clears_enqueued() -> None:
    store = InMemoryAiJobQueueStore()
    store.enqueued.append("job-1")
    store.reset()
    assert store.enqueued == []


# ---------------------------------------------------------------------------
# RedisAiJobQueueStore
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_redis_store_raises_when_client_is_none(monkeypatch) -> None:
    monkeypatch.setattr(queue_module, "get_redis_client", lambda: None)
    store = RedisAiJobQueueStore()

    with pytest.raises(RuntimeError, match="Redis is required"):
        await store.enqueue("job-1")


@pytest.mark.asyncio
async def test_redis_store_pushes_job_id_to_configured_queue(monkeypatch) -> None:
    fake_client = AsyncMock()
    fake_client.lpush = AsyncMock()
    monkeypatch.setattr(queue_module, "get_redis_client", lambda: fake_client)
    monkeypatch.setattr(
        queue_module, "get_settings", lambda: _settings(worker_queue_name="ai_jobs")
    )

    store = RedisAiJobQueueStore()
    await store.enqueue("job-1")

    fake_client.lpush.assert_awaited_once_with("ai_jobs", "job-1")


# ---------------------------------------------------------------------------
# resolve_ai_job_queue_store / set_ai_job_queue_store / reset
# ---------------------------------------------------------------------------


def test_resolve_returns_override_when_set(monkeypatch) -> None:
    fake_store = object()
    set_ai_job_queue_store(fake_store)
    try:
        assert resolve_ai_job_queue_store() is fake_store
    finally:
        set_ai_job_queue_store(None)


def test_resolve_returns_in_memory_store_in_test_env(monkeypatch) -> None:
    monkeypatch.setattr(queue_module, "_store_override", None)
    monkeypatch.setattr(
        queue_module, "get_settings",
        lambda: _settings(environment="test", redis_url=None),
    )
    result = resolve_ai_job_queue_store()
    assert isinstance(result, InMemoryAiJobQueueStore)


def test_resolve_returns_in_memory_store_when_no_redis_url(monkeypatch) -> None:
    monkeypatch.setattr(queue_module, "_store_override", None)
    monkeypatch.setattr(
        queue_module, "get_settings",
        lambda: _settings(environment="development", redis_url=None),
    )
    result = resolve_ai_job_queue_store()
    assert isinstance(result, InMemoryAiJobQueueStore)


def test_resolve_returns_redis_store_when_redis_url_present(monkeypatch) -> None:
    monkeypatch.setattr(queue_module, "_store_override", None)
    monkeypatch.setattr(
        queue_module, "get_settings",
        lambda: _settings(environment="development", redis_url="redis://localhost:6379"),
    )
    result = resolve_ai_job_queue_store()
    assert isinstance(result, RedisAiJobQueueStore)


def test_set_ai_job_queue_store_updates_override() -> None:
    fake_store = object()
    set_ai_job_queue_store(fake_store)
    assert queue_module._store_override is fake_store
    set_ai_job_queue_store(None)
    assert queue_module._store_override is None


def test_reset_in_memory_ai_job_queue_store_clears_enqueued() -> None:
    queue_module._in_memory_store.enqueued.append("job-x")
    reset_in_memory_ai_job_queue_store()
    assert queue_module._in_memory_store.enqueued == []


def test_get_in_memory_ai_job_queue_store_returns_singleton() -> None:
    assert get_in_memory_ai_job_queue_store() is queue_module._in_memory_store
