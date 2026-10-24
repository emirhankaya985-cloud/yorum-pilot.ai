"""Periodic and startup cleanup of expired cached reviews and derived drafts."""
import asyncio
import logging
from contextlib import suppress
from .db import SessionLocal
from .lifecycle import purge_expired
log = logging.getLogger(__name__)

def cleanup_once() -> int:
    with SessionLocal() as db:
        return purge_expired(db)

async def cleanup_loop(interval_seconds: float = 21600) -> None:
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await asyncio.to_thread(cleanup_once)
        except Exception:
            log.exception('Periodic review TTL cleanup failed')

async def stop_cleanup(task: asyncio.Task) -> None:
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
