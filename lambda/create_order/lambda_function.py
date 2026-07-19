"""Lambda 5 — 발주서 생성 (create_order)

재고 부족 시 실행되어 purchase-orders 테이블에 발주 기록을 저장한다.
프론트엔드 발주 승인/거절 액션(POST /order)도 이 Lambda로 라우팅된다.

두 가지 호출 형태를 지원한다:
1) 발주서 생성 (Action Group / 대시보드):
   { "facility_id": "설비2", "required_part": "베어링B",
     "recommendation": "베어링 즉시 교체 권고", "qty": 1 }
   → order_id 발급 후 저장

2) 발주 상태 변경 (프론트 승인/거절):
   { "order_id": "PO-...", "facility_id": "L47340",
     "decision": "approved", "decided_by": "admin" }
   → 해당 발주의 설비별 상태 갱신
"""
import sys
import os
import uuid
from datetime import datetime, timezone

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from common.utils import parse_event_body, api_response  # noqa: E402

VALID_DECISIONS = ("pending", "approved", "rejected", "ordered")


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _new_order_id():
    # 사람이 읽기 쉬운 발주번호: PO-<날짜>-<랜덤4자리>
    return f"PO-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"


def notify_order_saved(body, use_mock):
    """통합 발주서 저장 알림 — DynamoDB에 쓰지 않고 SNS 메시지 1건만 발행."""
    order_id = body.get("order_id", "") or ""
    if not isinstance(order_id, str):
        order_id = str(order_id)
    decided_by = body.get("decided_by", "unknown") or "unknown"
    items = body.get("items")
    if not isinstance(items, list):
        items = []

    # 품목 라인 방어적으로 구성
    item_lines = []
    for it in items:
        if not isinstance(it, dict):
            continue
        facility_id = it.get("facility_id", "-") or "-"
        label = it.get("part_name") or it.get("part_id") or "-"
        quantity = it.get("quantity", 1)
        if quantity is None:
            quantity = 1
        item_lines.append(f"- {facility_id} / {label} x {quantity}")

    subject = f"[통합발주서 저장] {order_id}"
    if len(subject) > 100:
        subject = subject[:100]

    message = (
        "통합 발주서가 저장되었습니다.\n"
        f"발주번호: {order_id}\n"
        f"승인자: {decided_by}\n"
        f"시각: {_now_iso()}\n"
        f"포함 설비: {len(item_lines)}대\n"
        "\n"
        "[품목]\n"
        + ("\n".join(item_lines) if item_lines else "-")
    )

    if not use_mock:
        from common.aws import get_sns

        topic_arn = os.environ.get("SNS_ORDER_COMPLETED_TOPIC")
        if isinstance(topic_arn, str) and topic_arn:
            try:
                get_sns().publish(TopicArn=topic_arn, Subject=subject, Message=message)
            except Exception as e:  # noqa: BLE001 — 알림 실패가 응답을 깨지 않도록 무시
                print(f"[notify_order_saved] SNS publish 실패 — 무시: {e}")

    return api_response(200, {"notified": True, "order_id": order_id, "item_count": len(items or [])})


def create_order(body, use_mock):
    facility_id = body.get("facility_id")
    part = body.get("required_part")
    if not facility_id or not part:
        return api_response(400, {"error": "facility_id, required_part가 필요합니다."})

    try:
        qty = int(body.get("qty", 1))
        if qty < 1:
            raise ValueError
    except (ValueError, TypeError):
        return api_response(400, {"error": "qty는 1 이상의 정수여야 합니다."})

    order = {
        "order_id": _new_order_id(),
        "timestamp": _now_iso(),
        "facility_id": facility_id,
        "required_part": part,
        "qty": qty,
        "recommendation": body.get("recommendation", ""),
        "status": "pending",
    }

    if not use_mock:
        from common.aws import get_table

        table = get_table("DYNAMODB_ORDER_TABLE", "purchase-orders")
        table.put_item(Item=order)

    return api_response(200, {"created": True, "order": order})


def update_decision(body, use_mock):
    order_id = body.get("order_id")
    facility_id = body.get("facility_id")
    decision = body.get("decision")
    if decision not in VALID_DECISIONS:
        return api_response(400, {"error": f"decision은 {VALID_DECISIONS} 중 하나여야 합니다."})

    record = {
        "order_id": order_id,
        "facility_id": facility_id,
        "status": decision,
        "decided_by": body.get("decided_by", "unknown"),
        "decided_at": _now_iso(),
    }

    # 부품/고장 정보(있을 때만 저장) — 프론트 신규 페이로드(part_id/part_name/qty/failure_type)와
    # 과거 단일 필드 호출(required_part/quantity) 두 형태를 모두 수용
    failure_type = body.get("failure_type")
    if isinstance(failure_type, str) and failure_type:
        record["failure_type"] = failure_type

    part_id = body.get("part_id")
    if isinstance(part_id, str) and part_id:
        record["part_id"] = part_id

    part_name = body.get("part_name")
    if not (isinstance(part_name, str) and part_name):
        part_name = body.get("required_part")
    if isinstance(part_name, str) and part_name:
        record["part_name"] = part_name

    qty_raw = body.get("quantity")
    if qty_raw is None:
        qty_raw = body.get("qty")
    if qty_raw is not None:
        try:
            record["quantity"] = int(qty_raw)
        except (ValueError, TypeError):
            pass

    if not use_mock:
        from common.aws import get_table

        table = get_table("DYNAMODB_ORDER_TABLE", "purchase-orders")
        # PK: order_id, SK: timestamp — 설비별 결정 이력을 append은
        table.put_item(Item={**record, "timestamp": record["decided_at"]})

    return api_response(200, {"updated": True, "decision": record})


def handler(event, context):
    body = parse_event_body(event)
    use_mock = body.get("use_mock", False)

    # 통합 발주서 저장 알림 — DynamoDB 미기록, SNS 1건만 발행
    if body.get("notify") == "order_saved":
        return notify_order_saved(body, use_mock)

    # decision 필드가 있으면 상태 변경, 없으면 신규 발주 생성
    if body.get("decision") is not None:
        return update_decision(body, use_mock)
    return create_order(body, use_mock)


lambda_handler = handler
