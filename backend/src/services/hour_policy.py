from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

TOLERANCE_MINUTES = 30


def _round_quarter(value: Decimal) -> Decimal:
    return (value * 4).quantize(Decimal("1"), rounding=ROUND_HALF_UP) / 4


def validate_work_hours(record: dict, course: dict) -> dict:
    """返回领域校验结果。排班冲突、缺签和超过单次口径上限不能直接进入审批。"""
    issues = []
    check_in = record.get("check_in")
    check_out = record.get("check_out")
    if not check_in or not check_out:
        issues.append("missing_checkin")
    else:
        weekday = check_in.isoweekday()
        if weekday != course["weekday"]:
            issues.append("weekday_conflict")
        schedule_start = datetime.combine(check_in.date(), course["start_time"], tzinfo=check_in.tzinfo)
        schedule_end = datetime.combine(check_in.date(), course["end_time"], tzinfo=check_in.tzinfo)
        if check_in < schedule_start - timedelta(minutes=TOLERANCE_MINUTES) or check_in > schedule_start + timedelta(minutes=TOLERANCE_MINUTES):
            issues.append("checkin_outside_schedule")
        if check_out < schedule_end - timedelta(minutes=TOLERANCE_MINUTES) or check_out > schedule_end + timedelta(minutes=TOLERANCE_MINUTES):
            issues.append("checkout_outside_schedule")
        if check_out <= check_in:
            issues.append("invalid_interval")
    if issues:
        return {"status": "manual_review", "validated_hours": Decimal("0.00"), "conflict_type": ",".join(issues)}
    actual_hours = Decimal(str((check_out - check_in).total_seconds() / 3600)).quantize(Decimal("0.01"))
    reported = Decimal(str(record["reported_hours"]))
    cap = Decimal(str(course["expected_hours"]))
    validated = _round_quarter(min(actual_hours, reported, cap))
    if validated <= 0:
        return {"status": "manual_review", "validated_hours": Decimal("0.00"), "conflict_type": "zero_effective_hours"}
    return {"status": "submitted", "validated_hours": validated, "conflict_type": None}


def pivot_monthly(rows: list[dict], month: str) -> dict:
    """按学院、课程班、活动类型、助教做透视汇总，只消费 approved 行。"""
    groups = {}
    approved_hours = Decimal("0")
    for row in rows:
        if str(row["work_date"])[:7] != month or row["status"] != "approved":
            continue
        key = (row["department"], row["class_code"], row["course_name"], row["activity_type"], row["ta_name"])
        item = groups.setdefault(key, {"department": key[0], "class_code": key[1], "course_name": key[2], "activity_type": key[3], "ta_name": key[4], "approved_hours": Decimal("0"), "approved_record_count": 0})
        item["approved_hours"] += Decimal(str(row["validated_hours"]))
        item["approved_record_count"] += 1
        approved_hours += Decimal(str(row["validated_hours"]))
    values = []
    for item in groups.values():
        item["approved_hours"] = float(item["approved_hours"])
        values.append(item)
    values.sort(key=lambda x: (x["department"], x["class_code"], x["activity_type"], x["ta_name"]))
    return {"month": month, "rows": values, "total_approved_hours": float(approved_hours), "row_count": len(values)}
