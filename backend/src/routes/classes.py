from fastapi import APIRouter, Depends, HTTPException
from ..db import get_conn
from .deps import current_user, require_roles

router = APIRouter(prefix="/classes", tags=["classes"])

@router.get("")
def list_classes(user=Depends(current_user)):
    with get_conn() as conn:
        rows = conn.execute("""SELECT c.*, u.name AS teacher_name FROM course_classes c LEFT JOIN users u ON u.id=c.teacher_id
            WHERE c.status='active' ORDER BY c.department,c.code""").fetchall()
    return {"items": [dict(r) for r in rows]}

@router.post("/{class_id}/checkin")
def record_checkin(class_id: int, user=Depends(require_roles("ta", "college_admin"))):
    with get_conn() as conn:
        row = conn.execute("SELECT id, code, course_name, weekday, start_time, end_time FROM course_classes WHERE id=%s AND status='active'", (class_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="课程班不存在")
    return {"class_id": class_id, "message": "签到入口已打开，请在工时填报页提交签到时间", "schedule": dict(row)}
