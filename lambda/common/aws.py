"""AWS 리소스 클라이언트 헬퍼 — DynamoDB 테이블 핸들 등을 지연 생성.

boto3 클라이언트는 콜드스타트에서만 만들면 되도록 모듈 레벨에 캐시.
로컬/목업 환경에서 boto3가 없거나 자격증명이 없어도 import 자체는 실패하지 않도록
사용 시점에 lazy import 한다.
"""
import os

_dynamodb = None


def _get_dynamodb():
    global _dynamodb
    if _dynamodb is None:
        import boto3  # lazy import — 목업 실행 시 boto3 미설치여도 무방

        region = os.environ.get("AWS_REGION", "ap-northeast-2")
        _dynamodb = boto3.resource("dynamodb", region_name=region)
    return _dynamodb


def get_table(env_name, default_name):
    """환경변수로 지정된 DynamoDB 테이블 핸들 반환.

    env_name: 테이블명을 담은 환경변수 이름 (예: "DYNAMODB_INVENTORY_TABLE")
    default_name: 환경변수 미설정 시 사용할 기본 테이블명
    """
    table_name = os.environ.get(env_name, default_name)
    return _get_dynamodb().Table(table_name)
