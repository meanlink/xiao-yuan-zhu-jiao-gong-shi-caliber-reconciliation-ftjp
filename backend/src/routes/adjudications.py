import hashlib

from fastapi import APIRouter, Depends, Header, HTTPException
from ..db import get_conn
from ..schemas.adjudication import AdjudicationDecisionRequest
from ..services import adjudication
from .deps import current_user, require_roles

router = APIRouter(prefix="/adjudications", tags=["adjudications"])


def _idempotency_key(case_id: int, payload: AdjudicationDecisionRequest, header_key: str | None) -> str:
    """客户端应显式传入幂等键；缺省时用请求内容派生，保证同样的重试不会重复记账。"""
    if header_key and header_key.strip():
        return header_key.strip()[:120]
    if payload.idempotency_key:
        return payload.idempotency_key
    raw = f"{case_id}:{payload.chosen_record_id}:{payload.expected_version}:{payload.reason}"
    return "auto-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:48]


@router.get("")
def list_cases(month: str | None = None, user=Depends(current_user)):
    with get_conn() as conn:
        return {"items": adjudication.list_cases(conn, user, month)}


@router.get("/{case_id}")
def get_case(case_id: int, user=Depends(current_user)):
    with get_conn() as conn:
        return adjudication.get_case(conn, case_id, user)


@router.post("/{case_id}/decisions")
def decide(
    case_id: int,
    payload: AdjudicationDecisionRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    user=Depends(require_roles("college_admin")),
):
    key = _idempotency_key(case_id, payload, idempotency_key)
    with get_conn() as conn:
        receipt = adjudication.decide(
            conn,
            case_id=case_id,
            chosen_record_id=payload.chosen_record_id,
            reason=payload.reason,
            idempotency_key=key,
            expected_version=payload.expected_version,
            actor_id=user["id"],
        )
    return receipt
