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
import json
import logging
from datetime import datetime, timezone

_HERE = os.path.dirname(__file__)
sys.path.insert(0, _HERE)                       # 로컬 테스트에서도 mock_dashboard 임포트 보장
sys.path.append(os.path.join(_HERE, ".."))      # common 패키지 접근
from common.utils import parse_event_body, api_response  # noqa: E402
from mock_dashboard import MOCK_EQUIPMENTS, MOCK_ORDER  # noqa: E402


logger = logging.getLogger(__name__)


STATUS_MAP = {
    "DANGER": "critical",
    "CRITICAL": "critical",
    "WARNING": "warning",
    "CAUTION": "warning",
    "NORMAL": "normal",
    "OK": "normal",
}


# 정비 매뉴얼 기준 고장 유형 → 부품 코드 매핑 (RNF는 매뉴얼상 대응 부품 없음 → 의도적으로 제외)
PART_CODE_BY_FAILURE = {
    "TWF": "TW-101",
    "HDF": "HD-202",
    "PWF": "PW-303",
    "OSF": "OS-404",
}


def _load_inventory():
    """parts-inventory 테이블을 스캔해 {part_id(str): quantity(int)} 맵을 반환.

    quantity가 Decimal/str 이어도 int로 강제 변환한다. part_id가 비어있거나
    문자열이 아닌 행, quantity를 파싱할 수 없는 행은 logger.warning 후 건너뛴다.
    기존 무페이지네이션 스타일과 동일하게 단일 ``.scan().get("Items", [])`` 사용.
    """
    from common.aws import get_table

    table = get_table("DYNAMODB_INVENTORY_TABLE", "parts-inventory")
    items = table.scan().get("Items", [])
    inventory = {}
    for item in items:
        if not isinstance(item, dict):
            logger.warning("Skipping invalid parts-inventory record: expected object")
            continue
        part_id = item.get("part_id")
        if not isinstance(part_id, str) or not part_id.strip():
            logger.warning("Skipping parts-inventory record with invalid part_id")
            continue
        try:
            quantity = int(item.get("quantity"))
        except (TypeError, ValueError):
            logger.warning(
                "Skipping parts-inventory record with unparseable quantity for part_id=%s",
                part_id,
            )
            continue
        inventory[part_id.strip()] = quantity
    return inventory


def _safe_json_loads(raw, expected_type, field_name):
    """Parse a DynamoDB JSON field and enforce its required container shape."""
    parsed = raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError, ValueError):
            logger.warning("Invalid %s: malformed JSON; using empty structure", field_name)
            return expected_type()

    if not isinstance(parsed, expected_type):
        logger.warning(
            "Invalid %s: expected %s, got %s; using empty structure",
            field_name,
            expected_type.__name__,
            type(parsed).__name__,
        )
        return expected_type()
    return parsed


