"""Redis-backed AI job queue store (async AI pipeline)."""

from __future__ import annotations

from typing import Protocol

from app.config import get_settings
from app.db.redis_client import get_redis_client


class AiJobQueueStore(Protocol):
    async def enqueue(self, job_id: str) -> None: ...


class InMemoryAiJobQueueStore:
    def __init__(self) -> None:
        self.enqueued: list[str] = []

    async def enqueue(self, job_id: str) -> None:
        self.enqueued.append(job_id)

    def reset(self) -> None:
        self.enqueued.clear()


class RedisAiJobQueueStore:
    async def enqueue(self, job_id: str) -> None:
        client = get_redis_client()
        if client is None:
            raise RuntimeError("Redis is required for AI job queueing")

        settings = get_settings()
        await client.lpush(settings.worker_queue_name, job_id)


_in_memory_store = InMemoryAiJobQueueStore()
_store_override: AiJobQueueStore | None = None


def set_ai_job_queue_store(store: AiJobQueueStore | None) -> None:
    global _store_override
    _store_override = store


def reset_in_memory_ai_job_queue_store() -> None:
    _in_memory_store.reset()


def get_in_memory_ai_job_queue_store() -> InMemoryAiJobQueueStore:
    return _in_memory_store


def resolve_ai_job_queue_store() -> AiJobQueueStore:
    if _store_override is not None:
        return _store_override

    settings = get_settings()
    if settings.environment == "test" or not settings.redis_url:
        return _in_memory_store

    return RedisAiJobQueueStore()
