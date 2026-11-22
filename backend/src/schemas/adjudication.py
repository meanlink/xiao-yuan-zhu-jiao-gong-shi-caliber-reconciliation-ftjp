from pydantic import BaseModel, Field


class AdjudicationDecisionRequest(BaseModel):
    chosen_record_id: int
    reason: str = Field(min_length=2, max_length=500)
    expected_version: int | None = None
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=120)
