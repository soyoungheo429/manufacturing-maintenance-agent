# Lambda 1: 센서 데이터 읽기 + Bedrock Agent 호출
# 리전: us-east-1
#
# 흐름 변경 (Agentic 아키텍처 전환):
#   기존: EventBridge(10분)/refresh → sensor_read → anomaly_filter(범위비교+힌트) → Agent
#   변경: EventBridge(10분)/refresh → sensor_read → Agent (raw 데이터 그대로 전달)
#
#   anomaly_filter는 제거되었다. 센서값이 정상 범위인지 판단하는 것은
#   이제 Agent가 range_check Action Group을 스스로 호출해서 판단한다.
#   이 Lambda는 전처리나 판단을 하지 않고, S3에서 읽은 원본 데이터를
#   그대로 invoke_agent()에 전달하기만 한다.
#
# 설비 ID 관련 변경:
#   기존에는 AI4I 데이터셋의 Product ID(예: L47340)를 그대로 facility_id로
#   사용했다. Product ID는 수천 개가 존재하는 임시 식별자라 샘플링할 때마다
#   설비 ID가 랜덤하게 바뀌는 문제가 있었다 (대시보드에서 "설비 5대"를
#   고정 추적할 수 없음). 이제는 고정된 설비 ID 5개(FACILITY_IDS)를
#   미리 정의해두고, 샘플링된 5행에 순서대로 매핑한다.
#   원본 Product ID는 source_product_id로 남겨서 데이터 추적용으로 보존한다.

import boto3
import pandas as pd
import io
import json
import os
import time
import uuid

# 시뮬레이션 설비 수
NUM_FACILITIES = 5
# 시연 시 이상 감지가 반드시 보이도록 고장 데이터에서 보장할 최소 설비 수
NUM_GUARANTEED_FAILURES = 2

# 고정 설비 ID (매 실행마다 동일한 5대를 추적할 수 있도록 고정)
FACILITY_IDS = ['FAC-001', 'FAC-002', 'FAC-003', 'FAC-004', 'FAC-005']

REGION         = 'us-east-1'
AGENT_ID       = os.environ.get('BEDROCK_AGENT_ID', '')
AGENT_ALIAS_ID = os.environ.get('BEDROCK_AGENT_ALIAS_ID', '')
# 세션 ID 접두어 (설비별로 세션을 분리하기 위함)
SESSION_PREFIX = os.environ.get('SESSION_PREFIX', 'sensor-session')


def read_sensor_data():
    """S3에서 센서 데이터를 읽어 5대 설비 raw 데이터를 반환한다 (전처리 없음)."""
    s3_client = boto3.client('s3', region_name=REGION)

    bucket_name = 'pbl5team-sensor-data'
    file_key = 'latest/sensor_data.csv'

    response = s3_client.get_object(Bucket=bucket_name, Key=file_key)
    csv_content = response['Body'].read().decode('utf-8')

    df = pd.read_csv(io.StringIO(csv_content))

    # 고장/정상 풀 분리 (시연 시 이상 감지가 반드시 보이도록 함)
    failure_pool = df[df['Machine failure'] == 1]
    normal_pool  = df[df['Machine failure'] == 0]

    n_fail   = min(NUM_GUARANTEED_FAILURES, len(failure_pool))
    n_normal = NUM_FACILITIES - n_fail

    sampled_failure = failure_pool.sample(n=n_fail, random_state=None)
    sampled_normal  = normal_pool.sample(n=n_normal, random_state=None)

    # 합치고 셔플 (순서 고정 방지)
    sampled_df = pd.concat([sampled_failure, sampled_normal]).sample(frac=1).reset_index(drop=True)

    # 컬럼명 rename
    sampled_df = sampled_df.rename(columns={
        'Air temperature [K]':     'air_temp',
        'Process temperature [K]': 'process_temp',
        'Rotational speed [rpm]':  'rotation_speed',
        'Torque [Nm]':             'torque',
        'Tool wear [min]':         'tool_wear'
    })

    # 고정 설비 ID를 순서대로 매핑 (원본 Product ID는 source_product_id로 보존)
    sensor_data = []
    for i, (_, row) in enumerate(sampled_df.iterrows()):
        sensor_data.append({
            'facility_id':        FACILITY_IDS[i],
            'source_product_id':  str(row['Product ID']),
            'product_type':       str(row['Type']),
            'air_temp':            float(row['air_temp']),
            'process_temp':        float(row['process_temp']),
            'rotation_speed':      int(row['rotation_speed']),
            'torque':              float(row['torque']),
            'tool_wear':           int(row['tool_wear'])
        })

    return sensor_data


