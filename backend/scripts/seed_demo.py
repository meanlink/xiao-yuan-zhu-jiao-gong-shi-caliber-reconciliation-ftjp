from datetime import datetime, timezone
from decimal import Decimal
from src.db import get_conn, init_db
from src.services.auth_service import ensure_users
from src.security import hash_password

init_db()
ensure_users()
with get_conn() as conn:
    teacher = conn.execute("SELECT id FROM users WHERE email='teacher@donglan.edu'").fetchone()["id"]
    ta = conn.execute("SELECT id FROM users WHERE email='ta@donglan.edu'").fetchone()["id"]
    conn.execute("""INSERT INTO course_classes(code,course_name,department,term,weekday,start_time,end_time,room,expected_hours,teacher_id)
        VALUES ('CS201-A','数据结构与算法','信息工程学院','2026-秋',1,'09:00','11:00','知行楼 A201',2.0,%s)
        ON CONFLICT(code) DO UPDATE SET teacher_id=EXCLUDED.teacher_id""", (teacher,))
    conn.execute("""INSERT INTO course_classes(code,course_name,department,term,weekday,start_time,end_time,room,expected_hours,teacher_id)
        VALUES ('DS110-B','数据分析导论','信息工程学院','2026-秋',3,'14:00','16:00','知行楼 B305',2.0,%s)
        ON CONFLICT(code) DO UPDATE SET teacher_id=EXCLUDED.teacher_id""", (teacher,))
    conn.execute("""INSERT INTO course_classes(code,course_name,department,term,weekday,start_time,end_time,room,expected_hours,teacher_id)
        VALUES ('EDU305-C','教育测量基础','教育学院','2026-秋',4,'10:00','12:00','博学楼 204',2.0,%s)
        ON CONFLICT(code) DO UPDATE SET teacher_id=EXCLUDED.teacher_id""", (teacher,))
    # 同一助教周一上午在两个学院各有一节课，用来演示跨学院签到时段重叠。
    conn.execute("""INSERT INTO course_classes(code,course_name,department,term,weekday,start_time,end_time,room,expected_hours,teacher_id)
        VALUES ('FL210-D','学术英语写作','外国语学院','2026-秋',1,'09:00','11:00','语林楼 305',2.0,%s)
        ON CONFLICT(code) DO UPDATE SET teacher_id=EXCLUDED.teacher_id""", (teacher,))
    classes = {r["code"]: r["id"] for r in conn.execute("SELECT id,code FROM course_classes").fetchall()}
    # Stable natural keys keep reruns idempotent while preserving review states.
    seed_rows = [
        (classes["CS201-A"], ta, "2026-11-02", "2026-11-02T09:05:00+00:00", "2026-11-02T10:55:00+00:00", "答疑", "课前习题答疑与课堂签到协助", 1.75, 1.75, "approved", None),
        (classes["DS110-B"], ta, "2026-11-04", "2026-11-04T14:08:00+00:00", "2026-11-04T15:42:00+00:00", "实验辅导", "清洗实验数据并辅导小组作业", 1.5, 1.5, "submitted", None),
        (classes["EDU305-C"], ta, "2026-11-05", "2026-11-05T09:10:00+00:00", "2026-11-05T12:08:00+00:00", "资料整理", "教育测量案例资料整理", 2.5, 0, "manual_review", "checkout_outside_schedule"),
        (classes["FL210-D"], ta, "2026-11-02", "2026-11-02T09:10:00+00:00", "2026-11-02T10:50:00+00:00", "作业批改", "批改学术英语段落并整理反馈", 1.75, 1.75, "adjudication_pending", "overlapping_time"),
    ]
    for row in seed_rows:
        conn.execute("""INSERT INTO work_records(class_id,ta_id,work_date,check_in,check_out,activity_type,work_description,reported_hours,validated_hours,status,conflict_type)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(class_id,ta_id,work_date,activity_type) DO NOTHING""", row)
    # 演示数据里已经有并发审批的结果：CS201-A 先计薪，外国语学院的 FL210-D 留待裁决。
    a = conn.execute("SELECT id FROM work_records WHERE class_id=%s AND ta_id=%s AND work_date=%s AND activity_type=%s",
                     (classes["CS201-A"], ta, "2026-11-02", "答疑")).fetchone()
    b = conn.execute("SELECT id FROM work_records WHERE class_id=%s AND ta_id=%s AND work_date=%s AND activity_type=%s",
                     (classes["FL210-D"], ta, "2026-11-02", "作业批改")).fetchone()
    if a and b:
        conn.execute("""INSERT INTO adjudication_cases(ta_id,record_a_id,record_b_id,winner_record_id,status)
            VALUES (%s,%s,%s,%s,'pending')
            ON CONFLICT(record_a_id,record_b_id) DO NOTHING""", (ta, a["id"], b["id"], a["id"]))
        conn.execute("""UPDATE work_records SET review_note=COALESCE(review_note, %s)
            WHERE id=%s AND review_note IS NULL""", (f"与记录 #{a['id']} 签到时段重叠，等待学院管理员裁决", b["id"]))
print("seed_demo complete: 4 classes, 4 work records, 3 users, 1 conflict case")
