"""Lambda 7 — 새로고침 + 1분 쿨다운 (refresh)

POST /refresh 로 호출된다. 사용자별 쿨다운을 확인하고,
쿨다운이 지났으면 sensor_read Lambda를 트리거(실제 폴링 재실행)한다.

- 첫 호출:        200 { "triggered": true }
- 쿨다운 내 호출:  429 { "cooldown": true, "remaining": <초> }
- 1분 경과 후:     200 (다시 트리거)

프론트엔드 api/index.js의 refreshData()가 429의 remaining을 읽어
클라이언트 쿨다운 타이머를 서버 기준으로 동기화한다.

MVP는 Lambda 메모리(워밍된 컨테이너)에 마지막 호출 시각을 저장한다.
실제 운영에서는 DynamoDB(또는 ElastiCache)로 이전해 다중 인스턴스에서도
쿨다운이 공유되도록 해야 한다.
"""
import sys
import os
import time

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from common.utils import parse_event_body, api_response  # noqa: E402

COOLDOWN_SEC = 60

# 사용자별 마지막 새로고침 시각(epoch) — 콜드스타트 시 초기화됨(MVP 한계)
_last_refresh = {}


def trigger_sensor_read(use_mock):
    """sensor_read Lambda 호출 (실제) 또는 목업 스킵."""
    if use_mock:
        return {"triggered": True, "mock": True}
    import boto3

    region = os.environ.get("AWS_REGION", "us-east-1")
    fn = os.environ.get("SENSOR_READ_FUNCTION", "sensor_read")
    client = boto3.client("lambda", region_name=region)
    client.invoke(FunctionName=fn, InvocationType="Event")  # 비동기 트리거
    return {"triggered": True}


def handler(event, context):
    body = parse_event_body(event)
    use_mock = body.get("use_mock", False)
    user_id = body.get("user_id", "default")

    now = time.time()
    last = _last_refresh.get(user_id, 0)
    elapsed = now - last

    if elapsed < COOLDOWN_SEC:
        remaining = int(round(COOLDOWN_SEC - elapsed))
        return api_response(429, {"cooldown": True, "remaining": remaining})

    _last_refresh[user_id] = now
    result = trigger_sensor_read(use_mock)
    return api_response(200, {"cooldown": False, **result})


lambda_handler = handler
