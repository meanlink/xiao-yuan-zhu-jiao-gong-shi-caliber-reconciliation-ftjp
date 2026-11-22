import time
from collections import defaultdict, deque
from fastapi import Request
from fastapi.responses import JSONResponse

_windows = defaultdict(deque)

async def rate_limit_middleware(request: Request, call_next):
    if request.url.path in {"/health", "/docs", "/openapi.json"}:
        return await call_next(request)
    key = request.client.host if request.client else "unknown"
    now = time.time()
    bucket = _windows[key]
    while bucket and bucket[0] < now - 30:
        bucket.popleft()
    if len(bucket) >= 120:
        return JSONResponse(status_code=429, content={"detail": "请求过于频繁，请稍后重试"})
    bucket.append(now)
    return await call_next(request)
