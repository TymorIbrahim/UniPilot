"""Delete the accounts the Playwright suite leaves behind, and their data.

    python scripts/purge_e2e_test_users.py            # dry run, the default
    python scripts/purge_e2e_test_users.py --apply

## Why this exists

The E2E suite registers real accounts against the shared database and never
cleans up. Measured 2026-08-29 on `unipilot_python`:

    users              1,548 total  →    147 real,  1,401 @example.com  (90.5%)
    student_profiles   1,110 total  →    137 real,    945 test
    completed_courses    577 rows   →    265 real,    312 test

That does two kinds of damage.

**It makes every data-quality figure fiction.** "462 of 971 profiles point at a
deleted degree program" is 9 of 137 once test accounts are excluded, and the
"cohort of 179 sharing one orphan id" was the suite reusing a degreeId rather
than a damaged student cohort.

**It makes the suite non-deterministic.** Three full runs on identical code gave
4 failed, 0 failed, then 3 failed, with different tests each time; the failing
tests passed in isolation. Each run starts from a dirtier state than the last.

## What makes this safe to run

Deleting users is the most destructive thing in this repo, so the selection is
narrow and checked rather than trusted:

- only addresses ending `@example.com`, which is a reserved documentation domain
  (RFC 2606) and cannot be a real person's address;
- every selected address is re-validated individually before anything is
  deleted, so a regex that matched too much cannot slip through;
- the run aborts if the selection would exceed `--max-fraction` of all users
  (default 0.95), which catches a mis-scoped filter before it empties the table;
- dry run by default, and it prints what it found either way.

## What it does NOT do

It does not touch `courses`, `course_offerings`, `degree_programs` or anything
else in the catalog -- only per-user records keyed by a deleted user's `userId`.

It is deliberately NOT wired into the Playwright global setup. A cleanup step
that runs automatically against whatever database happens to be configured is a
worse hazard than the debris it removes; run it deliberately, or from CI where
the database is known to be disposable.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

# RFC 2606 reserves example.com for documentation. Nobody receives mail there,
# which is why the suite uses it and why it is safe to key deletion on.
TEST_EMAIL = re.compile(r"@example\.com$", re.IGNORECASE)
TEST_EMAIL_QUERY = {"email": {"$regex": r"@example\.com$", "$options": "i"}}

# Collections holding per-user rows, keyed by `userId`.
USER_OWNED = (
    "student_profiles",
    "completed_courses",
    "semester_plans",
    "academic_risks",
    "ai_recommendations",
    "advisor_conversations",
    "moodle_grades",
    "moodle_deadlines",
    "outlook_oauth_tokens",
)


async def purge(
    database: AsyncIOMotorDatabase, *, apply: bool, max_fraction: float
) -> int:
    total_users = await database["users"].count_documents({})
    candidates = await database["users"].find(
        TEST_EMAIL_QUERY, {"_id": 1, "email": 1}
    ).to_list(None)

    # Re-check every address individually. The regex selected them; this decides.
    selected, rejected = [], []
    for user in candidates:
        (selected if TEST_EMAIL.search(str(user.get("email") or "")) else rejected).append(user)

    print("database    : %s" % database.name)
    print("users total : %d" % total_users)
    print("selected    : %d  (%.1f%% of all users)"
          % (len(selected), 100.0 * len(selected) / total_users if total_users else 0))
    if rejected:
        print("REJECTED    : %d matched the query but failed re-validation" % len(rejected))
        return 1

    if not selected:
        print("\nNothing to purge.")
        return 0

    fraction = len(selected) / total_users if total_users else 0
    if fraction > max_fraction:
        print(
            "\nABORTED: the selection is %.1f%% of all users, above the %.0f%% ceiling.\n"
            "That is more likely a mis-scoped filter than a real result. Raise\n"
            "--max-fraction deliberately if the database really is that disposable."
            % (100 * fraction, 100 * max_fraction)
        )
        return 1

    ids = [u["_id"] for u in selected]
    print("\n%-26s %10s" % ("collection", "rows"))
    print("-" * 38)
    planned = {}
    for name in USER_OWNED:
        n = await database[name].count_documents({"userId": {"$in": ids}})
        planned[name] = n
        if n:
            print("%-26s %10d" % (name, n))
    print("%-26s %10d" % ("users", len(ids)))

    if not apply:
        print("\nDry run. Re-run with --apply to delete.")
        return 0

    for name, n in planned.items():
        if n:
            await database[name].delete_many({"userId": {"$in": ids}})
    result = await database["users"].delete_many({"_id": {"$in": ids}})
    print("\nDeleted %d users and their records." % result.deleted_count)

    left = await database["users"].count_documents(TEST_EMAIL_QUERY)
    remaining = await database["users"].count_documents({})
    print("verify: %d test users left, %d users remain" % (left, remaining))
    return 0 if left == 0 else 1


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--max-fraction", type=float, default=0.95)
    parser.add_argument("--mongo-uri", default=os.environ.get("MONGO_URI"))
    parser.add_argument("--mongo-db", default=os.environ.get("MONGO_DB", "unipilot"))
    args = parser.parse_args()

    if not args.mongo_uri:
        raise SystemExit("MONGO_URI is not set and --mongo-uri was not given.")

    database = AsyncIOMotorClient(args.mongo_uri)[args.mongo_db]
    raise SystemExit(await purge(database, apply=args.apply, max_fraction=args.max_fraction))


if __name__ == "__main__":
    asyncio.run(main())
