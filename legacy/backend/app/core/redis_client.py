import logging
from typing import Optional

import redis

from app.config import settings

logger = logging.getLogger(__name__)

_client: Optional[redis.Redis] = None


def init_redis_pool() -> Optional[redis.Redis]:
    global _client
    try:
        client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password or None,
            socket_timeout=settings.redis_socket_timeout,
            decode_responses=True,
        )
        client.ping()
        _client = client
        logger.info("Redis connected: %s:%s", settings.redis_host, settings.redis_port)
        return _client
    except Exception as exc:
        logger.warning("Redis unavailable, memory-only cache active: %s", exc)
        _client = None
        return None


def get_redis_client() -> Optional[redis.Redis]:
    return _client


def close_redis_pool() -> None:
    global _client
    if _client:
        try:
            _client.close()
        except Exception:
            pass
        _client = None


def redis_is_healthy() -> bool:
    if _client is None:
        return False
    try:
        return bool(_client.ping())
    except Exception:
        return False
