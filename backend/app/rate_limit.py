"""In-memory demo abuse guard; use shared distributed limits before production."""
import time
from collections import defaultdict, deque
from threading import Lock
from fastapi import HTTPException, Request
_lock = Lock()
_history: dict[tuple[str,str],deque[float]] = defaultdict(deque)

def throttle(request: Request, group: str, *, limit: int=25, seconds: int=60) -> None:
    address = request.client.host if request.client else 'unknown'
    key = (group,address)
    now = time.monotonic()
    with _lock:
        if len(_history) > 20000:
            _history.clear()
        slots = _history[key]
        while slots and slots[0] <= now-seconds:
            slots.popleft()
        if len(slots) >= limit:
            raise HTTPException(status_code=429,detail='Çok fazla deneme. Bir süre sonra tekrar deneyin.',
                                headers={'Retry-After':str(seconds)})
        slots.append(now)
