"""跨学院签到时段重叠的计薪裁决集成测试。

需要本地 PostgreSQL；设置 TEST_DATABASE_URL 指向一个可清空的测试库。
运行：pytest -q backend/tests
"""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, time

import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "postgresql://campus:campus123@127.0.0.1:17754/campus_hours")

from src.db import get_conn  # noqa: E402
from src.main import app  # noqa: E402
from src.security import hash_password  # noqa: E402

BASE = date(2026, 11, 2)  # 周一
MONTH = "2026-11"


def _reset():
    with get_conn() as conn:
        conn.execute("""TRUNCATE adjudication_decisions, adjudication_cases, work_records,
            approval_sheets, audit_logs, course_classes, users RESTART IDENTITY CASCADE""")
        for email, name, role in (
            ("ta@donglan.edu", "林若溪", "ta"),
            ("teacher@donglan.edu", "周明远", "teacher"),
            ("admin@donglan.edu", "沈老师", "college_admin"),
        ):
            conn.execute(
                "INSERT INTO users(email,name,role,password_hash) VALUES (%s,%s,%s,%s)",
                (email, name, role, hash_password("campus123")),
            )
        teacher = conn.execute("SELECT id FROM users WHERE email='teacher@donglan.edu'").fetchone()["id"]
        conn.execute(
            """INSERT INTO course_classes(code,course_name,department,term,weekday,start_time,end_time,room,expected_hours,teacher_id)
                VALUES ('A-101','甲学院课程','甲学院','2026-秋',1,'09:00','11:00','甲楼 1',2.0,%s),
                       ('B-202','乙学院课程','乙学院','2026-秋',1,'09:00','11:00','乙楼 2',2.0,%s)""",
            (teacher, teacher),
        )


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        _reset()
        yield c