def invoke_agent_for_facility(facility_data: dict) -> None:
    """
    설비 1대의 raw 센서 데이터를 Bedrock Agent에 그대로 전달한다.
    전처리/판단 없이 데이터만 넘기고, 이상 여부 판단(range_check),
    원인 분석(rag_search/calculator), 저장(db_save)은 전부 Agent가 수행한다.

    Agent Instruction의 입력 형식 정의(facility_id, product_type,
    sensor_values{...})와 맞추기 위해, 센서 측정값 5개는 sensor_values로
    묶어서 전달한다. source_product_id는 데이터 추적용이라 판단에는
    불필요하므로 감싸지 않고 최상위에 남겨둔다.

    세션 ID는 매 호출마다 새로 생성한다 (설비 고정 세션 재사용 안 함).
    설비별로 세션을 고정했을 때, Bedrock Agent가 세션에 쌓인 과거
    대화 히스토리(옛 Instruction 기준의 예전 tool call 패턴)를 최신
    Instruction 지침보다 우선 참고하는 문제가 있었다 (예: dynamo_save를
    옛 5-파라미터 방식으로 호출, required_part에 "NORMAL" 삽입,
    recommendation을 영어로 반환). 설비별 과거 이력은 세션이 아니라
    Knowledge Base(facility-kb-v3, backup/failure_history.txt 기반)가
    담당하므로, 세션을 매번 새로 만들어도 "설비별 기억" 기능은 유지된다.
    """
    client = boto3.client('bedrock-agent-runtime', region_name=REGION)

    session_id = f"{SESSION_PREFIX}-{facility_data['facility_id']}-{int(time.time())}-{uuid.uuid4().hex[:6]}"

    payload = {
        'facility_id':       facility_data['facility_id'],
        'source_product_id': facility_data['source_product_id'],
        'product_type':      facility_data['product_type'],
        'sensor_values': {
            'air_temp':       facility_data['air_temp'],
            'process_temp':   facility_data['process_temp'],
            'rotation_speed': facility_data['rotation_speed'],
            'torque':         facility_data['torque'],
            'tool_wear':      facility_data['tool_wear']
        }
    }
    input_text = json.dumps(payload, ensure_ascii=False)

    response = client.invoke_agent(
        agentId=AGENT_ID,
        agentAliasId=AGENT_ALIAS_ID,
        sessionId=session_id,
        inputText=input_text
    )

    # 스트리밍 응답을 끝까지 소비해야 Agent 실행이 완료됨 (내용은 사용하지 않음)
    for event in response.get('completion', []):
        _ = event.get('chunk', {})


def lambda_handler(event, context):
    """
    S3에서 센서 데이터를 읽어 5대 설비 raw 데이터를 Bedrock Agent에 전달하는 Lambda

    입력: 없음 (EventBridge 스케줄 또는 refresh Lambda가 트리거)

    출력:
        {
            "statusCode": 200,
            "sensor_data": [...],       # 참고/디버깅용 원본 데이터
            "agent_invoked": [...]      # 설비별 Agent 호출 성공 여부
        }
    """
    if not AGENT_ID or not AGENT_ALIAS_ID:
        return {
            'statusCode': 500,
            'error': 'BEDROCK_AGENT_ID 또는 BEDROCK_AGENT_ALIAS_ID 환경변수가 설정되지 않았습니다'
        }

    try:
        sensor_data = read_sensor_data()

        agent_invoked = []
        errors = []

        for facility_data in sensor_data:
            try:
                invoke_agent_for_facility(facility_data)
                agent_invoked.append({
                    'facility_id': facility_data['facility_id'],
                    'invoked': True
                })
            except Exception as e:
                agent_invoked.append({
                    'facility_id': facility_data['facility_id'],
                    'invoked': False
                })
                errors.append({'facility_id': facility_data['facility_id'], 'error': str(e)})

        return {
            'statusCode': 200,
            'sensor_data': sensor_data,
            'agent_invoked': agent_invoked,
            'errors': errors,
            'message': f'{len(sensor_data)}대 센서 데이터 읽기 완료, Agent 호출 {sum(1 for a in agent_invoked if a["invoked"])}건 성공'
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'error': str(e),
            'message': '센서 데이터 읽기 실패'
        }
