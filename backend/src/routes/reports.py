import json
from fastapi import APIRouter, Depends
from ..db import get_conn
from ..schemas.reports import ReportRequest
from ..services.audit import record_audit_conn
from ..services.monthly import monthly_preview
from .deps import require_roles

router = APIRouter(prefix="/reports", tags=["reports"])

@router.get("/monthly")
def monthly_report(month: str = "2026-11", department: str = "信息工程学院", user=Depends(require_roles("teacher", "college_admin", "ta"))):
    with get_conn() as conn:
        return monthly_preview(conn, department, month)

@router.post("/monthly/publish")
def publish_report(payload: ReportRequest, user=Depends(require_roles("college_admin"))):
    with get_conn() as conn:
        result = monthly_preview(conn, payload.department, payload.month)
        conn.execute("""INSERT INTO approval_sheets(department,month,status,totals_json,approved_by,published_at)
            VALUES (%s,%s,'published',%s,%s,now())
            ON CONFLICT(department,month) DO UPDATE SET status='published', totals_json=EXCLUDED.totals_json, approved_by=EXCLUDED.approved_by, published_at=now()""", (payload.department, payload.month, json.dumps(result, ensure_ascii=False), user["id"]))
        record_audit_conn(conn, user["id"], "monthly_report_published", "approval_sheet", None, {"department": payload.department, "month": payload.month, "total_approved_hours": result["total_approved_hours"]})
    return {"status": "published", **result}
