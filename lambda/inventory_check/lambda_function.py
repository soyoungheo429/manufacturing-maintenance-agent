"""Lambda 4 — 재고 확인 (inventory_check)

parts-inventory 테이블을 조회해 부품 재고 유무를 판정한다.
- 재고 부족(0)  → has_stock=false, action="CREATE_ORDER"  (발주서 생성 트리거)
- 재고 있음      → has_stock=true,  action="NOTIFY_ONLY"   (알림만)

Action Group 2(maintenance-solution)에서 create_order 앞단으로 호출된다.

입력: { "required_part": "베어링B", "qty": 1, "use_mock": true }
"""
import sys
import os

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from common.utils import parse_event_body, api_response  # noqa: E402

# MVP 목업 재고 — 실제 연동 시 DynamoDB parts-inventory 테이블로 대체
# 프론트엔드 constants.js의 PARTS_INVENTORY와 동일 품목 유지
MOCK_INVENTORY = {
    "베어링A": 2,
    "베어링B": 0,   # 재고 없음 → 발주 트리거
    "공구날": 5,
    "냉각수": 3,
    "윤활유": 0,    # 재고 없음 → 발주 트리거
    # 프론트엔드 부품명 체계
    "절삭공구 인서트 #T-4812": 5,
    "스핀들 베어링 6204-2RS": 0,
    "구동 모터 3상 1.5kW": 0,
    "전력 드라이버 FR-A740-0.4K": 1,
    "냉각팬 AC-9238": 1,
    "방열판 HS-120AL": 0,
    "냉각수 펌프 CP-40W": 0,
}


def get_stock(part, use_mock):
    """부품 재고 반환. 미등록 부품이면 None(재고 0과 구분)."""
    if use_mock:
        return MOCK_INVENTORY.get(part)  # 미등록 시 None
    # 실제 연동: parts-inventory 테이블 조회 (PK: part_id, 재고 필드명: quantity)
    from common.aws import get_table

    table = get_table("DYNAMODB_INVENTORY_TABLE", "parts-inventory")
    resp = table.get_item(Key={"part_id": part})
    item = resp.get("Item")
    return int(item["quantity"]) if item else None


def check_part(part, required_qty, use_mock):
    stock = get_stock(part, use_mock)
    # 미등록 부품(오타 등)은 재고 0으로 간주하지 않고 별도 액션으로 구분 —
    # 조용히 CREATE_ORDER가 트리거되어 오발주가 나가는 것을 방지
    if stock is None:
        return {
            "required_part": part,
            "required_qty": required_qty,
            "stock": None,
            "order_qty": 0,
            "has_stock": False,
            "action": "UNKNOWN_PART",
        }
    order_qty = max(0, required_qty - stock)
    has_stock = order_qty == 0
    return {
        "required_part": part,
        "required_qty": required_qty,
        "stock": stock,
        "order_qty": order_qty,          # 재고 차감 후 실제 발주 필요 수량
        "has_stock": has_stock,
        "action": "NOTIFY_ONLY" if has_stock else "CREATE_ORDER",
    }


def _parse_qty(raw):
    """qty를 양의 정수로 파싱. 실패 시 ValueError."""
    qty = int(raw)
    if qty < 1:
        raise ValueError("qty는 1 이상이어야 합니다.")
    return qty


def handler(event, context):
    body = parse_event_body(event)
    use_mock = body.get("use_mock", False)

    try:
        # 단일 부품(required_part) 또는 다중 부품(parts 리스트) 모두 지원
        # 필드명은 단일/배치 모두 required_part로 통일
        if "parts" in body:
            items = body["parts"]
            results = [
                check_part(p.get("required_part"), _parse_qty(p.get("qty", 1)), use_mock)
                for p in items
            ]
            need_order = any(r["action"] == "CREATE_ORDER" for r in results)
            return api_response(200, {"results": results, "need_order": need_order})

        part = body.get("required_part")
        if not part:
            return api_response(400, {"error": "required_part 파라미터가 필요합니다."})
        qty = _parse_qty(body.get("qty", 1))
        return api_response(200, check_part(part, qty, use_mock))
    except (ValueError, TypeError):
        return api_response(400, {"error": "qty는 1 이상의 정수여야 합니다."})


# AWS Lambda 진입점 별칭
lambda_handler = handler
