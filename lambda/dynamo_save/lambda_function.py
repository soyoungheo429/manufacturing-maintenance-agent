# db_save Lambda (Bedrock Action Group) — 구 이름: dynamo_save
# 역할: Bedrock Agent가 분석한 결과를 DynamoDB(detection-results)에 저장
# 리전: us-east-1
#
# 스펙 변경 배경:
#   Agentic 아키텍처 전환에 따라 Action Group 입력 스펙이 아래처럼 재정의됨.
#     equipment_id, timestamp, sensor_data, is_anomaly, reasoning,
#     actions_taken, recommended_action  →  save_status
#
#   다만 dashboard_data(프론트 연동, 다른 담당자 파트)가 기존 필드명
#   (facility_id/status/risk_level/failure_type/sensor_values/
#   recommendation/required_part)에 강하게 의존하고 있어, 필드명을 완전히
#   갈아엎으면 대시보드가 깨진다. 그래서 이 Lambda는 새 스펙의 파라미터를
#   받아 기존 DynamoDB 스키마로 매핑하여 저장한다 (하위 호환 유지).
#
#   새 파라미터 ↔ 기존 컬럼 매핑:
#     equipment_id       → facility_id (PK)
#     timestamp           → timestamp (SK, 없으면 저장 시각으로 자동 생성)
#     sensor_data          → sensor_values (JSON 문자열로 저장)
#     is_anomaly           → status ('DANGER'/'NORMAL', risk_level 있으면 그걸로 재계산)
#     reasoning            → recommendation에 병합 (recommended_action과 함께)
#     actions_taken        → actions_taken 컬럼 신규 추가 (기존 스키마에 없던 필드)
#     recommended_action   → recommendation (기존 필드명 유지, dashboard_data가 이 필드를 읽음)
#
#   구 파라미터(facility_id/risk_level/status/failure_type/recommendation/
#   required_part)도 그대로 지원한다 — 다른 Action Group이나 기존 테스트가
#   구 파라미터로 호출해도 정상 동작한다.
#
# 입력: Bedrock Action Group 형식 / 일반 JSON 형식 모두 지원.

import boto3
import json
from datetime import datetime
from decimal import Decimal
from boto3.dynamodb.conditions import Key

TABLE_NAME = 'detection-results'
REGION = 'us-east-1'


def determine_status(risk_level) -> str:
    """위험도(0~100) 기준 상태 결정."""
    if risk_level >= 70:
        return 'DANGER'
    elif risk_level >= 30:
        return 'WARNING'
    else:
        return 'NORMAL'


# ─────────────────────────────────────────────────────────────────────
# Bedrock Action Group 입출력 래퍼
# ─────────────────────────────────────────────────────────────────────
def _is_bedrock_event(event: dict) -> bool:
    return isinstance(event, dict) and 'actionGroup' in event and (
        'parameters' in event or 'function' in event or 'apiPath' in event
    )


def _coerce(value):
    """Bedrock 파라미터 값(문자열)을 적절한 타입으로 변환."""
    if not isinstance(value, str):
        return value
    s = value.strip()
    if s.startswith('{') or s.startswith('['):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return value
    if s.lower() in ('true', 'false'):
        return s.lower() == 'true'
    try:
        return float(s) if '.' in s else int(s)
    except ValueError:
        return value


def _parse_bedrock_event(event: dict) -> dict:
    """Bedrock Action Group 이벤트에서 parameters를 dict로 추출."""
    params = {}
    for p in event.get('parameters', []):
        name = p.get('name')
        if name:
            params[name] = _coerce(p.get('value'))

    request_body = event.get('requestBody', {})
    for _media, spec in request_body.get('content', {}).items():
        for p in spec.get('properties', []):
            name = p.get('name')
            if name:
                params[name] = _coerce(p.get('value'))

    return params


