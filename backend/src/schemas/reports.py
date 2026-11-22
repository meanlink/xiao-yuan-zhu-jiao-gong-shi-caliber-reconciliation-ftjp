from pydantic import BaseModel, Field

class ReportRequest(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    department: str = Field(min_length=2, max_length=80)
