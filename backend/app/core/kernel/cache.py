"""
app/core/kernel/cache.py
Cache store — Redis primary with in-memory fallback. Auto-detects Redis
via REDIS_URL; falls back silently to an in-process dict if unavailable.

Usage:
    from app.core.kernel.cache import get_cache, set_cache, cached, rate_limit

    set_cache("my_key", {"data": 123}, ttl=300)
    val = get_cache("my_key")

    @cached(ttl=60, prefix="products")
    def get_products(db): ...
"""

import hashlib
import inspect
import json
import os
import time
import uuid
from functools import wraps
from typing import Any, Optional

from loguru import logger

# ── Redis connection ──────────────────────────────────────────────────────────
_redis = None
_REDIS_URL = os.getenv("REDIS_URL")

if _REDIS_URL:
    try:
        import redis as _redis_lib
        _client = _redis_lib.from_url(_REDIS_URL, decode_responses=True, socket_timeout=2)
        _client.ping()
        _redis = _client
        logger.debug("[Cache] Redis connected ✅")
    except Exception as e:
        logger.warning(f"[Cache] Redis unavailable — using in-memory fallback: {e}")

# ── In-memory fallback ────────────────────────────────────────────────────────
_mem: dict[str, tuple[Any, float]] = {}   # key → (value, expires_at)
_MEM_MAX_SIZE = 5_000


def _mem_evict() -> None:
    """Remove expired entries; if still over limit, drop oldest by expiry."""
    now = time.time()
    expired = [k for k, (_, exp) in _mem.items() if exp <= now]
    for k in expired:
        _mem.pop(k, None)
    if len(_mem) >= _MEM_MAX_SIZE:
        overflow = len(_mem) - (_MEM_MAX_SIZE // 2)
        for k in sorted(_mem, key=lambda k: _mem[k][1])[:overflow]:
            _mem.pop(k, None)


# ── Key helpers ───────────────────────────────────────────────────────────────

def make_key(prefix: str, *args, **kwargs) -> str:
    """Build a deterministic cache key from prefix + call arguments."""
    clean_args = [a for a in args if not hasattr(a, "query")]
    clean_kwargs = {k: v for k, v in kwargs.items() if k not in ("db", "session")}
    raw = json.dumps({"a": clean_args, "k": clean_kwargs}, sort_keys=True, default=str)
    digest = hashlib.md5(raw.encode()).hexdigest()[:12]
    return f"{prefix}:{digest}"


# ── Core operations ───────────────────────────────────────────────────────────

def get_cache(key: str) -> Optional[Any]:
    if _redis:
        try:
            raw = _redis.get(key)
            return json.loads(raw) if raw else None
        except Exception as e:
            logger.warning(f"[Cache] Redis GET error: {e}")
    entry = _mem.get(key)
    if entry is None:
        return None
    value, expires_at = entry
    if time.time() > expires_at:
        _mem.pop(key, None)
        return None
    return value


def set_cache(key: str, value: Any, ttl: int = 300) -> None:
    if _redis:
        try:
            _redis.setex(key, ttl, json.dumps(value, ensure_ascii=False, default=str))
            return
        except Exception as e:
            logger.warning(f"[Cache] Redis SET error: {e}")
    if len(_mem) >= _MEM_MAX_SIZE:
        _mem_evict()
    _mem[key] = (value, time.time() + ttl)


def clear_cache(key: str) -> None:
    """Delete a single key."""
    if _redis:
        try:
            _redis.delete(key)
            return
        except Exception as e:
            logger.warning(f"[Cache] Redis DEL error: {e}")
    _mem.pop(key, None)


def invalidate_pattern(pattern: str) -> int:
    """Delete all keys matching *pattern*. Returns count deleted."""
    count = 0
    if _redis:
        try:
            cursor, keys_to_delete = 0, []
            while True:
                cursor, batch = _redis.scan(cursor, match=f"*{pattern}*", count=100)
                keys_to_delete.extend(batch)
                if cursor == 0:
                    break
            if keys_to_delete:
                count = _redis.delete(*keys_to_delete)
            return count
        except Exception as e:
            logger.warning(f"[Cache] Redis SCAN error: {e}")
    for k in list(_mem.keys()):
        if pattern in k:
            del _mem[k]
            count += 1
    return count


# ── Rate limiter ──────────────────────────────────────────────────────────────

def rate_limit(key: str, max_requests: int, window_seconds: int) -> bool:
    """
    Sliding-window rate limiter.
    Returns True if the request is allowed, False if the limit is exceeded.
    """
    full_key = f"rl:{key}"
    now = time.time()

    if _redis:
        try:
            pipe = _redis.pipeline()
            pipe.zremrangebyscore(full_key, 0, now - window_seconds)
            pipe.zadd(full_key, {f"{now}:{uuid.uuid4().hex[:8]}": now})
            pipe.zcard(full_key)
            pipe.expire(full_key, window_seconds + 1)
            results = pipe.execute()
            return results[2] <= max_requests
        except Exception as e:
            logger.warning(f"[Cache] Rate limit Redis error: {e}")

    entry = _mem.get(full_key)
    timestamps: list[float] = []
    if entry is not None:
        raw, _ = entry
        if isinstance(raw, list):
            timestamps = [t for t in raw if now - t < window_seconds]

    if len(timestamps) >= max_requests:
        _mem[full_key] = (timestamps, now + window_seconds)
        return False

    timestamps.append(now)
    _mem[full_key] = (timestamps, now + window_seconds)
    return True


# ── Decorator ─────────────────────────────────────────────────────────────────

def cached(ttl: int = 300, prefix: str = ""):
    """Cache decorator — works on both sync and async functions."""
    def decorator(func):
        key_prefix = prefix or f"{func.__module__}.{func.__qualname__}"

        if inspect.iscoroutinefunction(func):
            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                key = make_key(key_prefix, *args, **kwargs)
                hit = get_cache(key)
                if hit is not None:
                    return hit
                result = await func(*args, **kwargs)
                set_cache(key, result, ttl)
                return result
            return async_wrapper
        else:
            @wraps(func)
            def sync_wrapper(*args, **kwargs):
                key = make_key(key_prefix, *args, **kwargs)
                hit = get_cache(key)
                if hit is not None:
                    return hit
                result = func(*args, **kwargs)
                set_cache(key, result, ttl)
                return result
            return sync_wrapper

    return decorator