def _parse_iso8601_timestamp(raw):
    """Return a UTC datetime for an ISO-8601 timestamp, or None when invalid."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    value = raw.strip()
    if value.endswith(("Z", "z")):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _stable_item_key(item):
    """Provide deterministic tie-breaking when timestamps represent the same instant."""
    return json.dumps(item, sort_keys=True, default=str, ensure_ascii=False)


def select_latest_valid_records(items):
    """Select exactly one latest valid record for each nonempty facility ID."""
    latest = {}
    for item in items:
        if not isinstance(item, dict):
            logger.warning("Skipping invalid detection record: expected object")
            continue
        facility_id = item.get("facility_id")
        if not isinstance(facility_id, str) or not facility_id.strip():
            logger.warning("Skipping detection record with invalid facility_id")
            continue
        parsed_timestamp = _parse_iso8601_timestamp(item.get("timestamp"))
        if parsed_timestamp is None:
            logger.warning(
                "Skipping detection record with invalid timestamp for facility_id=%s",
                facility_id,
            )
            continue

        candidate_key = (parsed_timestamp, _stable_item_key(item))
        current = latest.get(facility_id)
        if current is None or candidate_key > current[0]:
            latest[facility_id] = (candidate_key, item)

    return [latest[facility_id][1] for facility_id in sorted(latest)]


VALID_ORDER_DECISIONS = ("pending", "approved", "rejected", "ordered")


def _valid_purchase_order_rows(items):
    """Return purchase-order rows that are dicts with a non-blank order_id.

    Non-dict rows and rows with a missing/blank order_id are skipped with a
    warning. facility_id validation is deferred to the line/decision builders so
    that a single row can be rejected in exactly one place.
    """
    rows = []
    for item in items:
        if not isinstance(item, dict):
            logger.warning("Skipping invalid purchase-order record: expected object")
            continue
        order_id = item.get("order_id")
        if not isinstance(order_id, str) or not order_id.strip():
            logger.warning("Skipping purchase-order record with missing/blank order_id")
            continue
        rows.append(item)
    return rows


def _select_most_recent_order_id(rows):
    """Return the order_id of the most-recent row overall (latest valid timestamp).

    Considers every row (creation and decision alike). Ties break deterministically
    by a stable serialization of the row. Returns "" when no row has a valid
    timestamp.
    """
    best_key = None
    best_id = ""
    for row in rows:
        parsed_ts = _parse_iso8601_timestamp(row.get("timestamp"))
        if parsed_ts is None:
            continue
        candidate_key = (parsed_ts, _stable_item_key(row))
        if best_key is None or candidate_key > best_key:
            best_key = candidate_key
            best_id = row.get("order_id", "").strip()
    return best_id


def _resolve_part_name(row):
    """Resolve a row's part name across both producer conventions.

    Precedence: ``required_part`` (frontend/create_order path) first; if
    missing/blank, ``part_name`` (Bedrock Agent path); if still missing/blank,
    ``part_id`` (Agent path, e.g. "OS-404"). Returns a stripped non-empty string,
    or None when none is present.
    """
    for field in ("required_part", "part_name", "part_id"):
        value = row.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _resolve_part_id(row):
    """Resolve a row's part code (part_id) when present and non-empty.

    Returns the stripped ``part_id`` string, or None when the field is missing,
    not a string, or blank. This is the machine-readable code (e.g. "OS-404")
    distinct from the human-facing display name resolved by ``_resolve_part_name``.
    """
    value = row.get("part_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _coerce_qty(raw):
    """Coerce a stored qty (possibly Decimal/str) to int, defaulting to 1 on failure."""
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 1


def _resolve_qty(row):
    """Read a row's quantity across both conventions: ``qty`` first, else ``quantity``.

    The chosen field is coerced via ``_coerce_qty`` (Decimal/str -> int, default 1).
    """
    if "qty" in row:
        return _coerce_qty(row.get("qty"))
    return _coerce_qty(row.get("quantity"))


_EPOCH = datetime.min.replace(tzinfo=timezone.utc)


def _build_order_lines(rows):
    """Build lines from creation rows (resolvable part name), ascending by timestamp.

    A row is treated as a creation/line row iff its part name resolves to a
    non-empty string across either producer convention (see ``_resolve_part_name``).
    """
    creation = []
    for idx, row in enumerate(rows):
        part = _resolve_part_name(row)
        if part is None:
            continue
        facility_id = row.get("facility_id")
        if not isinstance(facility_id, str) or not facility_id.strip():
            logger.warning("Skipping order line with invalid facility_id")
            continue
        parsed_ts = _parse_iso8601_timestamp(row.get("timestamp"))
        creation.append((idx, parsed_ts, row, facility_id.strip(), part))

    # Preserve insertion order by ascending timestamp; rows without a valid
    # timestamp fall to the end while keeping their original relative order.
    creation.sort(key=lambda t: (t[1] is None, t[1] or _EPOCH, t[0]))

    lines = []
    seen = set()
    for _idx, _ts, row, facility_id, part in creation:
        dedup_key = (facility_id, part)
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        line = {
            "equipmentId": facility_id,
            "part": part,
            "qty": _resolve_qty(row),
        }
        part_id = _resolve_part_id(row)
        if part_id:
            line["partId"] = part_id
        if row.get("referenceOnly"):
            line["referenceOnly"] = True
        lines.append(line)
    return lines


def _build_order_decisions(rows, lines):
    """Map each facility_id to the status of its latest-timestamp row (unknown -> pending)."""
    latest = {}
    for item in rows:
        facility_id = item.get("facility_id")
        if not isinstance(facility_id, str) or not facility_id.strip():
            continue
        parsed_ts = _parse_iso8601_timestamp(item.get("timestamp"))
        if parsed_ts is None:
            continue
        fid = facility_id.strip()
        raw_status = item.get("status")
        status = raw_status.strip().lower() if isinstance(raw_status, str) else ""
        if status not in VALID_ORDER_DECISIONS:
            status = None
        candidate_key = (parsed_ts, _stable_item_key(item))
        current = latest.get(fid)
        if current is None or candidate_key > current[0]:
            latest[fid] = (candidate_key, status)

    decisions = {fid: (status or "pending") for fid, (_key, status) in latest.items()}
    # Ensure every facility that appears in lines has a decisions entry.
    for line in lines:
        decisions.setdefault(line["equipmentId"], "pending")
    return decisions


def _earliest_creation_timestamp(rows):
    """Return the earliest creation-row timestamp string, or '' when unknown."""
    best = None
    best_raw = ""
    for row in rows:
        if _resolve_part_name(row) is None:
            continue
        parsed_ts = _parse_iso8601_timestamp(row.get("timestamp"))
        if parsed_ts is None:
            continue
        if best is None or parsed_ts < best:
            best = parsed_ts
            raw = row.get("timestamp")
            best_raw = raw.strip() if isinstance(raw, str) else ""
    return best_raw


def _build_supplement_lines(detection_equipments, po_lines):
    """Build supplement lines from detection equipments for faulty facilities.

    For each mapped equipment dict whose status is not "normal", whose
    maintenanceRec.parts contains a non-blank part string, and whose id is not
    already represented among ``po_lines`` (the existing purchase-orders lines),
    append a line ``{"equipmentId": <id>, "part": <first non-blank part>,
    "qty": 1}``. Supplement lines never carry ``partId`` or ``referenceOnly``.

    Facilities with a blank/missing id or no usable part are skipped, and a
    facility is supplemented at most once.
    """
    if not isinstance(detection_equipments, list):
        return []

    existing_ids = {
        line["equipmentId"]
        for line in po_lines
        if isinstance(line, dict) and isinstance(line.get("equipmentId"), str)
    }

    supplement = []
    seen = set()
    for equipment in detection_equipments:
        if not isinstance(equipment, dict):
            continue
        if equipment.get("status") == "normal":
            continue
        facility_id = equipment.get("id")
        if not isinstance(facility_id, str) or not facility_id.strip():
            continue
        fid = facility_id.strip()
        if fid in existing_ids or fid in seen:
            continue
        rec = equipment.get("maintenanceRec")
        parts = rec.get("parts") if isinstance(rec, dict) else None
        if not isinstance(parts, list):
            continue
        part = None
        for candidate in parts:
            if isinstance(candidate, str) and candidate.strip():
                part = candidate.strip()
                break
        if part is None:
            continue
        seen.add(fid)
        line = {"equipmentId": fid, "part": part, "qty": 1}
        # 이 설비의 failure_type(예: "OSF")을 부품 코드로 매핑해 partId를 붙인다.
        # 이래야 보충된 감지 라인도 parts-inventory와 매칭된다. part(품명)는 그대로 유지.
        fault_analysis = equipment.get("faultAnalysis")
        faults = fault_analysis.get("faults") if isinstance(fault_analysis, dict) else None
        failure_type = faults[0] if isinstance(faults, list) and faults else None
        part_code = PART_CODE_BY_FAILURE.get(failure_type) if isinstance(failure_type, str) else None
        if part_code:
            line["partId"] = part_code
        supplement.append(line)
    return supplement


def build_order_from_purchase_orders(items, detection_equipments=None, inventory=None):
    """Assemble the frontend order object from purchase-orders rows.

    Aggregates across ALL order_ids into a single consolidated order view, because
    creation rows (which carry required_part/qty) and decision rows (which carry
    decided_by/status) can live under different order_id values in the live table:

      * lines    — built from creation rows (rows with a resolvable part name via
                   required_part, part_name, or part_id) across every order_id,
                   de-duplicated by (facility_id, part) and ordered ascending by
                   timestamp; then SUPPLEMENTED with detection-derived lines for
                   faulty facilities (status != "normal") that have a required part
                   but no purchase-orders creation row.
      * decisions — each facility_id mapped to the status of its latest-timestamp
                   row across every row (creation and decision), defaulting to
                   "pending". Facilities that appear only in decision rows are kept,
                   and every line's equipmentId is guaranteed a decision entry.
      * id        — the order_id of the most-recent row overall.
      * createdAt — the earliest creation-row timestamp string.

    ``detection_equipments`` is an optional list of mapped equipment dicts (see
    ``map_detection_to_equipment``). When omitted (None) no supplementation occurs,
    preserving backward compatibility.

    ``inventory`` is an optional ``{part_id: int}`` map (see ``_load_inventory``).
    When provided, each line whose ``partId`` is a key in the map gets a ``stock``
    field set to the real quantity; lines without a known/matching code leave
    ``stock`` absent. When omitted (None) no stock is attached (backward compatible).

    Returns an empty order object only when both the final lines list and the
    decisions map are empty.
    """
    empty_order = {"id": "", "createdAt": "", "decisions": {}, "lines": []}
    if not isinstance(items, list):
        logger.warning("purchase-orders scan returned non-list; using empty order")
        rows = []
    else:
        rows = _valid_purchase_order_rows(items)

    po_lines = _build_order_lines(rows)
    supplement_lines = _build_supplement_lines(detection_equipments, po_lines)
    lines = po_lines + supplement_lines

    # 실제 parts-inventory 재고를 라인에 부착. partId(부품 코드)가 재고 맵의 키로
    # 존재할 때만 line["stock"]을 설정한다. 코드가 없거나 재고에 없으면 stock은 부재
    # ("unknown" — 프론트가 폴백 처리). inventory가 None이면 부착하지 않음(하위 호환).
    if isinstance(inventory, dict):
        for line in lines:
            part_id = line.get("partId")
            if isinstance(part_id, str) and part_id in inventory:
                line["stock"] = inventory[part_id]

    decisions = _build_order_decisions(rows, lines)
    created_at = _earliest_creation_timestamp(rows)
    order_id = _select_most_recent_order_id(rows)

    if not lines and not decisions:
        return empty_order

    return {
        "id": order_id,
        "createdAt": created_at,
        "decisions": decisions,
        "lines": lines,
    }


def _parse_use_mock(raw):
    """Strictly parse supported boolean values; unknown or missing values are false."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        value = raw.strip().lower()
        if value == "true":
            return True
        if value == "false":
            return False
    return False


