"""Wait for MongoDB to accept commands before anything at startup needs it.

`docker-compose.yml` expresses the API's dependency on MongoDB with
`depends_on` + a healthcheck, but that ordering is only honoured by
`docker compose up` on a developer machine. The runtime that hosts the live
demo builds from the compose file and then launches the containers with no
ordering guarantee at all, so the API can very well come up first.

Without this wait the first Mongo call in `lifespan` -- seeding the demo
catalog -- raises, uvicorn exits before it ever binds a port, and the
container crash-loops until a restart happens to land after MongoDB is
listening. Visitors see a dead site for as long as that takes. Retrying here
turns a race into a short, quiet delay.
"""

from __future__ import annotations

import asyncio
import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger(__name__)

# 30 x 2s = up to a minute, comfortably longer than a cold MongoDB takes to
# start while still failing the container in a bounded time if the database
# is genuinely misconfigured rather than merely slow.
STARTUP_PING_ATTEMPTS = 30
STARTUP_PING_DELAY_SECONDS = 2.0


class DatabaseUnavailableError(RuntimeError):
    """MongoDB did not become reachable within the startup budget."""


async def wait_for_database(
    database: AsyncIOMotorDatabase,
    *,
    attempts: int = STARTUP_PING_ATTEMPTS,
    delay_seconds: float = STARTUP_PING_DELAY_SECONDS,
) -> None:
    """Ping `database` until it answers, or raise once the attempts run out."""
    last_error: BaseException | None = None

    for attempt in range(1, attempts + 1):
        try:
            await database.command("ping")
        except Exception as error:  # noqa: BLE001 -- any driver error means "not ready yet"
            last_error = error
            if attempt == attempts:
                break
            logger.warning(
                "MongoDB not reachable yet (attempt %d/%d), retrying in %.1fs: %s",
                attempt,
                attempts,
                delay_seconds,
                error,
            )
            await asyncio.sleep(delay_seconds)
            continue

        if attempt > 1:
            logger.info("MongoDB became reachable after %d attempts", attempt)
        return

    raise DatabaseUnavailableError(
        f"MongoDB did not become reachable after {attempts} attempts "
        f"({attempts * delay_seconds:.0f}s)."
    ) from last_error
