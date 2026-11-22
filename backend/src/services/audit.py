import json
from ..db import get_conn

def record_audit(actor_id: int | None, action: str, entity_type: str, entity_id: int | None, detail: dict):
    with get_conn() as conn:
        conn.execute("INSERT INTO audit_logs(actor_id, action, entity_type, entity_id, detail_json) VALUES (%s,%s,%s,%s,%s)", (actor_id, action, entity_type, entity_id, json.dumps(detail, ensure_ascii=False)))
