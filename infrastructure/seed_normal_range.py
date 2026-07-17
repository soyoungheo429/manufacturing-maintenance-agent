# sensor-normal-range 테이블 생성 + AI4I 2020 기준값 시드
# range_check Lambda가 조회하는 정상 범위 데이터를 준비한다.
#
# 실행 방법: python infrastructure/seed_normal_range.py
# 리전: us-east-1

import boto3
from decimal import Decimal

REGION     = 'us-east-1'
TABLE_NAME = 'sensor-normal-range'

NORMAL_RANGE = {
    'air_temp':       {'min': 295.3, 'max': 304.5, 'unit': 'K'},
    'process_temp':   {'min': 305.7, 'max': 313.8, 'unit': 'K'},
    'rotation_speed': {'min': 1168,  'max': 2695,  'unit': 'rpm'},
    'torque':         {'min': 12.6,  'max': 70.0,  'unit': 'Nm'},
    'tool_wear':      {'min': 0,     'max': 221,   'unit': 'min'}
}


def create_table_if_not_exists():
    client = boto3.client('dynamodb', region_name=REGION)
    existing = client.list_tables()['TableNames']
    if TABLE_NAME in existing:
        print(f'{TABLE_NAME} 테이블이 이미 존재합니다.')
        return

    client.create_table(
        TableName=TABLE_NAME,
        KeySchema=[{'AttributeName': 'sensor_type', 'KeyType': 'HASH'}],
        AttributeDefinitions=[{'AttributeName': 'sensor_type', 'AttributeType': 'S'}],
        BillingMode='PAY_PER_REQUEST'
    )
    client.get_waiter('table_exists').wait(TableName=TABLE_NAME)
    print(f'{TABLE_NAME} 테이블 생성 완료.')


def seed_data():
    dynamodb = boto3.resource('dynamodb', region_name=REGION)
    table = dynamodb.Table(TABLE_NAME)

    for sensor_type, spec in NORMAL_RANGE.items():
        table.put_item(Item={
            'sensor_type': sensor_type,
            'min':         Decimal(str(spec['min'])),
            'max':         Decimal(str(spec['max'])),
            'unit':        spec['unit']
        })
        print(f'  - {sensor_type}: {spec["min"]}~{spec["max"]} {spec["unit"]}')

    print('시드 데이터 삽입 완료.')


if __name__ == '__main__':
    create_table_if_not_exists()
    seed_data()
