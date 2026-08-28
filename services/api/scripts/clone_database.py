"""Clone a MongoDB database on the same cluster, documents and structure alike.

    python scripts/clone_database.py --source unipilot_python --target unipilot_app
    python scripts/clone_database.py --source unipilot_python --target unipilot_app --apply

DRY RUN BY DEFAULT. Without `--apply` it reports what it would copy and writes
nothing.

## Why this exists

`TymorIbrahim/unipilot-agent` was submitted as coursework and is being graded.
Its `scripts/seed.py` reads `unipilot_python` on the shared Atlas cluster to
rebuild the Supabase mirror the deployed agent serves from. UniPilot's own
services read and WRITE that same database.

So a change made while developing UniPilot -- a repaired transcript row, a new
validator, a dropped collection -- lands in the database a grader's re-seed
would read. The deployed agent reads Supabase and is insulated from this in
practice, but "in practice" is not a property to rely on during grading.

This clone gives UniPilot its own copy. The original keeps its name, so the
agent repo's `.env` needs no edit and its submitted state stays untouched.

## What is copied, and what deliberately is not

Documents, indexes (including `unique` and `partialFilterExpression`) and any
`$jsonSchema` validator, because a copy that silently drops constraints is worse
than no copy -- it looks like the original and accepts data the original would
have flagged.

`_id` values are preserved. They are not decorative here: `completed_courses.
courseId` and `student_profiles.degreeId` are ObjectId references into
`courses` and `degree_programs`, and regenerating ids would break every one of
them. See the dangling-reference work -- 462 profiles already point at programs
that no longer exist, and that number must not change because of a copy.

The `_id_` index is skipped because Mongo creates it itself and rejects an
attempt to build it again.
"""

from __future__ import annotations

import argparse
import asyncio
import os
from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

BATCH = 1000


async def _collection_plan(source: AsyncIOMotorDatabase, name: str) -> dict[str, Any]:
    info = await (await source.list_collections(filter={"name": name})).to_list(1)
    options = (info[0].get("options") or {}) if info else {}
    indexes = await source[name].index_information()
    return {
        "name": name,
        "documents": await source[name].count_documents({}),
        "validator": options.get("validator"),
        "validation_level": options.get("validationLevel"),
        "validation_action": options.get("validationAction"),
        "indexes": {k: v for k, v in indexes.items() if k != "_id_"},
    }


async def _copy_documents(
    source: AsyncIOMotorDatabase, target: AsyncIOMotorDatabase, name: str
) -> int:
    copied = 0
    batch: list[dict[str, Any]] = []
    async for document in source[name].find({}):
        batch.append(document)
        if len(batch) >= BATCH:
            await target[name].insert_many(batch, ordered=False)
            copied += len(batch)
            batch = []
    if batch:
        await target[name].insert_many(batch, ordered=False)
        copied += len(batch)
    return copied


async def _copy_indexes(target: AsyncIOMotorDatabase, name: str, indexes: dict) -> int:
    built = 0
    for index_name, spec in indexes.items():
        keys = [(field, direction) for field, direction in spec["key"]]
        kwargs: dict[str, Any] = {"name": index_name}
        for option in ("unique", "sparse", "partialFilterExpression", "expireAfterSeconds"):
            if option in spec:
                kwargs[option] = spec[option]
        await target[name].create_index(keys, **kwargs)
        built += 1
    return built


async def clone(
    client: AsyncIOMotorClient, source_name: str, target_name: str, *, apply: bool
) -> None:
    source = client[source_name]
    target = client[target_name]

    existing = await client.list_database_names()
    if target_name in existing and apply:
        names = await target.list_collection_names()
        if names:
            raise SystemExit(
                f"{target_name} already exists and has {len(names)} collection(s). "
                "Refusing to write into a non-empty target -- drop it first, or pick "
                "another name."
            )

    names = sorted(await source.list_collection_names())
    print("source : %s  (%d collections)" % (source_name, len(names)))
    print("target : %s%s" % (target_name, "" if apply else "   [DRY RUN -- nothing written]"))
    print()
    print("%-30s %9s %7s  %s" % ("collection", "docs", "idx", "validator"))
    print("-" * 60)

    total_docs = total_idx = 0
    for name in names:
        plan = await _collection_plan(source, name)
        total_docs += plan["documents"]
        total_idx += len(plan["indexes"])
        print(
            "%-30s %9d %7d  %s"
            % (name, plan["documents"], len(plan["indexes"]), "yes" if plan["validator"] else "-")
        )
        if not apply:
            continue

        if plan["validator"]:
            await target.create_collection(
                name,
                validator=plan["validator"],
                validationLevel=plan["validation_level"] or "strict",
                validationAction=plan["validation_action"] or "error",
            )
        if plan["documents"]:
            await _copy_documents(source, target, name)
        if plan["indexes"]:
            await _copy_indexes(target, name, plan["indexes"])

    print("-" * 60)
    print("%-30s %9d %7d" % ("TOTAL", total_docs, total_idx))
    if not apply:
        print("\nDry run. Re-run with --apply to write.")


async def verify(client: AsyncIOMotorClient, source_name: str, target_name: str) -> bool:
    """Compare the copy to the original, collection by collection."""
    source, target = client[source_name], client[target_name]
    names = sorted(await source.list_collection_names())
    print("\n%-30s %9s %9s  %s" % ("collection", "source", "target", "match"))
    print("-" * 62)
    ok = True
    for name in names:
        a = await source[name].count_documents({})
        b = await target[name].count_documents({})
        ia = len(await source[name].index_information())
        ib = len(await target[name].index_information())
        good = a == b and ia == ib
        ok = ok and good
        print("%-30s %9d %9d  %s" % (name, a, b, "ok" if good else "MISMATCH (idx %d/%d)" % (ia, ib)))
    return ok


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--mongo-uri", default=os.environ.get("MONGO_URI"))
    args = parser.parse_args()

    if not args.mongo_uri:
        raise SystemExit("MONGO_URI is not set and --mongo-uri was not given.")
    if args.source == args.target:
        raise SystemExit("source and target must differ.")

    client = AsyncIOMotorClient(args.mongo_uri)
    if not args.verify_only:
        await clone(client, args.source, args.target, apply=args.apply)
    if args.apply or args.verify_only:
        ok = await verify(client, args.source, args.target)
        print("\n%s" % ("Copy matches the source." if ok else "COPY DOES NOT MATCH -- do not switch over."))


if __name__ == "__main__":
    asyncio.run(main())
