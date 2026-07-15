# facility-pipeline Lambda
# Action Group 1: 이상 탐지
# 역할: 센서 데이터 읽기 + 이상 센서 추출만 수행 (저장하지 않음)
#
# Bedrock Agent 실행 흐름:
#   1. Agent가 이 Lambda(facility-pipeline) 호출
#      → sensor_values + abnormal_sensors 반환받음
#   2. Agent(Claude)가 Knowledge Base 검색 + 위험도/고장유형/권고 추론
#   3. Agent가 dynamo-save Lambda 호출 (분석 결과 포함하여 저장)
#   4. 이상 있으면 Agent가 maintenance-pipeline Lambda 호출
#
# 리전: us-east-1

import boto3
import pandas as pd
import io
import os
import random

# ── 설정 ────────────────────────────────────────────────────────────
REGION     = 'us-east-1'
BUCKET     = 'pbl5team-sensor-data'
FILE_KEY   = 'latest/sensor_data.csv'
MOCK_MODE  = os.environ.get('MOCK_MODE', 'false').lower() == 'true'

NUM_FACILITIES          = 5
NUM_GUARANTEED_FAILURES = 2

# 정상 범위 (AI4I 2020 기준)
NORMAL_RANGE = {
    'air_temp':       {'min': 295.3, 'max': 304.5, 'unit': 'K'},
    'process_temp':   {'min': 305.7, 'max': 313.8, 'unit': 'K'},
    'rotation_speed': {'min': 1168,  'max': 2695,  'unit': 'rpm'},
    'torque':         {'min': 12.6,  'max': 70.0,  'unit': 'Nm'},
    'tool_wear':      {'min': 0,     'max': 221,   'unit': 'min'}
}


# ── Step 1: S3에서 센서 데이터 읽기 ─────────────────────────────────
def read_sensor_data() -> list:
    """
    S3 CSV에서 5대 설비 센서 데이터를 샘플링하여 반환.
    고장 풀에서 NUM_GUARANTEED_FAILURES대, 정상 풀에서 나머지를 샘플링.
    """
    s3 = boto3.client('s3', region_name=REGION)
    response = s3.get_object(Bucket=BUCKET, Key=FILE_KEY)
    df = pd.read_csv(io.StringIO(response['Body'].read().decode('utf-8')))

    failure_pool = df[df['Machine failure'] == 1]
    normal_pool  = df[df['Machine failure'] == 0]

    n_fail   = min(NUM_GUARANTEED_FAILURES, len(failure_pool))
    n_normal = NUM_FACILITIES - n_fail

    sampled_df = pd.concat([
        failure_pool.sample(n=n_fail),
        normal_pool.sample(n=n_normal)
    ]).sample(frac=1).reset_index(drop=True)

    sampled_df = sampled_df.rename(columns={
        'Air temperature [K]':     'air_temp',
        'Process temperature [K]': 'process_temp',
        'Rotational speed [rpm]':  'rotation_speed',
        'Torque [Nm]':             'torque',
        'Tool wear [min]':         'tool_wear'
    })

    return [
        {
            'facility_id':    str(row['Product ID']),
            'product_type':   str(row['Type']),
            'air_temp':       float(row['air_temp']),
            'process_temp':   float(row['process_temp']),
            'rotation_speed': int(row['rotation_speed']),
            'torque':         float(row['torque']),
            'tool_wear':      int(row['tool_wear'])
        }
        for _, row in sampled_df.iterrows()
    ]


# ── Step 2: 이상 센서 추출 ───────────────────────────────────────────
def extract_abnormal_sensors(sensor_data: dict) -> list:
    """
    센서값을 정상 범위와 비교하여 벗어난 센서 목록 반환.
    Bedrock Agent가 이 결과를 분석 근거로 활용한다.
    """
    abnormal = []
    for sensor, spec in NORMAL_RANGE.items():
        value = sensor_data.get(sensor)
        if value is None:
            continue
        if value < spec['min'] or value > spec['max']:
            abnormal.append({
                'sensor':       sensor,
                'value':        value,
                'normal_range': f"{spec['min']}~{spec['max']}",
                'unit':         spec['unit']
            })
    return abnormal


# ── Mock 참고용 (테스트 시 예상 결과 확인용, 저장하지 않음) ──────────
def mock_status(abnormal_sensors: list) -> str:
    """
    MOCK_MODE 테스트 시 참고용 상태 표시.
    실제 위험도/상태 판단은 Bedrock Agent가 수행하므로
    여기서는 결과 확인 편의를 위한 힌트만 제공한다.
    """
    if not abnormal_sensors:
        return 'NORMAL'
    return 'WARNING' if len(abnormal_sensors) == 1 else random.choice(['WARNING', 'DANGER'])


# ── Lambda Handler ───────────────────────────────────────────────────
def lambda_handler(event, context):
    """
    Bedrock Agent Action Group 1: 이상 탐지 (전처리 전용)

    입력 (event):
        없음 — 호출 시 S3에서 자동으로 센서 데이터 읽음

    출력:
        {
            "statusCode": 200,
            "results": [
                {
                    "facility_id": "L47340",
                    "product_type": "L",
                    "sensor_values": {
                        "air_temp": 298.4,
                        "process_temp": 309.8,
                        "rotation_speed": 1421,
                        "torque": 68.3,
                        "tool_wear": 210
                    },
                    "abnormal_sensors": [
                        {
                            "sensor": "tool_wear",
                            "value": 210,
                            "normal_range": "0~221",
                            "unit": "min"
                        }
                    ],
                    "abnormal_count": 1
                },
                ...
            ],
            "anomaly_count": 2   ← 이상 감지된 설비 수
        }

    이후 Agent가:
      - 각 설비의 abnormal_sensors를 근거로 KB 검색 + Claude 추론
      - dynamo-save Lambda 호출 (위험도/고장유형/권고 포함하여 저장)
      - anomaly_count > 0 이면 maintenance-pipeline Lambda 호출
    """
    try:
        sensor_data_list = read_sensor_data()

        results       = []
        anomaly_count = 0

        for sensor_data in sensor_data_list:
            facility_id = sensor_data['facility_id']

            sensor_values = {
                k: v for k, v in sensor_data.items()
                if k not in ('facility_id', 'product_type')
            }

            abnormal_sensors = extract_abnormal_sensors(sensor_data)

            result = {
                'facility_id':      facility_id,
                'product_type':     sensor_data.get('product_type', ''),
                'sensor_values':    sensor_values,
                'abnormal_sensors': abnormal_sensors,
                'abnormal_count':   len(abnormal_sensors)
            }

            if MOCK_MODE:
                # 테스트 편의용 힌트 (실제 판단은 Agent가 수행)
                result['mock_status_hint'] = mock_status(abnormal_sensors)

            results.append(result)

            if abnormal_sensors:
                anomaly_count += 1

        return {
            'statusCode':    200,
            'results':       results,
            'anomaly_count': anomaly_count
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'error':      str(e),
            'message':    'facility-pipeline 실행 실패'
        }
