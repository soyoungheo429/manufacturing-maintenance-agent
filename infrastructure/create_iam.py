# =============================================
# 현재 상태: AWS CLI로 us-east-1에 생성 완료
# 추후 계획: boto3 코드로 대체 예정
# 실행 방법: python create_iam.py
# =============================================
#
# [이미 생성된 리소스 - us-east-1]
#
#   역할 1: lambda-execution-role
#     - 신뢰 대상(Trust Policy): lambda.amazonaws.com
#     - 연결된 정책:
#         AmazonS3FullAccess
#         AmazonDynamoDBFullAccess
#         AmazonBedrockFullAccess
#         CloudWatchLogsFullAccess
#     - ARN: arn:aws:iam::929751801721:role/lambda-execution-role
#     - 용도: Lambda 함수 실행 역할
#
#   역할 2: bedrock-agent-role
#     - 신뢰 대상(Trust Policy): bedrock.amazonaws.com
#     - 연결된 정책:
#         AmazonBedrockFullAccess
#         AmazonS3FullAccess
#         AmazonDynamoDBFullAccess
#         CloudWatchLogsFullAccess
#     - ARN: arn:aws:iam::929751801721:role/bedrock-agent-role
#     - 용도: Bedrock Agent 실행 역할
#
# [추후 구현할 내용]
#
#   1. boto3 클라이언트 초기화
#      client = boto3.client('iam')
#      (IAM은 글로벌 서비스이므로 region_name 불필요)
#
#   2. Trust Policy JSON 정의
#      lambda_trust_policy = {
#          "Version": "2012-10-17",
#          "Statement": [{
#              "Effect": "Allow",
#              "Principal": {"Service": "lambda.amazonaws.com"},
#              "Action": "sts:AssumeRole"
#          }]
#      }
#      bedrock_trust_policy = {
#          "Version": "2012-10-17",
#          "Statement": [{
#              "Effect": "Allow",
#              "Principal": {"Service": "bedrock.amazonaws.com"},
#              "Action": "sts:AssumeRole"
#          }]
#      }
#
#   3. 역할 2개 생성
#      client.create_role(
#          RoleName='lambda-execution-role',
#          AssumeRolePolicyDocument=json.dumps(lambda_trust_policy)
#      )
#      client.create_role(
#          RoleName='bedrock-agent-role',
#          AssumeRolePolicyDocument=json.dumps(bedrock_trust_policy)
#      )
#
#   4. 관리형 정책 연결 (각 역할에 4개씩)
#      managed_policies = [
#          'arn:aws:iam::aws:policy/AmazonS3FullAccess',
#          'arn:aws:iam::aws:policy/AmazonDynamoDBFullAccess',
#          'arn:aws:iam::aws:policy/AmazonBedrockFullAccess',
#          'arn:aws:iam::aws:policy/CloudWatchLogsFullAccess'
#      ]
#      for policy_arn in managed_policies:
#          client.attach_role_policy(RoleName='lambda-execution-role', PolicyArn=policy_arn)
#          client.attach_role_policy(RoleName='bedrock-agent-role', PolicyArn=policy_arn)
#
# [create_all.py에서 호출되는 함수]
#   def create_roles():
#       pass  # 추후 boto3 코드로 구현 예정
