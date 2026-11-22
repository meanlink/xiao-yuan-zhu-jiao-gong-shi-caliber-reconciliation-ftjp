from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from ..db import get_conn
from ..schemas.work_records import WorkRecordCreate, ReviewRequest
from ..services.hour_policy import validate_work_hours
from ..services.audit import record_audit
from .deps import current_user, require_roles

router = APIRouter(prefix="/work-records", tags=["work-records"])

LIST_SQL = """SELECT w.*, c.code AS class_code, c.course_name, c.department, c.term, c.weekday, c.start_time, c.end_time, c.teacher_id AS class_teacher_id,
    ta.name AS ta_name, teacher.name AS teacher_name FROM work_records w
    JOIN course_classes c ON c.id=w.class_id JOIN users ta ON ta.id=w.ta_id
    LEFT JOIN users teacher ON teacher.id=w.teacher_id"""

@router.get("")
def list_records(user=Depends(current_user)):
    params = []
    where = ""
    if user["role"] == "ta":
        where = " WHERE w.ta_id=%s"
        params.append(user["id"])
    elif user["role"] == "teacher":
        where = " WHERE c.teacher_id=%s"
        params.append(user["id"])
    with get_conn() as conn:
        rows = conn.execute(LIST_SQL + where + " ORDER BY w.work_date DESC, w.id DESC", params).fetchall()
    return {"items": [dict(r) for r in rows]}

@router.post("")
def create_record(payload: WorkRecordCreate, user=Depends(require_roles("ta"))):
    with get_conn() as conn:
        course = conn.execute("SELECT * FROM course_classes WHERE id=%s AND status='active'", (payload.class_id,)).fetchone()
        if not course:
            raise HTTPException(status_code=404, detail="课程班不存在")
        existing = conn.execute("SELECT id FROM work_records WHERE class_id=%s AND ta_id=%s AND work_date=%s AND activity_type=%s", (payload.class_id, user["id"], payload.work_date, payload.activity_type)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="同一课程班、日期和活动类型已有填报，请修改原记录")
        raw = payload.model_dump()
        raw["check_in"] = payload.check_in
        raw["check_out"] = payload.check_out
        result = validate_work_hours(raw, course)
        status = result["status"]
        row = conn.execute("""INSERT INTO work_records(class_id,ta_id,work_date,check_in,check_out,activity_type,work_description,reported_hours,validated_hours,status,conflict_type)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""", (payload.class_id,user["id"],payload.work_date,payload.check_in,payload.check_out,payload.activity_type,payload.work_description,payload.reported_hours,result["validated_hours"],status,result["conflict_type"])).fetchone()
    record_audit(user["id"], "work_record_created", "work_record", row["id"], {"status": status, "conflict_type": result["conflict_type"]})
    return {"id": row["id"], "status": status, "validated_hours": float(result["validated_hours"]), "conflict_type": result["conflict_type"]}

@router.post("/{record_id}/review")
def review_record(record_id: int, payload: ReviewRequest, user=Depends(require_roles("teacher", "college_admin"))):
    with get_conn() as conn:
        row = conn.execute(LIST_SQL + " WHERE w.id=%s", (record_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="工时记录不存在")
        if user["role"] == "teacher" and row["class_teacher_id"] != user["id"]:
            raise HTTPException(status_code=403, detail="教师只能处理自己课程班的工时")
        if row["status"] == "approved":
            raise HTTPException(status_code=409, detail="已审批记录不能重复处理")
        new_status = "manual_review" if row["status"] == "manual_review" else "approved"
        note = payload.note or ("学院管理员已复核签到冲突" if new_status == "approved" else "")
        conn.execute("UPDATE work_records SET status=%s, review_note=%s, teacher_id=%s, reviewed_at=now(), updated_at=now() WHERE id=%s", (new_status, note, user["id"], record_id))
    record_audit(user["id"], "work_record_reviewed", "work_record", record_id, {"status": new_status, "note": note})
    return {"id": record_id, "status": new_status, "message": "记录已审批，现可计入学院月报" if new_status == "approved" else "记录保留为人工复核"}

@router.post("/{record_id}/resolve-conflict")
def resolve_conflict(record_id: int, payload: ReviewRequest, user=Depends(require_roles("college_admin"))):
    with get_conn() as conn:
        row = conn.execute("""SELECT w.id,w.status,w.reported_hours,c.expected_hours
            FROM work_records w JOIN course_classes c ON c.id=w.class_id WHERE w.id=%s""", (record_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="工时记录不存在")
        if row["status"] != "manual_review":
            raise HTTPException(status_code=409, detail="当前记录不在人工复核状态")
        conn.execute("""UPDATE work_records SET status='submitted', validated_hours=LEAST(reported_hours, (SELECT expected_hours FROM course_classes WHERE id=work_records.class_id)),
            review_note=%s, updated_at=now() WHERE id=%s""", (payload.note or "学院管理员复核签到与排班后转教师审批", record_id))
    record_audit(user["id"], "attendance_conflict_resolved", "work_record", record_id, {"note": payload.note})
    return {"id": record_id, "status": "submitted"}
