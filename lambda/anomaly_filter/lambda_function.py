# Lambda 2: 센서 이상 전처리 + Bedrock Agent 호출
# 리전: us-east-1
#
# 역할:
#   1. 센서값을 정상 범위와 비교하여 벗어난 센서(abnormal_sensors)를 추출 (힌트 생성)
#   2. 설비 5대 전부에 대해 Bedrock Agent를 호출 (정상/이상 무관)
#      - 범위 벗어난 설비: abnormal_sensors 힌트를 함께 전달
#      - 범위 안 벗어난 설비: 빈 배열 전달 (Agent가 다른 요인으로 이상 여부 재분석)
#
# 이후 처리는 Agent가 담당:
#   - Knowledge Base(RAG) 검색
#   - Claude 추론 (위험도/고장유형/권고/부품)
#   - Action Group 호출: dynamo_save(저장), inventory_check(재고), create_order(발주)
#
# 즉 이 Lambda는 Agent 응답을 파싱하거나 저장하지 않는다. Agent를 깨우기만 한다.
#
# [Mock 모드] MOCK_MODE=true 시 Agent 없이 호출을 건너뛰고 전처리 결과만 반환 (테스트용)

import boto3
import json
import os

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
    센서값을 정상 범위와 비교하여 벗어난 센서 목록을 반환한다.
    이 결과는 Agent에게 "이 센서들이 범위를 벗어났다"는 힌트로 전달된다.

    반환 형식:
    [
        {"sensor": "torque", "value": 122.0, "normal_range": "12.6~70.0", "unit": "Nm"},
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
                'sensor':       sensor,
                'value':        value,
                'normal_range': f"{spec['min']}~{spec['max']}",
                'unit':         spec['unit']
            })
    return abnormal_sensors


def invoke_bedrock_agent(payload: dict) -> None:
    """
    단일 설비 데이터를 Bedrock Agent에 전달하여 세션을 시작한다.
    Agent가 KB 검색 + 추론 + Action Group(dynamo_save/inventory_check/create_order)을
    스스로 수행하므로, 이 함수는 Agent를 깨우기만 하고 응답은 파싱하지 않는다.
    """
    client = boto3.client('bedrock-agent-runtime', region_name=REGION)

    response = client.invoke_agent(
        agentId=AGENT_ID,
        agentAliasId=AGENT_ALIAS_ID,
        sessionId=f"session-{payload['facility_id']}",
        inputText=json.dumps(payload, ensure_ascii=False),
        endSession=True
    )

    # 스트리밍 응답을 끝까지 소비해야 Agent 실행이 완료됨 (내용은 사용하지 않음)
    for event in response.get('completion', []):
        _ = event.get('chunk', {})


def lambda_handler(event, context):
    """
    센서 이상 전처리 + Bedrock Agent 호출 Lambda

    입력 (event) — sensor_read 출력 구조:
        {
            "sensor_data": [
                {
                    "facility_id": "L47340",
                    "product_type": "L",
                    "air_temp": 298.1, "process_temp": 308.6,
                    "rotation_speed": 1500, "torque": 122.0, "tool_wear": 180
                },
                ...  (설비 5대)
            ]
        }

    출력:
        {
            "statusCode": 200,
            "processed": [
                {
                    "facility_id": "L47340",
                    "abnormal_count": 2,
                    "agent_invoked": true
                },
                ...
            ]
        }

    실제 분석 결과(위험도/권고 등)는 Agent가 Action Group(dynamo_save)으로
    DynamoDB에 저장하므로, 이 Lambda의 반환값에는 포함되지 않는다.
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

        processed = []
        errors    = []

        for sensor_data in sensor_data_list:
            facility_id = sensor_data.get('facility_id', 'UNKNOWN')

            try:
                # 원본 센서값 (facility_id, product_type 제외)
                sensor_values = {
                    k: v for k, v in sensor_data.items()
                    if k not in ('facility_id', 'product_type')
                }

                # 정상 범위 벗어난 센서 추출 (힌트)
                abnormal_sensors = extract_abnormal_sensors(sensor_data)

                # Agent에 전달할 페이로드
                payload = {
                    'facility_id':      facility_id,
                    'product_type':     sensor_data.get('product_type', ''),
                    'sensor_values':    sensor_values,
                    'abnormal_sensors': abnormal_sensors,
                    'abnormal_count':   len(abnormal_sensors)
                }

                # 정상/이상 무관하게 5대 전부 Agent 호출 (Mock 모드면 건너뜀)
                agent_invoked = False
                if not MOCK_MODE:
                    invoke_bedrock_agent(payload)
                    agent_invoked = True

                processed.append({
                    'facility_id':    facility_id,
                    'abnormal_count': len(abnormal_sensors),
                    'agent_invoked':  agent_invoked
                })

            except Exception as e:
                # 개별 설비 실패 시 나머지 설비 처리는 계속
                errors.append({'facility_id': facility_id, 'error': str(e)})

        return {
            'statusCode': 200,
            'processed':  processed,
            'errors':     errors
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'error':      str(e),
            'message':    '센서 전처리 및 Bedrock Agent 호출 실패'
        }
