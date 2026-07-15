# Lambda 3: 분석 결과 DynamoDB 저장 (Bedrock Action Group)
# 역할: Bedrock Agent가 분석한 결과(위험도/고장유형/권고/부품)를 DynamoDB에 저장
# 리전: us-east-1
#
# 동작:
#   anomaly_filter가 먼저 원본 센서 데이터를 저장(status=PENDING)해 둔다.
#   이 Lambda는 해당 facility_id의 "최신 레코드"를 찾아 분석 결과로 갱신(update)한다.
#   → 원본 센서값은 anomaly_filter가 정확히 저장하고, 분석 결과만 여기서 덮어씀.
#   → Agent는 facility_id만 정확히 넘기면 되고, 센서값을 relay할 필요가 없다.
#
# 매칭되는 PENDING 레코드가 없으면(예: 단독 테스트) 새 레코드를 생성한다(fallback).
#
# 입력: Bedrock Action Group 형식 / 일반 JSON 형식 모두 지원.
# 파라미터(6개): facility_id, risk_level, status, failure_type, recommendation, required_part

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


def save_detection(data: dict) -> dict:
    """
    Agent 분석 결과를 저장한다.
    - anomaly_filter가 남긴 최신 레코드가 있으면 → 그 레코드를 update
    - 없으면 → 새 레코드 생성 (fallback, 단독 테스트 대비)
    """
    facility_id = data.get('facility_id')
    if not facility_id:
        raise ValueError('facility_id는 필수 입력값입니다')

    risk_level     = data.get('risk_level', 0)
    failure_type   = data.get('failure_type', '')
    recommendation = data.get('recommendation', '')
    required_part  = data.get('required_part', '')
    status         = data.get('status') or determine_status(risk_level)

    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)

    latest_ts = _find_latest_timestamp(table, facility_id)

    if latest_ts:
        # 기존(원본) 레코드에 분석 결과만 덮어쓰기
        table.update_item(
            Key={'facility_id': facility_id, 'timestamp': latest_ts},
            UpdateExpression=(
                'SET #st = :status, risk_level = :risk, '
                'failure_type = :ft, recommendation = :rec, required_part = :part'
            ),
            ExpressionAttributeNames={'#st': 'status'},
            ExpressionAttributeValues={
                ':status': status,
                ':risk':   Decimal(str(risk_level)),
                ':ft':     failure_type,
                ':rec':    recommendation,
                ':part':   required_part
            }
        )
        return {'facility_id': facility_id, 'timestamp': latest_ts,
                'status': status, 'mode': 'updated'}

    # fallback: 원본 레코드가 없으면 새로 생성 (센서값은 비어있음)
    timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')
    sensor_values    = data.get('sensor_values', {})
    abnormal_sensors = data.get('abnormal_sensors', [])
    if not isinstance(sensor_values, str):
        sensor_values = json.dumps(sensor_values, ensure_ascii=False)
    if not isinstance(abnormal_sensors, str):
        abnormal_sensors = json.dumps(abnormal_sensors, ensure_ascii=False)

    table.put_item(Item={
        'facility_id':      facility_id,
        'timestamp':        timestamp,
        'status':           status,
        'sensor_values':    sensor_values,
        'abnormal_sensors': abnormal_sensors,
        'risk_level':       Decimal(str(risk_level)),
        'failure_type':     failure_type,
        'recommendation':   recommendation,
        'required_part':    required_part
    })
    return {'facility_id': facility_id, 'timestamp': timestamp,
            'status': status, 'mode': 'created'}


def lambda_handler(event, context):
    """
    1) Bedrock Action Group 호출 → Bedrock 형식 응답
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
        return {'statusCode': 200, 'message': '저장 완료', **result}
    except ValueError as e:
        return {'statusCode': 400, 'error': str(e)}
    except Exception as e:
        return {'statusCode': 500, 'error': str(e), 'message': 'DynamoDB 저장 실패'}
