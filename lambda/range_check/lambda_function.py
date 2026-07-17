# range_check Lambda (Bedrock Agent Action Group)
# 리전: us-east-1
#
# 역할: 설비 센서 하나의 값을 정상 범위(min~max)와 비교하여 이상 여부를 판단한다.
#   기존 anomaly_filter처럼 5개 센서를 한 번에 훑어서 "힌트"를 만들어 Agent에게
#   먼저 알려주는 방식이 아니라, Agent가 "이 센서가 정상인지 확인해야겠다"고
#   스스로 판단했을 때 호출하는 도구(Action Group)이다.
#
#   정상 범위 데이터는 DynamoDB(sensor-normal-range 테이블)에서 조회한다.
#   (AI4I 2020 데이터셋 기준값으로 시드됨 — infra/seed_normal_range.py 참고)
#
# 입력 (Bedrock Action Group parameters):
#   equipment_id  (string) — 설비 ID. 범위 조회 자체에는 쓰이지 않지만
#                             응답에 그대로 포함되어 Agent가 여러 설비를
#                             다룰 때 결과를 혼동하지 않도록 돕는다.
#                             (추후 설비별로 다른 정상범위를 두고 싶을 때
#                             _get_normal_range 조회 키로 확장 가능)
#   sensor_type   (string) — 센서 종류 (air_temp / process_temp / rotation_speed /
#                             torque / tool_wear)
#   sensor_value  (number) — 측정값
#
# 출력:
#   equipment_id    (string, 선택) — 입력받은 equipment_id 그대로 (있을 때만 포함)
#   is_anomaly      (bool)  — 정상 범위를 벗어났는지 여부
#   normal_min      (float) — 정상 범위 하한
#   normal_max      (float) — 정상 범위 상한
#   deviation_rate  (float) — 정상 범위를 벗어난 정도(%). 범위 안이면 0.
#                             하한 미달: (min-value)/min*100, 상한 초과: (value-max)/max*100

import boto3
import json
from decimal import Decimal

REGION     = 'us-east-1'
TABLE_NAME = 'sensor-normal-range'

# DynamoDB 조회 실패 시(테이블 미존재 등) 사용할 기본값 — AI4I 2020 데이터셋 기준
FALLBACK_RANGE = {
    'air_temp':       {'min': 295.3, 'max': 304.5, 'unit': 'K'},
    'process_temp':   {'min': 305.7, 'max': 313.8, 'unit': 'K'},
    'rotation_speed': {'min': 1168,  'max': 2695,  'unit': 'rpm'},
    'torque':         {'min': 12.6,  'max': 70.0,  'unit': 'Nm'},
    'tool_wear':      {'min': 0,     'max': 221,   'unit': 'min'}
}


# ─────────────────────────────────────────────────────────────────────
# Bedrock Action Group 입출력 래퍼 (dynamo_save/db_save와 동일 패턴)
# ─────────────────────────────────────────────────────────────────────
def _is_bedrock_event(event: dict) -> bool:
    return isinstance(event, dict) and 'actionGroup' in event and (
        'parameters' in event or 'function' in event or 'apiPath' in event
    )


def _coerce(value):
    """
    Bedrock 파라미터 값(문자열)을 적절한 타입으로 변환.
    정수 표기("221")는 int로, 소수/지수 표기("70.0", "1e10", "1E-5")는
    float로 변환한다. '.' 유무로만 판별하면 지수 표기("1e10")를 놓치므로
    먼저 int 변환을 시도하고, 실패하면 float 변환을 시도한다.
    """
    if not isinstance(value, str):
        return value
    s = value.strip()
    try:
        return int(s)
    except ValueError:
        pass
    try:
        return float(s)
    except ValueError:
        return value


def _parse_bedrock_event(event: dict) -> dict:
    params = {}
    for p in event.get('parameters', []):
        name = p.get('name')
        if name:
            params[name] = _coerce(p.get('value'))
    return params


