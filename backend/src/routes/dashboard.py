from fastapi import APIRouter, Depends
from ..db import get_conn
from .deps import current_user

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/summary")
def summary(user=Depends(current_user)):
    with get_conn() as conn:
        counts = conn.execute("""SELECT
            count(*) FILTER (WHERE status='submitted') AS submitted,
            count(*) FILTER (WHERE status='manual_review') AS manual_review,
            count(*) FILTER (WHERE status='approved') AS approved,
            coalesce(sum(validated_hours) FILTER (WHERE status='approved'),0) AS approved_hours
            FROM work_records""").fetchone()
        classes = conn.execute("SELECT count(*) AS count FROM course_classes WHERE status='active'").fetchone()
    return {"submitted": counts["submitted"], "manual_review": counts["manual_review"], "approved": counts["approved"], "approved_hours": float(counts["approved_hours"]), "active_classes": classes["count"], "role": user["role"]}
