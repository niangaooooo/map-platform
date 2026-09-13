"""Redis 客户端，用于 WebSocket Pub/Sub、编辑锁、在线状态、限流。

本地开发无 Redis 时，将 REDIS_URL 设为 `fakeredis://local` 即使用纯 Python 内存实现
（API 完全兼容，适合单进程本地试用）。
"""
import redis.asyncio as aioredis

from app.core.config import get_settings

_redis: aioredis.Redis | None = None


def get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        url = get_settings().REDIS_URL
        if url.startswith("fakeredis://"):
            import fakeredis.aioredis

            _redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
        else:
            _redis = aioredis.from_url(url, decode_responses=True)
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None
