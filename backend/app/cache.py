"""In-process TTL cache.

Enough for a single instance. The interface is deliberately the small subset
Redis also offers, so swapping the backing store is a one-file change when
this runs on more than one process.
"""
import asyncio
import time
from typing import Any, Awaitable, Callable

_store: dict[str, tuple[float, Any]] = {}
_locks: dict[str, asyncio.Lock] = {}


async def get_or_set(key: str, ttl: float, producer: Callable[[], Awaitable[Any]]) -> Any:
    now = time.monotonic()
    hit = _store.get(key)
    if hit and hit[0] > now:
        return hit[1]

    # One in-flight producer per key, so a cold cache under load doesn't fan
    # out N identical upstream calls.
    lock = _locks.setdefault(key, asyncio.Lock())
    async with lock:
        hit = _store.get(key)
        if hit and hit[0] > time.monotonic():
            return hit[1]
        value = await producer()
        _store[key] = (time.monotonic() + ttl, value)
        return value


def invalidate(prefix: str = "") -> int:
    keys = [k for k in _store if k.startswith(prefix)]
    for k in keys:
        _store.pop(k, None)
    return len(keys)
