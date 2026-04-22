"""
connectors/_cache.py
Simple TTL cache decorator for connector functions.
Avoids hitting Jira / Confluence / GitHub APIs repeatedly within a short window.
"""

import time
from functools import wraps


def ttl_cache(ttl_seconds: int = 60):
    """Cache a function's return value keyed by (args, kwargs) for ttl_seconds."""

    def decorator(func):
        store: dict = {}

        @wraps(func)
        def wrapper(*args, **kwargs):
            key = (args, tuple(sorted(kwargs.items())))
            now = time.time()
            hit = store.get(key)
            if hit and now - hit[0] < ttl_seconds:
                return hit[1]
            value = func(*args, **kwargs)
            store[key] = (now, value)
            return value

        wrapper.cache_clear = store.clear  # type: ignore[attr-defined]
        return wrapper

    return decorator
