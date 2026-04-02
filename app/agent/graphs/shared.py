from langgraph.checkpoint.redis.aio import AsyncRedisSaver

from app.config import settings

_checkpointer = None


async def get_checkpointer() -> AsyncRedisSaver:
    global _checkpointer
    if _checkpointer is None:
        _checkpointer = AsyncRedisSaver.from_conn_string(
            settings.redis_url,
            ttl={"default_ttl": 1440},
        )
        await _checkpointer.asetup()
    return _checkpointer