def _bedrock_response(event: dict, body_text: str) -> dict:
    """Bedrock Agent가 기대하는 응답 형식으로 래핑."""
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': event.get('actionGroup', ''),
            'function':    event.get('function', ''),
            'functionResponse': {
                'responseBody': {'TEXT': {'body': body_text}}
            }
        }
    }


# ─────────────────────────────────────────────────────────────────────
# 새 스펙 → 기존 스키마 매핑
# ─────────────────────────────────────────────────────────────────────
def _normalize_input(data: dict) -> dict:
    """
    새 스펙(equipment_id/sensor_data/is_anomaly/reasoning/actions_taken/
    recommended_action)과 구 스펙(facility_id/risk_level/status/
    failure_type/recommendation/required_part)을 모두 받아
    하나의 내부 표현으로 정규화한다. 새 스펙 필드가 있으면 우선한다.

    Action Group 파라미터 5개 제한(Bedrock 하드 리밋) 때문에, 분석 결과
    4개 필드(risk_level/failure_type/recommendation/required_part)를
    'analysis'라는 JSON 문자열 파라미터 하나로 묶어서 받을 수도 있다.
    _coerce()가 이미 JSON 문자열을 dict로 변환해두므로, 여기서는 그
    dict를 최상위 data에 병합해서 이후 로직을 그대로 재사용한다.
    analysis와 최상위 필드가 동시에 있으면 최상위 필드가 우선한다.
    """
    analysis = data.get('analysis')
    if isinstance(analysis, dict):
        data = {**analysis, **data}

    facility_id = data.get('equipment_id') or data.get('facility_id')

    # sensor_data(신규) 우선, 없으면 sensor_values(구) 사용
    sensor_values = data.get('sensor_data')
    if sensor_values is None:
        sensor_values = data.get('sensor_values', {})

    # is_anomaly(신규, bool) → status. status(구)가 명시되면 그게 우선.
    status = data.get('status')
    is_anomaly = data.get('is_anomaly')
    risk_level = data.get('risk_level', 0)
    if status is None and is_anomaly is not None:
        status = 'DANGER' if is_anomaly else 'NORMAL'
    if status is None:
        status = determine_status(risk_level)

    # recommended_action(신규) 우선, 없으면 recommendation(구) 사용.
    # reasoning(신규)이 있으면 뒤에 이어붙여 근거를 함께 저장한다.
    recommendation = data.get('recommended_action') or data.get('recommendation', '')
    reasoning = data.get('reasoning')
    if reasoning:
        recommendation = f"{recommendation} (근거: {reasoning})".strip()

    return {
        'facility_id':      facility_id,
        'timestamp':        data.get('timestamp'),
        'sensor_values':     sensor_values,
        'abnormal_sensors':  data.get('abnormal_sensors', []),
        'status':            status,
        'risk_level':        risk_level,
        'failure_type':      data.get('failure_type', ''),
        'recommendation':    recommendation,
        'required_part':     data.get('required_part', ''),
        'actions_taken':     data.get('actions_taken', '')
    }


# ─────────────────────────────────────────────────────────────────────
# 핵심 저장 로직
# ─────────────────────────────────────────────────────────────────────
def _find_latest_timestamp(table, facility_id: str):
    """해당 facility_id의 가장 최근 레코드 timestamp를 반환 (없으면 None)."""
    resp = table.query(
        KeyConditionExpression=Key('facility_id').eq(facility_id),
        ScanIndexForward=False,   # 내림차순 (최신순)
        Limit=1
    )
    items = resp.get('Items', [])
    return items[0]['timestamp'] if items else None


