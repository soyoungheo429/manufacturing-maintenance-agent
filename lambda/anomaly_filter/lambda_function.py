# Lambda 2: 센서 이상 전처리 + 원본 저장 + Bedrock Agent 호출
# 리전: us-east-1
#
# 역할:
#   1. 센서값을 정상 범위와 비교하여 벗어난 센서(abnormal_sensors)를 추출 (힌트 생성)
#   2. 원본 센서 데이터를 DynamoDB(detection-results)에 먼저 저장 (status=PENDING)
#      → 센서값 같은 정밀 숫자는 LLM을 거치지 않고 여기서 직접 저장 (왜곡 방지)
#   3. 설비 5대 전부에 대해 Bedrock Agent를 호출 (정상/이상 무관)
#
# 이후 Agent가 담당:
#   - Knowledge Base(RAG) 검색
#   - Claude 추론 (위험도/고장유형/권고/부품)
#   - Action Group 호출: dynamo_save(분석결과 update), inventory_check, create_order
#
# dynamo_save는 이 Lambda가 저장해둔 "최신 PENDING 레코드"를 찾아 분석 결과로 갱신한다.
# 따라서 Agent는 facility_id만 정확히 넘기면 되고, 센서값을 relay할 필요가 없다.
#
# [Mock 모드] MOCK_MODE=true 시 Agent 호출을 건너뛴다 (원본 저장은 그대로 수행).

import boto3
import json
import os
from datetime import datetime
from decimal import Decimal

REGION         = 'us-east-1'
AGENT_ID       = os.environ.get('BEDROCK_AGENT_ID', '')
AGENT_ALIAS_ID = os.environ.get('BEDROCK_AGENT_ALIAS_ID', '')
MOCK_MODE      = os.environ.get('MOCK_MODE', 'false').lower() == 'true'
TABLE_NAME     = 'detection-results'

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
    Agent에게 "이 센서들이 범위를 벗어났다"는 힌트로 전달된다.
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


def save_raw_record(facility_id: str, sensor_values: dict,
                    abnormal_sensors: list) -> str:
    """
    원본 센서 데이터를 detection-results에 먼저 저장한다 (분석 전, status=PENDING).
    Agent가 dynamo_save로 이 레코드를 찾아 분석 결과를 채운다.
    반환: 생성한 timestamp (레코드 SK)
    """
    timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')

    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)

    table.put_item(Item={
        'facility_id':      facility_id,
        'timestamp':        timestamp,
        'status':           'PENDING',          # 분석 전 상태
        'sensor_values':    json.dumps(sensor_values, ensure_ascii=False),
        'abnormal_sensors': json.dumps(abnormal_sensors, ensure_ascii=False),
        'risk_level':       Decimal('0'),
        'failure_type':     '',
        'recommendation':   '',
        'required_part':    ''
    })

    return timestamp


def invoke_bedrock_agent(payload: dict) -> None:
    """
    단일 설비 데이터를 Bedrock Agent에 전달하여 세션을 시작한다.
    Agent가 KB 검색 + 추론 + Action Group을 스스로 수행하므로,
    이 함수는 Agent를 깨우기만 하고 응답은 파싱하지 않는다.
    """
    client = boto3.client('bedrock-agent-runtime', region_name=REGION)

    response = client.invoke_agent(
        agentId=AGENT_ID,
        agentAliasId=AGENT_ALIAS_ID,
        sessionId=f"session-{payload['facility_id']}",
        inputText=json.dumps(payload, ensure_ascii=False),
        enableTrace=True   # [임시 디버깅] Agent 추론/도구호출 과정 로그 확인용
    )

    # 스트리밍 응답 소비 + 디버깅 로그
    final_text = ''
    for event in response.get('completion', []):
        if 'chunk' in event:
            final_text += event['chunk'].get('bytes', b'').decode('utf-8', errors='ignore')
        # [임시 디버깅] trace로 Agent가 어떤 도구를 부르려 하는지 확인
        if 'trace' in event:
            print('AGENT_TRACE:', json.dumps(event['trace'], ensure_ascii=False, default=str)[:2000])
    print('AGENT_FINAL_RESPONSE:', final_text[:1000])


def lambda_handler(event, context):
    """
    센서 이상 전처리 + 원본 저장 + Bedrock Agent 호출

    입력 (event) — sensor_read 출력:
        { "sensor_data": [ {facility_id, product_type, air_temp, ...}, ... ] }

    출력:
        {
            "statusCode": 200,
            "processed": [
                {"facility_id": "L47340", "abnormal_count": 2,
                 "raw_saved": true, "agent_invoked": true}
            ],
            "errors": []
        }
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

                # 1) 원본 센서 데이터 먼저 저장 (LLM 왜곡 방지)
                save_raw_record(facility_id, sensor_values, abnormal_sensors)

                # 2) Agent에 전달할 페이로드 (분석 힌트)
                payload = {
                    'facility_id':      facility_id,
                    'product_type':     sensor_data.get('product_type', ''),
                    'sensor_values':    sensor_values,
                    'abnormal_sensors': abnormal_sensors,
                    'abnormal_count':   len(abnormal_sensors)
                }

                # 3) 정상/이상 무관하게 Agent 호출 (Mock 모드면 건너뜀)
                agent_invoked = False
                if not MOCK_MODE:
                    invoke_bedrock_agent(payload)
                    agent_invoked = True

                processed.append({
                    'facility_id':    facility_id,
                    'abnormal_count': len(abnormal_sensors),
                    'raw_saved':      True,
                    'agent_invoked':  agent_invoked
                })

            except Exception as e:
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
