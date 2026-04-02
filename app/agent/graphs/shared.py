import asyncio

from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from app.config import settings

_checkpointer = None
_checkpointer_loop = None


async def get_checkpointer() -> AsyncRedisSaver:
    """Return a Redis checkpointer, recreating if the event loop has changed.

    Celery workers call asyncio.run() for each task, which creates a new event
    loop.  Connections from the previous loop are closed ('Buffer is closed').
    We detect loop changes and recreate the connection to avoid this.
    """
    global _checkpointer, _checkpointer_loop
    current_loop = asyncio.get_event_loop()
    if _checkpointer is None or _checkpointer_loop is not current_loop:
        _checkpointer_loop = current_loop
        cm = AsyncRedisSaver.from_conn_string(
            settings.redis_url,
            ttl={"default_ttl": 1440},
        )
        _checkpointer = await cm.__aenter__()
        await _checkpointer.asetup()
    return _checkpointer