def _bedrock_response(event: dict, body_dict: dict) -> dict:
    """Bedrock Agent가 기대하는 응답 형식으로 래핑. body는 JSON 문자열로 전달."""
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': event.get('actionGroup', ''),
            'function':    event.get('function', ''),
            'functionResponse': {
                'responseBody': {
                    'TEXT': {'body': json.dumps(body_dict, ensure_ascii=False)}
                }
            }
        }
    }


# ─────────────────────────────────────────────────────────────────────
# 핵심 로직
# ─────────────────────────────────────────────────────────────────────
def _get_normal_range(sensor_type: str) -> dict:
    """
    DynamoDB(sensor-normal-range)에서 센서 종류별 정상 범위를 조회한다.
    테이블이 없거나 항목이 없으면 FALLBACK_RANGE를 사용한다.
    """
    try:
        dynamodb = boto3.resource('dynamodb', region_name=REGION)
        table = dynamodb.Table(TABLE_NAME)
        resp = table.get_item(Key={'sensor_type': sensor_type})
        item = resp.get('Item')
        if item:
            return {
                'min':  float(item['min']),
                'max':  float(item['max']),
                'unit': item.get('unit', '')
            }
    except Exception:
        pass  # 테이블 미존재/조회 실패 시 fallback으로 진행

    return FALLBACK_RANGE.get(sensor_type, {'min': 0, 'max': 0, 'unit': ''})


def check_range(sensor_type: str, sensor_value: float, equipment_id: str = None) -> dict:
    """
    센서 하나의 값을 정상 범위와 비교하여 이상 여부와 이탈률을 계산한다.

    equipment_id는 현재 조회 로직(범위 산정)에는 쓰이지 않지만, 응답에
    그대로 포함시켜 Agent가 여러 설비를 동시에 다룰 때 "이 결과가 어느
    설비 건인지" 혼동 없이 추적할 수 있게 한다. 추후 설비별로 다른
    정상범위를 두게 되면 _get_normal_range 조회에도 활용할 수 있다.
    """
    spec = _get_normal_range(sensor_type)
    normal_min = spec['min']
    normal_max = spec['max']

    if sensor_value < normal_min:
        is_anomaly = True
        deviation_rate = round((normal_min - sensor_value) / normal_min * 100, 2) if normal_min else 0.0
    elif sensor_value > normal_max:
        is_anomaly = True
        deviation_rate = round((sensor_value - normal_max) / normal_max * 100, 2) if normal_max else 0.0
    else:
        is_anomaly = False
        deviation_rate = 0.0

    result = {
        'is_anomaly':     is_anomaly,
        'normal_min':     normal_min,
        'normal_max':     normal_max,
        'deviation_rate': deviation_rate
    }
    if equipment_id:
        result['equipment_id'] = equipment_id
    return result


def lambda_handler(event, context):
    """
    Bedrock Agent Action Group: range_check

    입력 (Bedrock Action Group 형식 또는 일반 JSON 둘 다 지원):
        equipment_id  (string, 선택) — 응답에 그대로 포함되어 결과 추적용으로 쓰임
        sensor_type   (string, 필수)
        sensor_value  (number, 필수)

    출력:
        { "equipment_id": str(선택), "is_anomaly": bool, "normal_min": float,
          "normal_max": float, "deviation_rate": float }
    """
    if _is_bedrock_event(event):
        params = _parse_bedrock_event(event)
    else:
        params = event

    try:
        equipment_id = params.get('equipment_id')
        sensor_type  = params.get('sensor_type')
        sensor_value = params.get('sensor_value')

        if sensor_type is None or sensor_value is None:
            error_body = {'error': 'sensor_type과 sensor_value는 필수 입력값입니다'}
            if _is_bedrock_event(event):
                return _bedrock_response(event, error_body)
            return {'statusCode': 400, **error_body}

        result = check_range(sensor_type, float(sensor_value), equipment_id)

        if _is_bedrock_event(event):
            return _bedrock_response(event, result)
        return {'statusCode': 200, **result}

    except Exception as e:
        error_body = {'error': str(e)}
        if _is_bedrock_event(event):
            return _bedrock_response(event, error_body)
        return {'statusCode': 500, **error_body}
