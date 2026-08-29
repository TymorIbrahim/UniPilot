"""The safety properties of the E2E-debris purge.

Deleting users is the most destructive operation in this repo, so what is tested
here is not "does it delete" but "what stops it deleting the wrong thing". Each
test corresponds to one guard, and each guard exists because the failure it
prevents is unrecoverable.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from bson import ObjectId
from mongomock_motor import AsyncMongoMockClient

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "purge_e2e_test_users.py"
_spec = importlib.util.spec_from_file_location("purge_e2e_test_users", _SCRIPT)
purge_module = importlib.util.module_from_spec(_spec)
sys.modules["purge_e2e_test_users"] = purge_module
_spec.loader.exec_module(purge_module)


async def _seed(database, *, real: int, test: int) -> None:
    for i in range(real):
        uid = ObjectId()
        await database["users"].insert_one({"_id": uid, "email": f"student{i}@technion.ac.il"})
        await database["student_profiles"].insert_one({"userId": uid, "programSlug": "x"})
        await database["completed_courses"].insert_one({"userId": uid, "grade": 90})
    for i in range(test):
        uid = ObjectId()
        await database["users"].insert_one({"_id": uid, "email": f"e2e-{i}@example.com"})
        await database["student_profiles"].insert_one({"userId": uid})
        await database["completed_courses"].insert_one({"userId": uid, "grade": 80})


@pytest.fixture
def database():
    return AsyncMongoMockClient()["purge_test"]


class TestItOnlySelectsReservedTestAddresses:
    @pytest.mark.asyncio
    async def test_a_dry_run_deletes_nothing(self, database):
        await _seed(database, real=5, test=20)
        await purge_module.purge(database, apply=False, max_fraction=0.95)
        assert await database["users"].count_documents({}) == 25
        assert await database["completed_courses"].count_documents({}) == 25

    @pytest.mark.asyncio
    async def test_real_accounts_survive(self, database):
        await _seed(database, real=5, test=20)
        await purge_module.purge(database, apply=True, max_fraction=0.95)
        remaining = await database["users"].distinct("email")
        assert len(remaining) == 5
        assert all(e.endswith("@technion.ac.il") for e in remaining)

    @pytest.mark.asyncio
    async def test_their_records_go_with_them(self, database):
        await _seed(database, real=5, test=20)
        await purge_module.purge(database, apply=True, max_fraction=0.95)
        assert await database["completed_courses"].count_documents({}) == 5
        assert await database["student_profiles"].count_documents({}) == 5

    @pytest.mark.asyncio
    async def test_a_lookalike_domain_is_not_selected(self, database):
        """`example.com.attacker.net` ends with neither, and `notexample.com`
        would match a careless substring check. RFC 2606 reserves exactly
        `example.com`, and only a trailing match is safe."""
        await database["users"].insert_one({"email": "someone@notexample.com"})
        await database["users"].insert_one({"email": "someone@example.com.other.net"})
        await database["users"].insert_one({"email": "real@example.com"})
        await purge_module.purge(database, apply=True, max_fraction=0.99)
        left = sorted(await database["users"].distinct("email"))
        assert left == ["someone@example.com.other.net", "someone@notexample.com"]


class TestTheCeiling:
    @pytest.mark.asyncio
    async def test_it_aborts_when_the_selection_is_implausibly_large(self, database):
        """A filter that selects nearly everything is far more likely to be a
        mistake than a real result, and there is no undo."""
        await _seed(database, real=1, test=99)
        rc = await purge_module.purge(database, apply=True, max_fraction=0.5)
        assert rc == 1
        assert await database["users"].count_documents({}) == 100

    @pytest.mark.asyncio
    async def test_the_ceiling_can_be_raised_deliberately(self, database):
        await _seed(database, real=1, test=99)
        rc = await purge_module.purge(database, apply=True, max_fraction=0.999)
        assert rc == 0
        assert await database["users"].count_documents({}) == 1


class TestTheCatalogIsNeverTouched:
    @pytest.mark.asyncio
    async def test_catalog_collections_are_left_alone(self, database):
        await _seed(database, real=2, test=10)
        await database["courses"].insert_one({"courseNumber": "00940412"})
        await database["degree_programs"].insert_one({"name": "ISE"})
        await purge_module.purge(database, apply=True, max_fraction=0.95)
        assert await database["courses"].count_documents({}) == 1
        assert await database["degree_programs"].count_documents({}) == 1


@pytest.mark.asyncio
async def test_an_empty_database_is_a_no_op(database):
    assert await purge_module.purge(database, apply=True, max_fraction=0.95) == 0
