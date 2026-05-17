from redis.asyncio import Redis


async def bump_version(redis: Redis, key: str) -> int:
    return int(await redis.incr(f"cache_version:{key}"))


async def get_version(redis: Redis, key: str) -> int:
    val = await redis.get(f"cache_version:{key}")
    return int(val) if val else 0
