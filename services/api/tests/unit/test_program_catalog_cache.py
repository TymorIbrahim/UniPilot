"""Unit tests for caching the program-scoped half of a progress computation."""

from __future__ import annotations

from bson import ObjectId
import pytest

from app.services import graduation_progress_service as service


@pytest.fixture
def catalog(monkeypatch):
    """Program-scoped documents, plus a count of how often Mongo was asked."""
    # Stable ids, as Mongo returns: a fresh ObjectId per call would make two
    # uncached reads differ for a reason the code is not responsible for.
    ids = {name: ObjectId() for name in ("core", "pool", "matrix")}
    state = {"calls": 0, "cache": {}}

    async def _requirements(database, program_code, include_internal=False):
        state["calls"] += 1
        return [{"_id": ids["core"], "requirementGroupId": f"{program_code}:core"}]

    async def _pools(database, program_code):
        state["calls"] += 1
        return [{"_id": ids["pool"], "requirementGroupId": f"{program_code}:pool"}]

    async def _matrix(database, program_code):
        state["calls"] += 1
        return [{"_id": ids["matrix"], "requirementGroupId": f"{program_code}:matrix"}]

    async def _enrich(database, *, program_code, pool_documents):
        state["calls"] += 1
        return pool_documents

    async def _get(key):
        return state["cache"].get(key)

    async def _set(key, value):
        state["cache"][key] = value

    monkeypatch.setattr(
        service.catalog_repository, "list_hard_requirements_for_program", _requirements
    )
    monkeypatch.setattr(service.catalog_repository, "list_course_pools_for_program", _pools)
    monkeypatch.setattr(
        service.catalog_repository, "list_semester_matrix_rules_for_program", _matrix
    )
    monkeypatch.setattr(service, "enrich_pool_documents_for_program", _enrich)
    monkeypatch.setattr(service, "get_cached_json", _get)
    monkeypatch.setattr(service, "set_cached_json", _set)
    return state


@pytest.mark.asyncio
async def test_a_second_student_in_the_program_asks_mongo_nothing(catalog) -> None:
    """These documents are identical for everyone in the program and change
    only on promotion, which is what makes them safe to share."""
    await service._load_program_catalog_context(object(), "009118-1-000")
    calls_after_first = catalog["calls"]

    await service._load_program_catalog_context(object(), "009118-1-000")

    assert calls_after_first == 4
    assert catalog["calls"] == calls_after_first


@pytest.mark.asyncio
async def test_a_different_program_is_fetched_separately(catalog) -> None:
    await service._load_program_catalog_context(object(), "009118-1-000")
    await service._load_program_catalog_context(object(), "013043-1-000")

    assert catalog["calls"] == 8


@pytest.mark.asyncio
async def test_a_cold_read_returns_exactly_what_a_warm_one_does(catalog) -> None:
    """Serialising stringifies ObjectIds. If a miss returned raw documents and a
    hit returned decoded ones, behaviour would depend on cache state -- and the
    test suite, which runs with the cache off, would never see production's
    shape."""
    cold = await service._load_program_catalog_context(object(), "009118-1-000")
    warm = await service._load_program_catalog_context(object(), "009118-1-000")

    assert cold == warm
    assert isinstance(cold["hardRequirements"][0]["_id"], str)


@pytest.mark.asyncio
async def test_the_shape_holds_even_with_no_cache_available(catalog, monkeypatch) -> None:
    async def _no_cache(key):
        return None

    async def _discard(key, value):
        return None

    monkeypatch.setattr(service, "get_cached_json", _no_cache)
    monkeypatch.setattr(service, "set_cached_json", _discard)

    first = await service._load_program_catalog_context(object(), "009118-1-000")
    second = await service._load_program_catalog_context(object(), "009118-1-000")

    assert first == second
    assert isinstance(first["poolDocuments"][0]["_id"], str)


@pytest.mark.asyncio
async def test_the_key_is_versioned_so_an_old_shape_is_ignored(catalog) -> None:
    await service._load_program_catalog_context(object(), "009118-1-000")

    key = next(iter(catalog["cache"]))
    assert key.endswith(f":v{service.PROGRAM_CATALOG_CACHE_VERSION}")
    assert "009118-1-000" in key
