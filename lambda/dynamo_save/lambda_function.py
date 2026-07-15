# Lambda 3: 탐지 결과 DynamoDB 저장 (Bedrock Action Group)
# 역할: Bedrock Agent가 분석한 결과(위험도/고장유형/권고/부품)를 DynamoDB에 저장
# 리전: us-east-1
#
# 이 Lambda는 Bedrock Agent의 Action Group으로 등록되어 Agent가 호출한다.
# Bedrock은 파라미터를 특수한 형식으로 넘기고, 특수한 형식의 응답을 기대하므로
# 아래 래퍼(_parse_bedrock_event / _bedrock_response)로 형식을 변환한다.
#
# 직접 테스트(콘솔 Test, 일반 JSON)도 가능하도록 두 형식을 모두 처리한다.

import boto3
import json
from datetime import datetime
from decimal import Decimal

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
    """Bedrock Agent가 호출한 이벤트인지 판별."""
    return isinstance(event, dict) and 'actionGroup' in event and (
        'parameters' in event or 'function' in event or 'apiPath' in event
    )


def _coerce(value: str):
    """Bedrock 파라미터 값(문자열)을 적절한 타입으로 변환.

    - JSON 객체/배열 문자열 → dict/list
    - 숫자 문자열 → int/float
    - 그 외 → 원본 문자열
    """
    if not isinstance(value, str):
        return value
    s = value.strip()
    # JSON 객체/배열 시도 (sensor_values, abnormal_sensors 대응)
    if s.startswith('{') or s.startswith('['):
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            return value
    # 숫자 시도
    try:
        if '.' in s:
            return float(s)
        return int(s)
    except ValueError:
        return value


def _parse_bedrock_event(event: dict) -> dict:
    """Bedrock Action Group 이벤트에서 parameters를 평범한 dict로 추출."""
    params = {}
    for p in event.get('parameters', []):
        name = p.get('name')
        if name:
            params[name] = _coerce(p.get('value'))

    # 일부 Agent 설정은 requestBody(OpenAPI 스타일)로 넘기기도 함
    request_body = event.get('requestBody', {})
    content = request_body.get('content', {})
    for _media, spec in content.items():
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
                'responseBody': {
                    'TEXT': {'body': body_text}
                }
            }
        }
    }


# ─────────────────────────────────────────────────────────────────────
# 핵심 저장 로직
# ─────────────────────────────────────────────────────────────────────
def save_detection(data: dict) -> dict:
    """분석 결과를 detection-results 테이블에 저장하고 요약을 반환."""
    facility_id      = data.get('facility_id')
    if not facility_id:
        raise ValueError('facility_id는 필수 입력값입니다')

    sensor_values    = data.get('sensor_values', {})
    abnormal_sensors = data.get('abnormal_sensors', [])
    risk_level       = data.get('risk_level', 0)
    failure_type     = data.get('failure_type', '')
    recommendation   = data.get('recommendation', '')
    required_part    = data.get('required_part', '')
    status           = data.get('status') or determine_status(risk_level)

    timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')

    # sensor_values / abnormal_sensors가 문자열로 넘어온 경우 그대로, dict면 직렬화
    if not isinstance(sensor_values, str):
        sensor_values = json.dumps(sensor_values, ensure_ascii=False)
    if not isinstance(abnormal_sensors, str):
        abnormal_sensors = json.dumps(abnormal_sensors, ensure_ascii=False)

    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)

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

    return {'facility_id': facility_id, 'timestamp': timestamp, 'status': status}


def lambda_handler(event, context):
    """
    두 가지 호출 방식을 모두 지원:

    1) Bedrock Action Group 호출 (실제 운영)
       event = {
         "actionGroup": "save-result",
         "function": "dynamo_save",
         "parameters": [
           {"name": "facility_id", "value": "L47340"},
           {"name": "risk_level", "value": "82"},
           {"name": "sensor_values", "value": "{...}"},
           ...
         ]
       }
       → Bedrock 형식으로 응답

    2) 일반 JSON 호출 (콘솔 Test / 직접 invoke)
       event = { "facility_id": "L47340", "risk_level": 82, ... }
       → 일반 형식으로 응답
    """
    # ── Bedrock Action Group 호출 ────────────────────────────────
    if _is_bedrock_event(event):
        try:
            data = _parse_bedrock_event(event)
            result = save_detection(data)
            body = (f"저장 완료 — 설비 {result['facility_id']}, "
                    f"상태 {result['status']}, 시각 {result['timestamp']}")
            return _bedrock_response(event, body)
        except Exception as e:
            return _bedrock_response(event, f"저장 실패: {str(e)}")

    # ── 일반 JSON 호출 (테스트용) ────────────────────────────────
    try:
        result = save_detection(event)
        return {
            'statusCode': 200,
            'message': '저장 완료',
            **result
        }
    except ValueError as e:
        return {'statusCode': 400, 'error': str(e)}
    except Exception as e:
        return {'statusCode': 500, 'error': str(e), 'message': 'DynamoDB 저장 실패'}
