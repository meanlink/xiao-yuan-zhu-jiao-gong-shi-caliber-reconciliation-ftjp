import json
from fastapi import APIRouter, Depends, HTTPException
from ..db import get_conn
from ..schemas.reports import ReportRequest
from ..services.hour_policy import pivot_monthly
from ..services.audit import record_audit
from .deps import require_roles

router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("/monthly")
def monthly_report(month: str = "2026-11", department: str = "信息工程学院", user=Depends(require_roles("teacher", "college_admin", "ta"))):
    with get_conn() as conn:
        rows = conn.execute("""SELECT w.work_date,w.status,w.validated_hours,w.activity_type,c.department,c.code AS class_code,c.course_name,u.name AS ta_name
            FROM work_records w JOIN course_classes c ON c.id=w.class_id JOIN users u ON u.id=w.ta_id
            WHERE c.department=%s AND w.work_date >= (%s || '-01')::date AND w.work_date < ((%s || '-01')::date + interval '1 month')""", (department, month, month)).fetchall()
    result = pivot_monthly([dict(r) for r in rows], month)
    result["department"] = department
    return result

@router.post("/monthly/publish")
def publish_report(payload: ReportRequest, user=Depends(require_roles("college_admin"))):
    with get_conn() as conn:
        rows = conn.execute("""SELECT w.work_date,w.status,w.validated_hours,w.activity_type,c.department,c.code AS class_code,c.course_name,u.name AS ta_name
            FROM work_records w JOIN course_classes c ON c.id=w.class_id JOIN users u ON u.id=w.ta_id
            WHERE c.department=%s AND w.work_date >= (%s || '-01')::date AND w.work_date < ((%s || '-01')::date + interval '1 month')""", (payload.department, payload.month, payload.month)).fetchall()
        result = pivot_monthly([dict(r) for r in rows], payload.month)
        conn.execute("""INSERT INTO approval_sheets(department,month,status,totals_json,approved_by,published_at)
            VALUES (%s,%s,'published',%s,%s,now())
            ON CONFLICT(department,month) DO UPDATE SET status='published', totals_json=EXCLUDED.totals_json, approved_by=EXCLUDED.approved_by, published_at=now()""", (payload.department, payload.month, json.dumps(result, ensure_ascii=False), user["id"]))
    record_audit(user["id"], "monthly_report_published", "approval_sheet", None, {"department": payload.department, "month": payload.month, "total_approved_hours": result["total_approved_hours"]})
    return {"status": "published", **result}
