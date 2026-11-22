from fastapi import APIRouter, Depends
from ..db import get_conn
from .deps import require_roles

router = APIRouter(prefix="/audit", tags=["audit"])

@router.get("")
def audit(user=Depends(require_roles("college_admin"))):
    with get_conn() as conn:
        rows = conn.execute("SELECT a.*, u.name AS actor_name FROM audit_logs a LEFT JOIN users u ON u.id=a.actor_id ORDER BY a.created_at DESC LIMIT 50").fetchall()
    return {"items": [dict(r) for r in rows]}
