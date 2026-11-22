from datetime import datetime, date
from decimal import Decimal
from pydantic import BaseModel, Field

class WorkRecordCreate(BaseModel):
    class_id: int
    work_date: date
    check_in: datetime | None = None
    check_out: datetime | None = None
    activity_type: str = Field(min_length=2, max_length=80)
    work_description: str = Field(min_length=4, max_length=500)
    reported_hours: Decimal = Field(gt=0, le=12)

class ReviewRequest(BaseModel):
    note: str = Field(default="", max_length=500)