def save_detection(raw_data: dict) -> dict:
    """
    Agent 분석 결과를 저장한다. 새/구 파라미터 스펙을 모두 지원한다(_normalize_input).
    - 기존 최신 레코드가 있으면 → 그 레코드를 update
    - 없으면 → 새 레코드 생성 (fallback, 단독 테스트 대비)
    """
    data = _normalize_input(raw_data)
    facility_id = data['facility_id']
    if not facility_id:
        raise ValueError('equipment_id(또는 facility_id)는 필수 입력값입니다')

    status         = data['status']
    risk_level      = data['risk_level']
    failure_type    = data['failure_type']
    recommendation  = data['recommendation']
    required_part   = data['required_part']
    actions_taken   = data['actions_taken']

    # sensor_values/abnormal_sensors는 DynamoDB에 문자열(JSON)로 저장한다.
    sensor_values    = data['sensor_values']
    abnormal_sensors = data['abnormal_sensors']
    if not isinstance(sensor_values, str):
        sensor_values = json.dumps(sensor_values, ensure_ascii=False)
    if not isinstance(abnormal_sensors, str):
        abnormal_sensors = json.dumps(abnormal_sensors, ensure_ascii=False)

    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)

    # timestamp가 명시적으로 넘어오면 그 레코드를 직접 지정, 아니면 최신 레코드 탐색
    latest_ts = data['timestamp'] or _find_latest_timestamp(table, facility_id)

    if latest_ts:
        # sensor_values가 '{}'(빈 값)이면 기존에 저장된 값을 덮어쓰지 않는다.
        # (Agent가 sensor_values를 안 보낸 호출이 기존 실측 데이터를 지우는 것을 방지)
        update_expr = (
            'SET #st = :status, risk_level = :risk, '
            'failure_type = :ft, recommendation = :rec, '
            'required_part = :part, actions_taken = :act'
        )
        expr_values = {
            ':status': status,
            ':risk':   Decimal(str(risk_level)),
            ':ft':     failure_type,
            ':rec':    recommendation,
            ':part':   required_part,
            ':act':    actions_taken
        }
        if sensor_values and sensor_values != '{}':
            update_expr += ', sensor_values = :sv, abnormal_sensors = :abn'
            expr_values[':sv']  = sensor_values
            expr_values[':abn'] = abnormal_sensors

        table.update_item(
            Key={'facility_id': facility_id, 'timestamp': latest_ts},
            UpdateExpression=update_expr,
            ExpressionAttributeNames={'#st': 'status'},
            ExpressionAttributeValues=expr_values
        )
        return {'facility_id': facility_id, 'timestamp': latest_ts,
                'status': status, 'mode': 'updated'}

    # fallback: 매칭 레코드가 없으면 새로 생성 (sensor_values/abnormal_sensors는 위에서 이미 문자열로 변환됨)
    timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')

    table.put_item(Item={
        'facility_id':      facility_id,
        'timestamp':        timestamp,
        'status':           status,
        'sensor_values':    sensor_values,
        'abnormal_sensors': abnormal_sensors,
        'risk_level':       Decimal(str(risk_level)),
        'failure_type':     failure_type,
        'recommendation':   recommendation,
        'required_part':    required_part,
        'actions_taken':    actions_taken
    })
    return {'facility_id': facility_id, 'timestamp': timestamp,
            'status': status, 'mode': 'created'}


def lambda_handler(event, context):
    """
    1) Bedrock Action Group 호출 → Bedrock 형식 응답 (save_status 포함)
    2) 일반 JSON 호출 (콘솔 Test) → 일반 형식 응답
    """
    if _is_bedrock_event(event):
        try:
            data = _parse_bedrock_event(event)
            result = save_detection(data)
            body = (f"저장 완료 — 설비 {result['facility_id']}, "
                    f"상태 {result['status']} ({result['mode']})")
            return _bedrock_response(event, body)
        except Exception as e:
            return _bedrock_response(event, f"저장 실패: {str(e)}")

    try:
        result = save_detection(event)
        return {'statusCode': 200, 'save_status': 'success',
                'message': '저장 완료', **result}
    except ValueError as e:
        return {'statusCode': 400, 'save_status': 'failed', 'error': str(e)}
    except Exception as e:
        return {'statusCode': 500, 'save_status': 'failed', 'error': str(e),
                'message': 'DynamoDB 저장 실패'}
