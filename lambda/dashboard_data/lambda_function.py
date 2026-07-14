"""Lambda 6 — 대시보드 데이터 조회 (dashboard_data)

GET /dashboard 로 호출되어 대시보드가 그릴 전체 데이터를 반환한다.
MVP: 목데이터 반환 / 실제: DynamoDB(detection-results, purchase-orders) 조회.

반환 구조는 프론트엔드 App.jsx의 loadDashboard()가 기대하는 형태에 맞춘다:
  {
    "summary":     { total, critical, warning, normal },
    "equipments":  [ ...설비 상세... ],   # App.jsx가 setEquipments로 사용
    "order":       { id, createdAt, decisions, lines },  # setOrder로 사용
    "recent_recommendations": [ ... ]     # (역할분담서 반환 구조 항목)
  }
"""
import sys
import os

_HERE = os.path.dirname(__file__)
sys.path.insert(0, _HERE)                       # 로컬 테스트에서도 mock_dashboard 임포트 보장
sys.path.append(os.path.join(_HERE, ".."))      # common 패키지 접근
from common.utils import parse_event_body, api_response  # noqa: E402
from mock_dashboard import MOCK_EQUIPMENTS, MOCK_ORDER  # noqa: E402


def build_summary(equipments):
    return {
        "total": len(equipments),
        "critical": sum(1 for e in equipments if e["status"] == "critical"),
        "warning": sum(1 for e in equipments if e["status"] == "warning"),
        "normal": sum(1 for e in equipments if e["status"] == "normal"),
    }


def build_recent_recommendations(equipments):
    """최근 AI 권고 목록 — 설비명 / 위험도 / 권고 내용 / 필요 부품."""
    recs = []
    for e in equipments:
        if e["status"] == "normal":
            continue
        recs.append(
            {
                "facility_id": e["id"],
                "status": e["status"],
                "recommendation": e["maintenanceRec"]["recommendation"],
                "parts": e["maintenanceRec"]["parts"],
            }
        )
    return recs


def get_dashboard(use_mock):
    if use_mock:
        equipments = MOCK_EQUIPMENTS
        order = MOCK_ORDER
    else:
        # 실제 연동: detection-results 스캔 → 설비 목록 구성, purchase-orders 조회
        # (임수희/허소영 파트의 저장 스키마 확정 후 매핑)
        from common.aws import get_table

        det = get_table("DYNAMODB_DETECTION_TABLE", "detection-results")
        equipments = det.scan().get("Items", [])
        order = MOCK_ORDER  # 발주 병합 로직 확정 전까지 목 유지

    return {
        "summary": build_summary(equipments),
        "equipments": equipments,
        "order": order,
        "recent_recommendations": build_recent_recommendations(equipments),
    }


def handler(event, context):
    body = parse_event_body(event)
    use_mock = body.get("use_mock", False)
    return api_response(200, get_dashboard(use_mock))


lambda_handler = handler
