# calculator Lambda (Bedrock Agent Action Group)
# 리전: us-east-1
#
# 역할: Agent가 산술 계산이 필요할 때 호출하는 범용 계산기.
#   LLM은 곱셈/나눗셈 같은 정밀 산술에 약하므로, 정확한 숫자 계산은
#   이 도구에 위임한다 (Agentic 패턴의 표준 관행).
#
#   사용 예 (agent/prompt.txt에 정의된 공식들):
#     - 전력(kW)     = torque * rotation_speed / 9549        (PWF 판단)
#     - Strain       = tool_wear * torque                     (OSF 판단,
#                       L:11000 / M:12000 / H:13000 Nm·min 임계값)
#     - 온도차(K)    = process_temp - air_temp                (HDF 판단, 8.6K 기준)
#     - 이탈률(%)    = (측정값 - 임계값) / 임계값 * 100
#
# 입력 (Bedrock Action Group parameters):
#   expression (string) — 사칙연산 수식 문자열. 예: "(52.3-45.0)/45.0*100"
#                          허용 문자: 숫자, + - * / ( ) . 공백
#
# 출력:
#   result (float) — 계산 결과
#
# 보안: eval()을 직접 쓰지 않는다. ast 모듈로 수식을 파싱하여
#       숫자와 사칙연산자(+ - * / 단항 -)만 허용하는 안전한 평가기를 사용한다.
#       임의 코드 실행(함수 호출, 속성 접근, import 등)은 전부 차단된다.

import ast
import json
import operator

# 허용할 연산자만 명시적으로 매핑 (그 외 노드는 전부 거부됨)
_ALLOWED_BINOPS = {
    ast.Add:  operator.add,
    ast.Sub:  operator.sub,
    ast.Mult: operator.mul,
    ast.Div:  operator.truediv,
    ast.Pow:  operator.pow,
    ast.Mod:  operator.mod,
}
_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


class UnsafeExpressionError(Exception):
    pass


def _safe_eval(node):
    """
    ast 노드를 재귀적으로 평가한다. 숫자 리터럴과 사칙연산(+ - * / % **),
    단항 부호(+ -), 괄호만 허용한다. 그 외 노드(함수 호출, 이름 참조,
    속성 접근 등)는 UnsafeExpressionError를 발생시킨다.
    """
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)

    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise UnsafeExpressionError(f'허용되지 않는 상수: {node.value!r}')

    # 계산 로직
    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_BINOPS:
            raise UnsafeExpressionError(f'허용되지 않는 연산자: {op_type.__name__}')
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        return _ALLOWED_BINOPS[op_type](left, right)

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _ALLOWED_UNARYOPS:
            raise UnsafeExpressionError(f'허용되지 않는 단항 연산자: {op_type.__name__}')
        operand = _safe_eval(node.operand)
        return _ALLOWED_UNARYOPS[op_type](operand)

    raise UnsafeExpressionError(f'허용되지 않는 표현식 유형: {type(node).__name__}')


def safe_calculate(expression: str) -> float:
    """
    수식 문자열을 안전하게 계산한다. eval()을 쓰지 않고 ast로 파싱하여
    숫자/사칙연산만 허용한다.
    """
    if not isinstance(expression, str) or not expression.strip():
        raise ValueError('expression은 비어있지 않은 문자열이어야 합니다')

    try:
        tree = ast.parse(expression, mode='eval')
    except SyntaxError as e:
        raise ValueError(f'수식 파싱 실패: {e}')

    try:
        result = _safe_eval(tree)
    except ZeroDivisionError:
        raise ValueError('0으로 나눌 수 없습니다')
    except UnsafeExpressionError as e:
        raise ValueError(f'허용되지 않는 수식입니다: {e}')

    return float(result)


# ─────────────────────────────────────────────────────────────────────
# Bedrock Action Group 입출력 래퍼 (dynamo_save/range_check와 동일 패턴)
# ─────────────────────────────────────────────────────────────────────
def _is_bedrock_event(event: dict) -> bool:
    return isinstance(event, dict) and 'actionGroup' in event and (
        'parameters' in event or 'function' in event or 'apiPath' in event
    )


def _parse_bedrock_event(event: dict) -> dict:
    params = {}
    for p in event.get('parameters', []):
        name = p.get('name')
        if name:
            params[name] = p.get('value')
    return params


def _bedrock_response(event: dict, body_dict: dict) -> dict:
    return {
        'messageVersion': '1.0',
        'response': {
            'actionGroup': event.get('actionGroup', ''),
            'function':    event.get('function', ''),
            'functionResponse': {
                'responseBody': {
                    'TEXT': {'body': json.dumps(body_dict, ensure_ascii=False)}
                }
            }
        }
    }


def lambda_handler(event, context):
    """
    Bedrock Agent Action Group: calculator

    입력 (Bedrock Action Group 형식 또는 일반 JSON 둘 다 지원):
        expression (string) — 예: "(52.3-45.0)/45.0*100"

    출력:
        { "result": float }
        실패 시: { "error": "..." }
    """
    if _is_bedrock_event(event):
        params = _parse_bedrock_event(event)
    else:
        params = event

    expression = params.get('expression', '')

    try:
        result = safe_calculate(expression)
        body = {'result': result}
        if _is_bedrock_event(event):
            return _bedrock_response(event, body)
        return {'statusCode': 200, **body}

    except ValueError as e:
        body = {'error': str(e)}
        if _is_bedrock_event(event):
            return _bedrock_response(event, body)
        return {'statusCode': 400, **body}

    except Exception as e:
        body = {'error': f'계산 중 오류 발생: {e}'}
        if _is_bedrock_event(event):
            return _bedrock_response(event, body)
        return {'statusCode': 500, **body}
