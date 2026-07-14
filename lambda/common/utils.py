"""Lambda 공용 유틸 — API Gateway 응답 포맷, JSON 직렬화, 환경변수 헬퍼."""
import json
import os
from decimal import Decimal


class DecimalEncoder(json.JSONEncoder):
    """DynamoDB가 숫자를 Decimal로 돌려주므로 JSON 직렬화 시 int/float로 변환."""

    def default(self, obj):
        if isinstance(obj, Decimal):
            # 정수면 int, 아니면 float
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)


def api_response(status_code, body):
    """API Gateway(Lambda 프록시 통합)용 응답 + CORS 헤더.

    프론트엔드가 다른 오리진(localhost / S3 정적 호스팅)에서 호출하므로 CORS 필수.
    """
    return {
        "statusCode": status_code,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
            "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        },
        "body": json.dumps(body, cls=DecimalEncoder, ensure_ascii=False),
    }


def parse_event_body(event):
    """API Gateway 프록시 이벤트든 직접 호출(Lambda Test)이든 동일하게 dict로 파싱.

    - API Gateway 프록시: 페이로드가 event["body"](JSON 문자열)에 담김
    - 콘솔 Test / Action Group 직접 호출: event 자체가 페이로드
    """
    if isinstance(event, dict) and "body" in event and event["body"] is not None:
        body = event["body"]
        if isinstance(body, str):
            try:
                return json.loads(body)
            except json.JSONDecodeError:
                return {}
        return body
    return event or {}


def env(name, default=None):
    return os.environ.get(name, default)
