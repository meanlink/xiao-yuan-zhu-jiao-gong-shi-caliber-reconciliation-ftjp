import json
from datetime import date, datetime
from decimal import Decimal

from fastapi import HTTPException

from ..services.audit import record_audit_conn
from ..services.monthly import monthly_preview

# 同一助教的所有审批/裁决操作共用一把事务级锁，保证并发审批只会有一笔进入计薪。
ADVISORY_NAMESPACE = 20261122

RECORD_SELECT = """SELECT w.id, w.class_id, w.ta_id, w.work_date, w.check_in, w.check_out, w.activity_type,
    w.work_description, w.reported_hours, w.validated_hours, w.status, w.conflict_type, w.review_note,
    w.teacher_id, w.reviewed_at, c.code AS class_code, c.course_name, c.department,
    c.teacher_id AS class_teacher_id, u.name AS ta_name
    FROM work_records w
    JOIN course_classes c ON c.id=w.class_id
    JOIN users u ON u.id=w.ta_id"""

CASE_SELECT = """SELECT ac.*, ta.name AS ta_name FROM adjudication_cases ac JOIN users ta ON ta.id=ac.ta_id"""


def jsonable(value):
    if isinstance(value, dict):
        return {k: jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def lock_ta(conn, ta_id: int) -> None:
    conn.execute("SELECT pg_advisory_xact_lock(%s, %s)", (ADVISORY_NAMESPACE, int(ta_id)))


def _record_view(row: dict) -> dict:
    return {
        "id": row["id"],
        "class_id": row["class_id"],
        "class_code": row["class_code"],
        "course_name": row["course_name"],
        "department": row["department"],
        "ta_id": row["ta_id"],
        "ta_name": row["ta_name"],
        "work_date": row["work_date"],
        "check_in": row["check_in"],
        "check_out": row["check_out"],
        "activity_type": row["activity_type"],
        "reported_hours": row["reported_hours"],
        "validated_hours": row["validated_hours"],
        "status": row["status"],
        "conflict_type": row["conflict_type"],
        "review_note": row["review_note"],
    }


def find_overlaps(conn, record: dict, statuses: tuple[str, ...]) -> list[dict]:
    """同一助教、不同学院、签到时段真实重叠的记录。"""
    if not record.get("check_in") or not record.get("check_out"):
        return []
    placeholders = ",".join(["%s"] * len(statuses))
    return conn.execute(
        RECORD_SELECT
        + f""" WHERE w.ta_id=%s AND w.id<>%s AND w.class_id<>%s AND c.department<>%s
            AND w.status IN ({placeholders})
            AND w.check_in IS NOT NULL AND w.check_out IS NOT NULL
            AND w.check_in < %s AND w.check_out > %s
            ORDER BY w.id""",
        (
            record["ta_id"], record["id"], record["class_id"], record["department"],
            *statuses, record["check_out"], record["check_in"],
        ),
    ).fetchall()


def mark_pending(conn, record_id: int, blocking_record_id: int) -> None:
    conn.execute(
        """UPDATE work_records SET status='adjudication_pending',
            conflict_type = CASE
                WHEN conflict_type IS NULL OR conflict_type='' THEN 'overlapping_time'
                WHEN conflict_type LIKE %s THEN conflict_type
                ELSE conflict_type || ',overlapping_time' END,
            review_note = COALESCE(NULLIF(review_note,''), %s),
            updated_at=now()
            WHERE id=%s""",
        ("%overlapping_time%", f"与记录 #{blocking_record_id} 签到时段重叠，等待学院管理员裁决", record_id),
    )


def ensure_case(conn, ta_id: int, record_a_id: int, record_b_id: int, winner_record_id: int) -> int:
    """冲突对按 id 归一化，重复识别不会产生重复案例。"""
    a, b = sorted((record_a_id, record_b_id))
    row = conn.execute(
        """INSERT INTO adjudication_cases(ta_id, record_a_id, record_b_id, winner_record_id, status)
            VALUES (%s,%s,%s,%s,'pending')
            ON CONFLICT(record_a_id, record_b_id) DO UPDATE SET
                updated_at=now(),
                winner_record_id = CASE
                    WHEN adjudication_cases.status='pending' THEN EXCLUDED.winner_record_id
                    ELSE adjudication_cases.winner_record_id END
            RETURNING id""",
        (ta_id, a, b, winner_record_id),
    ).fetchone()
    return row["id"]


def approve(conn, record_id: int, actor_id: int, note: str) -> None:
    conn.execute(
        """UPDATE work_records SET status='approved', review_note=%s, teacher_id=%s,
            reviewed_at=now(), updated_at=now() WHERE id=%s""",
        (note, actor_id, record_id),
    )


def apply_approval(conn, record: dict, actor_id: int, note: str) -> dict:
    """教师审批的核心状态机：先到的一笔计薪，后到的一笔转学院裁决。"""
    approved_overlaps = find_overlaps(conn, record, ("approved",))
    if approved_overlaps:
        blocker = approved_overlaps[0]
        mark_pending(conn, record["id"], blocker["id"])
        case_id = ensure_case(conn, record["ta_id"], record["id"], blocker["id"], blocker["id"])
        record_audit_conn(
            conn, actor_id, "work_record_conflict_detected", "work_record", record["id"],
            {"case_id": case_id, "blocking_record_id": blocker["id"], "reason": "overlapping_time"},
        )
        return {
            "id": record["id"],
            "status": "adjudication_pending",
            "case_id": case_id,
            "blocking_record_id": blocker["id"],
            "message": "签到时段与另一学院已计薪记录重叠，本笔留待学院管理员裁决",
        }

    approve(conn, record["id"], actor_id, note)
    record_audit_conn(
        conn, actor_id, "work_record_reviewed", "work_record", record["id"],
        {"status": "approved", "note": note},
    )

    blocked = []
    for other in find_overlaps(conn, record, ("submitted",)):
        mark_pending(conn, other["id"], record["id"])
        case_id = ensure_case(conn, record["ta_id"], record["id"], other["id"], record["id"])
        blocked.append({"record_id": other["id"], "case_id": case_id})
        record_audit_conn(
            conn, actor_id, "work_record_conflict_detected", "work_record", other["id"],
            {"case_id": case_id, "blocking_record_id": record["id"], "reason": "overlapping_time"},
        )
    return {"id": record["id"], "status": "approved", "blocked_records": blocked}


def find_case_for_record(conn, record_id: int) -> dict | None:
    return conn.execute(
        """SELECT * FROM adjudication_cases
            WHERE record_a_id=%s OR record_b_id=%s
            ORDER BY (status='pending') DESC, updated_at DESC, id DESC LIMIT 1""",
        (record_id, record_id),
    ).fetchone()


def compute_previews(conn, records: list[dict]) -> list[dict]:
    """同一事务内重算涉及学院的月报，保证两院预览一起更新或一起回滚。"""
    seen = set()
    previews = []
    for record in records:
        month = str(record["work_date"])[:7]
        key = (record["department"], month)
        if key in seen:
            continue
        seen.add(key)
        previews.append(monthly_preview(conn, record["department"], month))
    previews.sort(key=lambda item: (item["department"], item["month"]))
    return previews


def _decision_view(row: dict) -> dict:
    return {
        "id": row["id"],
        "seq": row["seq"],
        "chosen_record_id": row["chosen_record_id"],
        "previous_record_id": row["previous_record_id"],
        "reason": row["reason"],
        "actor_id": row["actor_id"],
        "actor_name": row.get("actor_name"),
        "created_at": row["created_at"],
    }


def case_detail(conn, case: dict) -> dict:
    records = conn.execute(
        RECORD_SELECT + " WHERE w.id IN (%s,%s)", (case["record_a_id"], case["record_b_id"])
    ).fetchall()
    records.sort(key=lambda row: row["id"])
    decisions = conn.execute(
        """SELECT d.*, u.name AS actor_name FROM adjudication_decisions d
            LEFT JOIN users u ON u.id=d.actor_id
            WHERE d.case_id=%s ORDER BY d.seq""",
        (case["id"],),
    ).fetchall()
    return {
        "id": case["id"],
        "ta_id": case["ta_id"],
        "ta_name": case["ta_name"],
        "status": case["status"],
        "version": case["version"],
        "winner_record_id": case["winner_record_id"],
        "month": str(records[0]["work_date"])[:7] if records else None,
        "records": [_record_view(row) for row in records],
        "decisions": [_decision_view(row) for row in decisions],
        "previews": compute_previews(conn, records),
        "created_at": case["created_at"],
        "updated_at": case["updated_at"],
    }


def _can_view(user: dict, case: dict, records: list[dict]) -> bool:
    if user["role"] == "college_admin":
        return True
    if user["role"] == "ta":
        return case["ta_id"] == user["id"]
    if user["role"] == "teacher":
        return any(row["class_teacher_id"] == user["id"] for row in records)
    return False


def list_cases(conn, user: dict, month: str | None = None) -> list[dict]:
    conditions = []
    params: list = []
    if user["role"] == "ta":
        conditions.append("ac.ta_id=%s")
        params.append(user["id"])
    elif user["role"] == "teacher":
        conditions.append(
            """EXISTS (SELECT 1 FROM work_records w JOIN course_classes c ON c.id=w.class_id
                WHERE w.id IN (ac.record_a_id, ac.record_b_id) AND c.teacher_id=%s)"""
        )
        params.append(user["id"])
    elif user["role"] != "college_admin":
        return []
    if month:
        conditions.append(
            """EXISTS (SELECT 1 FROM work_records w WHERE w.id IN (ac.record_a_id, ac.record_b_id)
                AND to_char(w.work_date,'YYYY-MM')=%s)"""
        )
        params.append(month)
    sql = CASE_SELECT
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY ac.updated_at DESC, ac.id DESC LIMIT 100"
    rows = conn.execute(sql, params).fetchall()
    return [case_detail(conn, row) for row in rows]


def get_case(conn, case_id: int, user: dict) -> dict:
    case = conn.execute(CASE_SELECT + " WHERE ac.id=%s", (case_id,)).fetchone()
    if not case:
        raise HTTPException(status_code=404, detail="冲突案例不存在")
    records = conn.execute(
        RECORD_SELECT + " WHERE w.id IN (%s,%s)", (case["record_a_id"], case["record_b_id"])
    ).fetchall()
    if not _can_view(user, case, records):
        raise HTTPException(status_code=403, detail="无权查看该冲突案例")
    return case_detail(conn, case)


def decide(
    conn,
    case_id: int,
    chosen_record_id: int,
    reason: str,
    idempotency_key: str,
    expected_version: int | None,
    actor_id: int,
) -> dict:
    reason = (reason or "").strip()
    if len(reason) < 2:
        raise HTTPException(status_code=422, detail="请填写改选理由")

    lookup = conn.execute("SELECT id, ta_id FROM adjudication_cases WHERE id=%s", (case_id,)).fetchone()
    if not lookup:
        raise HTTPException(status_code=404, detail="冲突案例不存在")
    lock_ta(conn, lookup["ta_id"])

    case = conn.execute(
        "SELECT * FROM adjudication_cases WHERE id=%s FOR UPDATE", (case_id,)
    ).fetchone()
    if not case:
        raise HTTPException(status_code=404, detail="冲突案例不存在")

    prior = conn.execute(
        "SELECT * FROM adjudication_decisions WHERE case_id=%s AND idempotency_key=%s",
        (case_id, idempotency_key),
    ).fetchone()
    if prior:
        if prior["chosen_record_id"] != chosen_record_id:
            raise HTTPException(status_code=409, detail="该幂等键已用于另一笔选择，拒绝覆盖")
        receipt = dict(prior["response_json"] or {})
        receipt["replayed"] = True
        original_version = (receipt.get("case") or {}).get("version")
        receipt["superseded"] = (
            original_version is not None and (case["version"] != original_version or case["winner_record_id"] != chosen_record_id)
        )
        receipt["current"] = {
            "winner_record_id": case["winner_record_id"],
            "version": case["version"],
            "status": case["status"],
        }
        return jsonable(receipt)

    if expected_version is not None and expected_version != case["version"]:
        raise HTTPException(
            status_code=409,
            detail=f"裁决已被其他操作更新（当前版本 {case['version']}），原决定保持不变，请刷新后重试",
        )

    if chosen_record_id not in (case["record_a_id"], case["record_b_id"]):
        raise HTTPException(status_code=400, detail="只能在本案例的两笔冲突记录中改选")

    records = conn.execute(
        RECORD_SELECT + " WHERE w.id IN (%s,%s) FOR UPDATE OF w",
        (case["record_a_id"], case["record_b_id"]),
    ).fetchall()
    record_map = {row["id"]: row for row in records}
    chosen = record_map[chosen_record_id]
    if chosen["status"] not in ("approved", "submitted", "adjudication_pending"):
        raise HTTPException(status_code=409, detail="目标记录当前状态不可计薪，原决定保持不变")
    if Decimal(str(chosen["validated_hours"])) <= 0:
        raise HTTPException(status_code=409, detail="目标记录有效工时为 0，无法改选，原决定保持不变")

    # 目标记录若还与本案之外的另一笔已计薪记录重叠，改选会造成重复计薪，拒绝并保留原决定。
    if chosen["check_in"] and chosen["check_out"]:
        outside = conn.execute(
            RECORD_SELECT
            + """ WHERE w.ta_id=%s AND w.id NOT IN (%s,%s) AND w.status='approved'
                AND w.check_in IS NOT NULL AND w.check_out IS NOT NULL
                AND w.check_in < %s AND w.check_out > %s""",
            (chosen["ta_id"], case["record_a_id"], case["record_b_id"], chosen["check_out"], chosen["check_in"]),
        ).fetchall()
        if outside:
            raise HTTPException(
                status_code=409,
                detail=f"目标记录仍与已计薪记录 #{outside[0]['id']} 时段重叠，无法改选，原决定保持不变",
            )

    previous_winner = case["winner_record_id"]

    # 先降级案例中另一笔已计薪记录，再提升所选记录，整个过程在同一事务内完成。
    for record_id, record in record_map.items():
        if record_id == chosen_record_id or record["status"] != "approved":
            continue
        conn.execute(
            """UPDATE work_records SET status='adjudication_pending',
                conflict_type = CASE
                    WHEN conflict_type IS NULL OR conflict_type='' THEN 'overlapping_time'
                    WHEN conflict_type LIKE %s THEN conflict_type
                    ELSE conflict_type || ',overlapping_time' END,
                review_note=%s, updated_at=now() WHERE id=%s""",
            ("%overlapping_time%", f"学院裁决改选，本笔暂停计薪：{reason}"[:500], record_id),
        )
        # 若该记录还是其他案例的计薪方，那些案例需要重新裁决，不能留下悬空的赢家。
        conn.execute(
            """UPDATE adjudication_cases SET status='pending', winner_record_id=NULL,
                version=version+1, updated_at=now()
                WHERE winner_record_id=%s AND id<>%s""",
            (record_id, case_id),
        )

    if chosen["status"] != "approved":
        conn.execute(
            """UPDATE work_records SET status='approved',
                teacher_id=COALESCE(teacher_id, (SELECT teacher_id FROM course_classes WHERE id=work_records.class_id)),
                review_note=%s, reviewed_at=now(), updated_at=now()
                WHERE id=%s""",
            (f"学院管理员改选计薪：{reason}"[:500], chosen_record_id),
        )

    new_version = case["version"] + 1
    conn.execute(
        """UPDATE adjudication_cases SET winner_record_id=%s, status='decided',
            version=%s, updated_at=now() WHERE id=%s""",
        (chosen_record_id, new_version, case_id),
    )

    seq = conn.execute(
        "SELECT COALESCE(MAX(seq),0)+1 AS seq FROM adjudication_decisions WHERE case_id=%s",
        (case_id,),
    ).fetchone()["seq"]
    decision = conn.execute(
        """INSERT INTO adjudication_decisions(case_id, seq, actor_id, chosen_record_id,
            previous_record_id, reason, idempotency_key)
            VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id, created_at""",
        (case_id, seq, actor_id, chosen_record_id, previous_winner, reason, idempotency_key),
    ).fetchone()

    fresh_records = conn.execute(
        RECORD_SELECT + " WHERE w.id IN (%s,%s)", (case["record_a_id"], case["record_b_id"])
    ).fetchall()
    fresh_records.sort(key=lambda row: row["id"])
    previews = compute_previews(conn, fresh_records)

    receipt = jsonable(
        {
            "case_id": case_id,
            "decision_id": decision["id"],
            "seq": seq,
            "chosen_record_id": chosen_record_id,
            "previous_record_id": previous_winner,
            "changed": previous_winner != chosen_record_id,
            "case": {
                "id": case_id,
                "status": "decided",
                "version": new_version,
                "winner_record_id": chosen_record_id,
            },
            "records": [_record_view(row) for row in fresh_records],
            "previews": previews,
            "decisions": [],
            "replayed": False,
            "created_at": decision["created_at"],
        }
    )

    conn.execute(
        "UPDATE adjudication_decisions SET response_json=%s WHERE id=%s",
        (json.dumps(receipt, ensure_ascii=False), decision["id"]),
    )
    record_audit_conn(
        conn, actor_id, "adjudication_decided", "adjudication_case", case_id,
        {
            "seq": seq,
            "chosen_record_id": chosen_record_id,
            "previous_record_id": previous_winner,
            "reason": reason,
            "previews": [
                {"department": item["department"], "month": item["month"], "total_approved_hours": item["total_approved_hours"]}
                for item in previews
            ],
        },
    )
    return receipt
