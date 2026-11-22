import logging
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger("campus-ta-hours")

async def error_middleware(request: Request, call_next):
    try:
        return await call_next(request)
    except Exception as exc:
        logger.exception("unhandled_error path=%s", request.url.path)
        return JSONResponse(status_code=500, content={"detail": "服务暂时不可用，请重试"})
