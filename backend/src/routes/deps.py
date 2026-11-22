from fastapi import Depends, Header, HTTPException
from ..security import decode_token
from ..db import get_conn

def current_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="请先登录")
    try:
        payload = decode_token(authorization.split(" ", 1)[1])
    except Exception:
        raise HTTPException(status_code=401, detail="登录已过期")
    with get_conn() as conn:
        user = conn.execute("SELECT id,email,name,role FROM users WHERE id=%s", (int(payload["sub"]),)).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user

def require_roles(*roles):
    def checker(user=Depends(current_user)):
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="当前角色没有此操作权限")
        return user
    return checker
