# Lambda 3: 탐지 결과 DynamoDB 저장
# 역할: anomaly_filter의 전처리 결과 + Bedrock Agent 분석 결과를 DynamoDB에 저장
# 리전: us-east-1

import boto3
import json
from datetime import datetime
from decimal import Decimal

# DynamoDB 설정
TABLE_NAME = 'detection-results'
REGION = 'us-east-1'


def determine_status(risk_level) -> str:
    """
    Bedrock Agent가 반환한 위험도(0~100) 기준으로 상태 결정
    - 70 이상: DANGER
    - 30 이상 70 미만: WARNING
    - 30 미만: NORMAL
    """
    if risk_level >= 70:
        return 'DANGER'
    elif risk_level >= 30:
        return 'WARNING'
    else:
        return 'NORMAL'


def lambda_handler(event, context):
    """
    탐지 결과를 DynamoDB에 저장하는 Lambda

    입력 (event) — anomaly_filter + Bedrock Agent 결과를 합산한 구조:
        facility_id      (str, 필수): 설비 식별자
        sensor_values    (dict, 필수): 원본 센서 측정값
        abnormal_sensors (list, 필수): 이상 센서 목록 [{sensor, value, normal_range, unit}, ...]
        risk_level       (int|float, 선택, 기본 0): Bedrock Agent가 계산한 위험도 0~100
        status           (str, 선택): Bedrock Agent가 판단한 상태 (없으면 risk_level로 자동 계산)
        failure_type     (str, 선택): 고장 유형 (Bedrock Agent 추론 결과)
        recommendation   (str, 선택): 정비 권고 (Bedrock Agent 추론 결과)
        required_part    (str, 선택): 필요 부품 (Bedrock Agent 추론 결과)

    저장 스키마 (detection-results):
        PK: facility_id  (String)
        SK: timestamp    (String, ISO 형식)
        + 나머지 필드 전부
    """
    try:
        # ── 필수 필드 파싱 ──────────────────────────────────────────
        facility_id      = event.get('facility_id')
        sensor_values    = event.get('sensor_values', {})
        abnormal_sensors = event.get('abnormal_sensors', [])

        if not facility_id:
            return {
                'statusCode': 400,
                'error': 'facility_id는 필수 입력값입니다'
            }

        # ── Bedrock Agent 결과 파싱 (없으면 기본값) ────────────────
        risk_level    = event.get('risk_level', 0)
        failure_type  = event.get('failure_type', '')
        recommendation = event.get('recommendation', '')
        required_part = event.get('required_part', '')

        # status: 명시적으로 넘어오면 사용, 없으면 risk_level로 자동 계산
        status = event.get('status') or determine_status(risk_level)

        # ── 타임스탬프 생성 ─────────────────────────────────────────
        timestamp = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')

        # ── DynamoDB 저장 ───────────────────────────────────────────
        dynamodb = boto3.resource('dynamodb', region_name=REGION)
        table = dynamodb.Table(TABLE_NAME)

        item = {
            'facility_id':      facility_id,
            'timestamp':        timestamp,
            'status':           status,
            # 원본 센서값: JSON 문자열로 변환 (DynamoDB Map 대신 String 저장)
            'sensor_values':    json.dumps(sensor_values, ensure_ascii=False),
            # 이상 센서 목록: JSON 문자열로 변환
            'abnormal_sensors': json.dumps(abnormal_sensors, ensure_ascii=False),
            # Bedrock Agent 분석 결과
            'risk_level':       Decimal(str(risk_level)),
            'failure_type':     failure_type,
            'recommendation':   recommendation,
            'required_part':    required_part
        }

        table.put_item(Item=item)

        return {
            'statusCode': 200,
            'message': '저장 완료',
            'facility_id': facility_id,
            'timestamp': timestamp,
            'status': status
        }

    except Exception as e:
        return {
            'statusCode': 500,
            'error': str(e),
            'message': 'DynamoDB 저장 실패'
        }