def _risk_level_to_confidence(risk_level):
    """risk_level(0~100 숫자)을 confidence(high/medium/low)로 변환."""
    try:
        level = float(risk_level)
    except (TypeError, ValueError):
        return "medium"
    if level >= 70:
        return "high"
    if level >= 40:
        return "medium"
    return "low"


def _sensor_values_to_sensors(sensor_values):
    """실제 스키마의 snake_case 센서값을 프론트 camelCase sensors로 매핑."""
    sv = _safe_json_loads(sensor_values, dict, "sensor_values")
    if not sv:
        return {}
    return {
        "airTemp": sv.get("air_temp"),
        "processTemp": sv.get("process_temp"),
        "rotationSpeed": sv.get("rotation_speed"),
        "torque": sv.get("torque"),
        "toolWear": sv.get("tool_wear"),
    }


def _abnormal_sensors_to_metrics(abnormal_sensors):
    """abnormal_sensors(JSON 배열)를 derivedMetrics 형태로 매핑."""
    items = _safe_json_loads(abnormal_sensors, list, "abnormal_sensors")
    metrics = []
    for it in items:
        if not isinstance(it, dict):
            continue
        metrics.append(
            {
                "label": it.get("sensor", ""),
                "value": it.get("value"),
                "unit": it.get("unit", ""),
                "alert": True,
                "normal_range": it.get("normal_range", ""),
            }
        )
    return metrics


