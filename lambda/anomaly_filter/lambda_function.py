# Lambda 2: 센서 이상 전처리 + Bedrock Agent 호출
# 역할: 정상 범위를 벗어난 센서를 추출하고, 설비별로 Bedrock Agent를 호출하여 분석 결과 반환
# 리전: us-east-1
#
# [Mock 모드]
# 환경변수 MOCK_MODE=true 설정 시 Bedrock Agent를 실제로 호출하지 않고
# 더미 분석 결과를 반환합니다. Agent 연결 전 파이프라인 테스트용입니다.
# Agent 연결 후에는 MOCK_MODE 환경변수를 삭제하거나 false로 변경하면 됩니다.

import boto3
import json
import os
import random

REGION         = 'us-east-1'
AGENT_ID       = os.environ.get('BEDROCK_AGENT_ID', '')
AGENT_ALIAS_ID = os.environ.get('BEDROCK_AGENT_ALIAS_ID', '')
MOCK_MODE      = os.environ.get('MOCK_MODE', 'false').lower() == 'true'

# 정상 범위 정의 (AI4I 2020 데이터셋 기준)
NORMAL_RANGE = {
    'air_temp':       {'min': 295.3, 'max': 304.5, 'unit': 'K'},
    'process_temp':   {'min': 305.7, 'max': 313.8, 'unit': 'K'},
    'rotation_speed': {'min': 1168,  'max': 2695,  'unit': 'rpm'},
    'torque':         {'min': 12.6,  'max': 70.0,  'unit': 'Nm'},
    'tool_wear':      {'min': 0,     'max': 221,   'unit': 'min'}
}


def extract_abnormal_sensors(sensor_data: dict) -> list:
    """
    단일 설비의 센서값을 정상 범위와 비교하여
    범위를 벗어난 센서 목록을 반환한다.

    반환 형식:
    [
        {
            "sensor": "torque",
            "value": 122.0,
            "normal_range": "12.6~70.0",
            "unit": "Nm"
        },
        ...
    ]
    """
    abnormal_sensors = []

    for sensor, spec in NORMAL_RANGE.items():
        value = sensor_data.get(sensor)
        if value is None:
            continue
        if value < spec['min'] or value > spec['max']:
            abnormal_sensors.append({
                'sensor': sensor,
                'value': value,
                'normal_range': f"{spec['min']}~{spec['max']}",
                'unit': spec['unit']
            })

    return abnormal_sensors


def mock_bedrock_agent(payload: dict) -> dict:
    """
    Bedrock Agent 연결 전 테스트용 Mock 함수.
    abnormal_count에 따라 현실적인 더미 결과를 반환한다.
    """
    facility_id    = payload['facility_id']
    abnormal_count = payload['abnormal_count']
    abnormal_sensors = payload.get('abnormal_sensors', [])
    sensor_names   = [s['sensor'] for s in abnormal_sensors]

    if abnormal_count == 0:
        return {
            'facility_id':    facility_id,
            'risk_level':     random.randint(0, 15),
            'status':         'NORMAL',
            'failure_type':   'NORMAL',
            'recommendation': '정상 운전 중입니다. 다음 정기보전일을 준수하세요.',
            'required_part':  '',
            'reasoning':      '모든 센서값이 정상 범위 내에 있습니다. (Mock 응답)'
        }

    # 이상 센서 조합으로 고장 유형 추정
    if 'tool_wear' in sensor_names and 'torque' in sensor_names:
        failure_type = 'OSF'
        risk_level   = random.randint(70, 90)
        rec          = '즉시 가동 중단 후 절삭공구 교체 필요. 토크와 공구 마모가 동시에 임계값을 초과했습니다.'
        part         = '절삭공구 인서트'
    elif 'tool_wear' in sensor_names:
        failure_type = 'TWF'
        risk_level   = random.randint(55, 75)
        rec          = '공구 마모가 한계치에 근접했습니다. 다음 교대 전 절삭공구 교체를 권장합니다.'
        part         = '절삭공구 인서트'
    elif 'air_temp' in sensor_names or 'process_temp' in sensor_names:
        failure_type = 'HDF'
        risk_level   = random.randint(50, 70)
        rec          = '냉각 시스템 점검이 필요합니다. 냉각팬 및 방열판 상태를 확인하세요.'
        part         = '냉각팬'
    elif 'torque' in sensor_names or 'rotation_speed' in sensor_names:
        failure_type = 'PWF'
        risk_level   = random.randint(40, 65)
        rec          = '전력 계통 점검이 필요합니다. 구동 모터 및 전력 드라이버 상태를 확인하세요.'
        part         = '전력 드라이버'
    else:
        failure_type = 'RNF'
        risk_level   = random.randint(30, 50)
        rec          = '명확한 패턴 없는 이상이 감지되었습니다. 전반적인 설비 점검을 권장합니다.'
        part         = ''

    status = 'DANGER' if risk_level >= 70 else 'WARNING'

    return {
        'facility_id':    facility_id,
        'risk_level':     risk_level,
        'status':         status,
        'failure_type':   failure_type,
        'recommendation': rec,
        'required_part':  part,
        'reasoning':      f'이상 센서 {sensor_names} 감지. {failure_type} 패턴으로 판단. (Mock 응답)'
    }


