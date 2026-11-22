from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from ..db import get_conn
from ..schemas.work_records import WorkRecordCreate, ReviewRequest
from ..services.hour_policy import validate_work_hours
from ..services.audit import record_audit, record_audit_conn
from ..services import adjudication
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
        # 锁住该助教，再重新读取；并发审批同一助教的重叠记录时只会有一笔进入计薪。
        adjudication.lock_ta(conn, row["ta_id"])
        row = conn.execute(LIST_SQL + " WHERE w.id=%s", (record_id,)).fetchone()
        if row["status"] == "approved":
            raise HTTPException(status_code=409, detail="已审批记录不能重复处理")
        if row["status"] == "adjudication_pending":
            # 并发审批时后到的请求命中同一冲突对：结果一致，保留待裁决，不视为失败。
            case = adjudication.find_case_for_record(conn, record_id)
            return {
                "id": record_id,
                "status": "adjudication_pending",
                "case_id": case["id"] if case else None,
                "message": "该记录与其他学院记录时段重叠，留待学院管理员裁决",
            }
        if row["status"] == "manual_review":
            note = payload.note or ""
            conn.execute("UPDATE work_records SET status='manual_review', review_note=%s, teacher_id=%s, reviewed_at=now(), updated_at=now() WHERE id=%s", (note, user["id"], record_id))
            record_audit_conn(conn, user["id"], "work_record_reviewed", "work_record", record_id, {"status": "manual_review", "note": note})
            return {"id": record_id, "status": "manual_review", "message": "记录保留为人工复核"}
        if row["status"] != "submitted":
            raise HTTPException(status_code=409, detail="当前状态不可审批")
        note = payload.note or "任课教师核对签到与工作说明后审批"
        result = adjudication.apply_approval(conn, row, user["id"], note)
    if result["status"] == "approved":
        message = "记录已审批，现可计入学院月报"
        if result["blocked_records"]:
            message += f"；同时有 {len(result['blocked_records'])} 笔重叠记录转入学院裁决"
    else:
        message = result["message"]
    return {**result, "message": message}

@router.post("/{record_id}/resolve-conflict")
def resolve_conflict(record_id: int, payload: ReviewRequest, user=Depends(require_roles("college_admin"))):
    with get_conn() as conn:
        row = conn.execute("""SELECT w.id,w.ta_id,w.status,w.reported_hours,c.expected_hours
            FROM work_records w JOIN course_classes c ON c.id=w.class_id WHERE w.id=%s""", (record_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="工时记录不存在")
        adjudication.lock_ta(conn, row["ta_id"])
        row = conn.execute("""SELECT w.id,w.ta_id,w.status,w.reported_hours,c.expected_hours
            FROM work_records w JOIN course_classes c ON c.id=w.class_id WHERE w.id=%s""", (record_id,)).fetchone()
        if row["status"] == "adjudication_pending":
            raise HTTPException(status_code=409, detail="重叠记录只能通过冲突裁决改选计薪方")
        if row["status"] != "manual_review":
            raise HTTPException(status_code=409, detail="当前记录不在人工复核状态")
        note = payload.note or "学院管理员复核签到与排班后转教师审批"
        conn.execute("""UPDATE work_records SET status='submitted', validated_hours=LEAST(reported_hours, (SELECT expected_hours FROM course_classes WHERE id=work_records.class_id)),
            review_note=%s, updated_at=now() WHERE id=%s""", (note, record_id))
        record_audit_conn(conn, user["id"], "attendance_conflict_resolved", "work_record", record_id, {"note": payload.note})
    return {"id": record_id, "status": "submitted"}