def _resolve_detection_part(item):
    """detection-results 행에서 재고 매칭용 부품 식별자를 뽑는다.

    ``part_id``(매뉴얼 코드, 예: "OS-404")가 있으면 최우선으로 쓴다 — 이게
    inventory_check/프론트 PARTS_INVENTORY의 키와 정확히 일치하는 값이기 때문.
    없으면 ``required_part``로 폴백한다 — 지금은 Bedrock Agent가 자유 텍스트
    ("cutting tool insert" 등)를 채워서 재고 매칭이 깨지는데, 프롬프트가
    코드만 출력하도록 고쳐지면 이 폴백 없이도 자동으로 정상화된다.
    """
    for field in ("part_id", "required_part"):
        value = item.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def map_detection_to_equipment(item):
    """detection-results 실제 스키마(facility_id, status='DANGER' 등) →
    프론트 equipments 스키마(id, status='critical' 등)로 변환.

    허소영/임수희 파트의 dynamo_save가 저장하는 실제 필드 기준 (콘솔에서 확인한 스키마).
    필드가 없을 경우 안전하게 기본값으로 대체한다.
    """
    raw_status = item.get("status")
    normalized_status = raw_status.strip().upper() if isinstance(raw_status, str) else ""
    status = STATUS_MAP.get(normalized_status)
    if status is None:
        logger.warning(
            "Unknown or missing status for facility_id=%s: %r; using warning",
            item.get("facility_id"),
            raw_status,
        )
        status = "warning"

    failure_type = item.get("failure_type", "")
    faults = [failure_type] if failure_type else []

    required_part = _resolve_detection_part(item)
    parts = [required_part] if required_part else []

    return {
        "id": item.get("facility_id", "UNKNOWN"),
        "status": status,
        "lastUpdated": item.get("timestamp", ""),
        "sensors": _sensor_values_to_sensors(item.get("sensor_values")),
        "faultAnalysis": {
            "faults": faults,
            "confidence": _risk_level_to_confidence(item.get("risk_level")),
            "diagnosis": item.get("recommendation", ""),
            "derivedMetrics": _abnormal_sensors_to_metrics(item.get("abnormal_sensors")),
        },
        "maintenanceRec": {
            "similarCases": [],
            "recommendation": item.get("recommendation", ""),
            "parts": parts,
        },
    }


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
        # 실제 연동: detection-results 스캔 → 최신 유효 설비별 레코드만 스키마 매핑
        from common.aws import get_table

        det = get_table("DYNAMODB_DETECTION_TABLE", "detection-results")
        raw_items = det.scan().get("Items", [])
        latest_items = select_latest_valid_records(raw_items)
        equipments = [map_detection_to_equipment(item) for item in latest_items]

        # 실제 연동: purchase-orders 스캔 → 최신 발주 1건을 프론트 order 구조로 조립
        orders_table = get_table("DYNAMODB_ORDER_TABLE", "purchase-orders")
        raw_orders = orders_table.scan().get("Items", [])

        # 실제 연동: parts-inventory 스캔 → 라인별 실제 재고량 부착
        inventory = _load_inventory()
        order = build_order_from_purchase_orders(raw_orders, equipments, inventory)

    return {
        "summary": build_summary(equipments),
        "equipments": equipments,
        "order": order,
        "recent_recommendations": build_recent_recommendations(equipments),
    }


def handler(event, context):
    body = parse_event_body(event)
    raw_use_mock = body.get("use_mock")
    if "use_mock" not in body and isinstance(event, dict):
        qs = event.get("queryStringParameters") or {}
        raw_use_mock = qs.get("use_mock")
    return api_response(200, get_dashboard(_parse_use_mock(raw_use_mock)))


lambda_handler = handler
