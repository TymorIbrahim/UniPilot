#!/usr/bin/env python3
"""Load CheeseFork course ratings into the `course_ratings` collection.

    python scripts/fetch_cheesefork_feedback.py --limit 20        # dry run
    python scripts/fetch_cheesefork_feedback.py --apply

Reads the public `courseFeedback` collection -- the same data any visitor sees
on cheesefork.cf, fetched over the REST API with the web key the site ships --
and stores per-course aggregates only. See `app/sources/cheesefork_feedback.py`
for what is deliberately not stored.

Only courses already in our catalog are requested, one at a time with a small
delay: this is someone else's service and there is no reason to hammer it.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

import httpx
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.sources.cheesefork_feedback import (  # noqa: E402
    document_url,
    parse_feedback_document,
)

PROJECT = "cheesefork-de9af"
WEB_API_KEY = "AIzaSyAfKPyTM83mkLgdQTdx9YS9UXywiswwIYI"
RATINGS_COLLECTION = "course_ratings"
REQUEST_DELAY_SECONDS = 0.15


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write to Mongo")
    parser.add_argument("--limit", type=int, default=0, help="stop after N courses")
    args = parser.parse_args()

    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_uri)
    database = client[settings.mongo_db_name]

    numbers = sorted(
        {
            str(document["courseNumber"])
            async for document in database[settings.production_courses_collection].find(
                {"courseNumber": {"$exists": True}}, {"courseNumber": 1}
            )
        }
    )
    if args.limit:
        numbers = numbers[: args.limit]
    print(f"catalog courses to ask about: {len(numbers)}")

    found: list = []
    async with httpx.AsyncClient(timeout=30.0) as http:
        for index, number in enumerate(numbers, start=1):
            try:
                response = await http.get(document_url(PROJECT, number, WEB_API_KEY))
            except httpx.HTTPError as exc:
                print(f"  {number}: {type(exc).__name__}")
                continue
            if response.status_code == 404:
                continue  # no feedback for this course, which is ordinary
            if response.status_code != 200:
                print(f"  {number}: HTTP {response.status_code}")
                continue
            rating = parse_feedback_document(response.json(), course_number=number)
            if rating is not None:
                found.append(rating)
            if index % 100 == 0:
                print(f"  ...{index}/{len(numbers)} asked, {len(found)} with ratings")
            time.sleep(REQUEST_DELAY_SECONDS)

    print(f"\ncourses with usable ratings: {len(found)}")
    if not args.apply:
        print("DRY RUN -- pass --apply to write. Sample:")
        for rating in found[:8]:
            print(f"  {rating.as_public_dict()}")
        return 0

    collection = database[RATINGS_COLLECTION]
    await collection.create_index("courseNumber", unique=True)
    for rating in found:
        await collection.update_one(
            {"courseNumber": rating.course_number},
            {"$set": {**rating.as_public_dict(), "source": "cheesefork-courseFeedback"}},
            upsert=True,
        )
    print(f"written to `{RATINGS_COLLECTION}`: {len(found)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