def _login(client, email):
    r = client.post("/auth/login", json={"email": email, "password": "campus123"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _classes(client, headers):
    items = client.get("/classes", headers=headers).json()["items"]
    return {c["code"]: c["id"] for c in items}


def _create(client, headers, class_id, activity, check_in, check_out, reported=1.75):
    body = {
        "class_id": class_id,
        "work_date": BASE.isoformat(),
        "check_in": f"{BASE.isoformat()}T{check_in}:00+00:00",
        "check_out": f"{BASE.isoformat()}T{check_out}:00+00:00",
        "activity_type": activity,
        "work_description": "跨学院同时段工作说明",
        "reported_hours": reported,
    }
    r = client.post("/work-records", json=body, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "submitted", r.text
    return r.json()["id"]


def _preview(client, headers, dept):
    return client.get(f"/reports/monthly?month={MONTH}&department={dept}", headers=headers).json()


@pytest.fixture(scope="module")
def conflict(client):
    _reset()
    ta = _login(client, "ta@donglan.edu")
    teacher = _login(client, "teacher@donglan.edu")
    admin = _login(client, "admin@donglan.edu")
    codes = _classes(client, ta)
    a = _create(client, ta, codes["A-101"], "答疑", "09:05", "10:55")
    b = _create(client, ta, codes["B-202"], "实验辅导", "09:10", "10:50")

    # 并发审批：两个请求同时尝试让同一助教的两笔重叠记录计薪。
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(
            lambda rid: client.post(f"/work-records/{rid}/review", json={"note": "并发审批"}, headers=teacher),
            [a, b],
        ))
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    statuses = {r.json()["id"]: r.json()["status"] for r in results}
    assert sorted(statuses.values()) == ["adjudication_pending", "approved"], statuses
    winner = next(rid for rid, st in statuses.items() if st == "approved")
    pending = next(rid for rid, st in statuses.items() if st == "adjudication_pending")
    return {"ta": ta, "teacher": teacher, "admin": admin, "a": a, "b": b, "winner": winner, "pending": pending}


def test_concurrent_approval_accounts_only_one(client, conflict):
    records = {r["id"]: r for r in client.get("/work-records", headers=conflict["admin"]).json()["items"]}
    assert records[conflict["winner"]]["status"] == "approved"
    assert records[conflict["pending"]]["status"] == "adjudication_pending"
    assert records[conflict["pending"]]["conflict_type"].find("overlapping_time") >= 0
    first = _preview(client, conflict["admin"], "甲学院")
    second = _preview(client, conflict["admin"], "乙学院")
    assert first["total_approved_hours"] + second["total_approved_hours"] == pytest.approx(1.75)


def test_switch_decision_updates_both_departments(client, conflict):
    case = client.get("/adjudications", headers=conflict["admin"]).json()["items"][0]
    assert {r["id"] for r in case["records"]} == {conflict["a"], conflict["b"]}
    # 先到的一笔暂时计薪，案例仍待学院裁决。
    assert case["status"] == "pending"
    assert case["winner_record_id"] == conflict["winner"]

    target = conflict["pending"]
    r = client.post(
        f"/adjudications/{case['id']}/decisions",
        json={"chosen_record_id": target, "reason": "乙学院课程要求现场签到，排班窗口完全吻合", "expected_version": case["version"]},
        headers={**conflict["admin"], "Idempotency-Key": "switch-1"},
    )
    assert r.status_code == 200, r.text
    receipt = r.json()
    assert receipt["chosen_record_id"] == target
    assert receipt["previous_record_id"] == conflict["winner"]
    # 无论并发时哪一笔先计薪，改选后只有目标所在学院计入，原学院归零。
    target_dept = next(rec["department"] for rec in receipt["records"] if rec["id"] == target)
    winner_dept = next(rec["department"] for rec in receipt["records"] if rec["id"] == conflict["winner"])
    previews = {p["department"]: p["total_approved_hours"] for p in receipt["previews"]}
    assert previews[target_dept] == pytest.approx(1.75)
    assert previews[winner_dept] == pytest.approx(0.0)

    detail = client.get(f"/adjudications/{case['id']}", headers=conflict["admin"]).json()
    assert detail["winner_record_id"] == target
    statuses = {r["id"]: r["status"] for r in detail["records"]}
    assert statuses[target] == "approved"
    assert statuses[conflict["winner"]] == "adjudication_pending"
    assert detail["decisions"][-1]["reason"] == "乙学院课程要求现场签到，排班窗口完全吻合"
    assert detail["decisions"][-1]["chosen_record_id"] == target
    assert len(detail["decisions"]) == 1


def test_retry_receipt_does_not_double_account(client, conflict):
    case = client.get("/adjudications", headers=conflict["admin"]).json()["items"][0]
    target = case["winner_record_id"]
    before = client.get(f"/adjudications/{case['id']}", headers=conflict["admin"]).json()
    r = client.post(
        f"/adjudications/{case['id']}/decisions",
        json={"chosen_record_id": target, "reason": "乙学院课程要求现场签到，排班窗口完全吻合", "expected_version": 0},
        headers={**conflict["admin"], "Idempotency-Key": "switch-1"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["replayed"] is True
    assert r.json()["superseded"] is False
    after = client.get(f"/adjudications/{case['id']}", headers=conflict["admin"]).json()
    assert len(after["decisions"]) == len(before["decisions"])
    assert after["version"] == before["version"]
    assert after["winner_record_id"] == target


def test_old_receipt_retry_never_overwrites_later_decision(client, conflict):
    case = client.get("/adjudications", headers=conflict["admin"]).json()["items"][0]
    current = case["winner_record_id"]
    other = conflict["a"] if current == conflict["b"] else conflict["b"]

    r = client.post(
        f"/adjudications/{case['id']}/decisions",
        json={"chosen_record_id": other, "reason": "复核后发现另一笔签到更符合排班窗口", "expected_version": case["version"]},
        headers={**conflict["admin"], "Idempotency-Key": "switch-2"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["chosen_record_id"] == other

    replayed = client.post(
        f"/adjudications/{case['id']}/decisions",
        json={"chosen_record_id": current, "reason": "乙学院课程要求现场签到，排班窗口完全吻合", "expected_version": 0},
        headers={**conflict["admin"], "Idempotency-Key": "switch-1"},
    )
    assert replayed.status_code == 200, replayed.text
    assert replayed.json()["replayed"] is True
    assert replayed.json()["superseded"] is True
    assert replayed.json()["current"]["winner_record_id"] == other

    detail = client.get(f"/adjudications/{case['id']}", headers=conflict["admin"]).json()
    assert detail["winner_record_id"] == other
    assert len(detail["decisions"]) == 2


def test_stale_version_keeps_original_decision(client, conflict):
    case = client.get("/adjudications", headers=conflict["admin"]).json()["items"][0]
    winner_before = case["winner_record_id"]
    stale_target = conflict["a"] if winner_before == conflict["b"] else conflict["b"]
    r = client.post(
        f"/adjudications/{case['id']}/decisions",
        json={"chosen_record_id": stale_target, "reason": "基于旧页面的改选", "expected_version": case["version"] - 1},
        headers={**conflict["admin"], "Idempotency-Key": "stale-1"},
    )
    assert r.status_code == 409
    detail = client.get(f"/adjudications/{case['id']}", headers=conflict["admin"]).json()
    assert detail["winner_record_id"] == winner_before
    assert len(detail["decisions"]) == 2


def test_rejected_switch_keeps_original_decision_intact(client, conflict):
    case = client.get("/adjudications", headers=conflict["admin"]).json()["items"][0]
    before = client.get(f"/adjudications/{case['id']}", headers=conflict["admin"]).json()
    loser = conflict["a"] if case["winner_record_id"] == conflict["b"] else conflict["b"]

    # 把待改选记录的有效工时改成 0，模拟业务校验失败：整笔事务回滚，原决定保留。
    with get_conn() as conn:
        conn.execute("UPDATE work_records SET validated_hours=0 WHERE id=%s", (loser,))
    try:
        r = client.post(
            f"/adjudications/{case['id']}/decisions",
            json={"chosen_record_id": loser, "reason": "尝试改选无效记录", "expected_version": case["version"]},
            headers={**conflict["admin"], "Idempotency-Key": "invalid-1"},
        )
        assert r.status_code == 409
    finally:
        with get_conn() as conn:
            conn.execute("UPDATE work_records SET validated_hours=1.75 WHERE id=%s", (loser,))

    after = client.get(f"/adjudications/{case['id']}", headers=conflict["admin"]).json()
    assert after["winner_record_id"] == before["winner_record_id"]
    assert after["version"] == before["version"]
    assert len(after["decisions"]) == len(before["decisions"])
    previews_before = {p["department"]: p["total_approved_hours"] for p in before["previews"]}
    previews_after = {p["department"]: p["total_approved_hours"] for p in after["previews"]}
    assert previews_after == previews_before


def test_second_approval_cannot_reverse_existing_decision(client, conflict):
    """已裁决的冲突对再次审批时，只保留待裁决状态，不得绕过学院裁决翻转计薪方。"""
    case = client.get("/adjudications", headers=conflict["admin"]).json()["items"][0]
    winner = case["winner_record_id"]
    loser = conflict["a"] if winner == conflict["b"] else conflict["b"]
    # 把落选记录重新置为 submitted，再让教师审批它。
    with get_conn() as conn:
        conn.execute("UPDATE work_records SET status='submitted' WHERE id=%s", (loser,))
    r = client.post(f"/work-records/{loser}/review", json={"note": "教师再次审批"}, headers=conflict["teacher"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "adjudication_pending"
    detail = client.get(f"/adjudications/{case['id']}", headers=conflict["admin"]).json()
    assert detail["winner_record_id"] == winner
    statuses = {rec["id"]: rec["status"] for rec in detail["records"]}
    assert statuses[loser] == "adjudication_pending"
    assert statuses[winner] == "approved"


def test_approval_page_exposes_both_records_and_reasons(client, conflict):
    records = client.get("/work-records", headers=conflict["teacher"]).json()["items"]
    ids = {r["id"] for r in records}
    assert {conflict["a"], conflict["b"]} <= ids
    detail = client.get("/adjudications", headers=conflict["teacher"]).json()["items"][0]
    assert len(detail["records"]) == 2
    assert {d["reason"] for d in detail["decisions"]} == {
        "乙学院课程要求现场签到，排班窗口完全吻合",
        "复核后发现另一笔签到更符合排班窗口",
    }
    # 助教只能看到涉及自己的案例，其他助教看不到。
    assert client.get("/adjudications", headers=conflict["ta"]).json()["items"]
