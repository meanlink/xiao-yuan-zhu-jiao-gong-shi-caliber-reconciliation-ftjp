from .hour_policy import pivot_monthly

PIVOT_SQL = """SELECT w.work_date,w.status,w.validated_hours,w.activity_type,c.department,c.code AS class_code,c.course_name,u.name AS ta_name
    FROM work_records w JOIN course_classes c ON c.id=w.class_id JOIN users u ON u.id=w.ta_id
    WHERE c.department=%s AND w.work_date >= (%s || '-01')::date AND w.work_date < ((%s || '-01')::date + interval '1 month')"""


def fetch_pivot_rows(conn, department: str, month: str) -> list[dict]:
    return conn.execute(PIVOT_SQL, (department, month, month)).fetchall()


def monthly_preview(conn, department: str, month: str) -> dict:
    """按数据库当前已审批记录实时透视，调用方可放在同一事务里读取多个学院。"""
    result = pivot_monthly([dict(r) for r in fetch_pivot_rows(conn, department, month)], month)
    result["department"] = department
    return result
