# Lambda 1: 센서 데이터 읽기
# 리전: us-east-1

import boto3
import pandas as pd
import io

# 시뮬레이션 설비 수
NUM_FACILITIES = 5
# 시연 시 이상 감지가 반드시 보이도록 고장 데이터에서 보장할 최소 설비 수
NUM_GUARANTEED_FAILURES = 2

REGION = 'us-east-1'


def lambda_handler(event, context):
    """
    S3에서 센서 데이터를 읽어 5대 설비 상태를 반환하는 Lambda 함수

    샘플링 전략 (시연용):
    - 고장 풀 (Machine failure=1): NUM_GUARANTEED_FAILURES 행 샘플링
    - 정상 풀 (Machine failure=0): 나머지 행 샘플링
    - 두 풀을 합쳐 셔플 → 항상 일부 이상 설비가 포함됨

    설비 ID: 각 행의 Product ID를 그대로 사용 (L/M/H 타입 포함)
    """
    try:
        # S3 클라이언트 초기화
        s3_client = boto3.client('s3', region_name='us-east-1')

        # S3에서 CSV 파일 읽기
        bucket_name = 'pbl5team-sensor-data'
        file_key = 'latest/sensor_data.csv'

        response = s3_client.get_object(Bucket=bucket_name, Key=file_key)
        csv_content = response['Body'].read().decode('utf-8')

        df = pd.read_csv(io.StringIO(csv_content))

        # 고장/정상 풀 분리
        failure_pool = df[df['Machine failure'] == 1]
        normal_pool  = df[df['Machine failure'] == 0]

        # 고장 풀에서 NUM_GUARANTEED_FAILURES 행 샘플링
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

        # Product ID를 설비 ID로 사용
        sensor_data = []
        for _, row in sampled_df.iterrows():
            sensor_data.append({
                'facility_id':    str(row['Product ID']),
                'product_type':   str(row['Type']),
                'air_temp':       float(row['air_temp']),
                'process_temp':   float(row['process_temp']),
                'rotation_speed': int(row['rotation_speed']),
                'torque':         float(row['torque']),
                'tool_wear':      int(row['tool_wear'])
            })

        return {
            'statusCode': 200,
            'sensor_data': sensor_data
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'error': str(e),
            'message': '센서 데이터 읽기 실패'
        }