def invoke_bedrock_agent(payload: dict) -> dict:
    """
    단일 설비 데이터를 Bedrock Agent에 전달하고 분석 결과를 반환한다.

    payload 구조:
    {
        "facility_id": "L47340",
        "product_type": "L",
        "sensor_values": { ... },
        "abnormal_sensors": [ ... ],
        "abnormal_count": 1
    }
    """
    client = boto3.client('bedrock-agent-runtime', region_name=REGION)

    input_text = json.dumps(payload, ensure_ascii=False)
    session_id = f"session-{payload['facility_id']}"

    response = client.invoke_agent(
        agentId=AGENT_ID,
        agentAliasId=AGENT_ALIAS_ID,
        sessionId=session_id,
        inputText=input_text,
        endSession=True
    )

    # 스트리밍 응답 수집
    raw_output = ''
    for event in response.get('completion', []):
        chunk = event.get('chunk', {})
        if 'bytes' in chunk:
            raw_output += chunk['bytes'].decode('utf-8')

    return parse_agent_response(raw_output, payload['facility_id'])


def parse_agent_response(raw: str, facility_id: str) -> dict:
    """
    Agent 응답 문자열에서 JSON을 추출한다.
    순수 JSON이 아닌 경우(앞뒤 텍스트 포함)에도 처리한다.
    """
    raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    start = raw.find('{')
    end   = raw.rfind('}')
    if start != -1 and end != -1:
        try:
            return json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            pass

    # 파싱 실패 시 에러 구조 반환 (파이프라인 중단 방지)
    return {
        'facility_id':    facility_id,
        'risk_level':     0,
        'status':         'UNKNOWN',
        'failure_type':   'UNKNOWN',
        'recommendation': 'Bedrock Agent 응답 파싱 실패 — 수동 점검 필요',
        'required_part':  '',
        'reasoning':      f'Raw response: {raw[:300]}'
    }


def lambda_handler(event, context):
    """
    센서 이상 전처리 + Bedrock Agent 호출 Lambda

    입력 (event) — Lambda1 출력 구조:
        sensor_data: list[dict]
        [
            {
                "facility_id": "L47340",
                "product_type": "L",
                "air_temp": 298.1,
                "process_temp": 308.6,
                "rotation_speed": 1500,
                "torque": 122.0,
                "tool_wear": 180
            },
            ...
        ]

    출력:
        analyses: list[dict]  — 설비별 Bedrock Agent 분석 결과
        [
            {
                "facility_id": "L47340",
                "risk_level": 75,
                "status": "DANGER",
                "failure_type": "TWF",
                "recommendation": "...",
                "required_part": "...",
                "reasoning": "...",
                "sensor_values": { ... },
                "abnormal_sensors": [ ... ]
            },
            ...
        ]
    """
    if not MOCK_MODE and (not AGENT_ID or not AGENT_ALIAS_ID):
        return {
            'statusCode': 500,
            'error': 'BEDROCK_AGENT_ID 또는 BEDROCK_AGENT_ALIAS_ID 환경변수가 설정되지 않았습니다'
        }

    try:
        sensor_data_list = event.get('sensor_data', [])

        if not sensor_data_list:
            return {
                'statusCode': 400,
                'error': 'sensor_data 필드가 없거나 비어있습니다'
            }

        analyses = []
        errors   = []

        for sensor_data in sensor_data_list:
            facility_id = sensor_data.get('facility_id', 'UNKNOWN')

            try:
                # 원본 센서값 보존 (facility_id, product_type 제외)
                sensor_values = {
                    k: v for k, v in sensor_data.items()
                    if k not in ('facility_id', 'product_type')
                }

                # 정상 범위 벗어난 센서 추출
                abnormal_sensors = extract_abnormal_sensors(sensor_data)

                # Bedrock Agent 호출 페이로드 구성
                payload = {
                    'facility_id':     facility_id,
                    'product_type':    sensor_data.get('product_type', ''),
                    'sensor_values':   sensor_values,
                    'abnormal_sensors': abnormal_sensors,
                    'abnormal_count':  len(abnormal_sensors)
                }

                # Bedrock Agent 호출 (Mock 모드면 더미 결과 반환)
                if MOCK_MODE:
                    analysis = mock_bedrock_agent(payload)
                else:
                    analysis = invoke_bedrock_agent(payload)

                # dynamo_save에서 필요한 필드 병합
                analysis['sensor_values']    = sensor_values
                analysis['abnormal_sensors'] = abnormal_sensors

                analyses.append(analysis)

            except Exception as e:
                # 개별 설비 실패 시 파이프라인 전체 중단 방지
                errors.append({'facility_id': facility_id, 'error': str(e)})
                analyses.append({
                    'facility_id':    facility_id,
                    'risk_level':     0,
                    'status':         'UNKNOWN',
                    'failure_type':   'UNKNOWN',
                    'recommendation': f'분석 중 오류 발생: {str(e)}',
                    'required_part':  '',
                    'reasoning':      'Lambda 처리 오류',
                    'sensor_values':  sensor_data,
                    'abnormal_sensors': []
                })

        return {
            'statusCode': 200,
            'analyses':   analyses,
            'errors':     errors
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'error':      str(e),
            'message':    '센서 전처리 및 Bedrock Agent 호출 실패'
        }
