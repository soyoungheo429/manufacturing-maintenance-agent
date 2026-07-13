# 🏭 manufacturing-maintenance-agent

AWS Bedrock Agent 기반 제조 설비 고장 예측 및 자율 정비 권고 시스템

## 팀원

| 이름 | 역할 | 담당 |
|------|------|------|
| 허소영 | 클라우드 인프라 | AWS 리소스 + Lambda (센서/필터/저장) |
| 임수희 | AI/ML | 데이터 전처리 + KB + Bedrock Agent |
| 손재우 | 프론트엔드 | 웹 대시보드 + Lambda (재고/발주/조회) |

## 브랜치 전략
- main: 최종 완성본
- soyoung: 허소영
- suhee: 임수희
- jaewoo: 손재우

## 시작하기
cp .env.example .env
# .env에 값 입력 후 개발 시작

## 주의사항
- .env 파일 절대 커밋 금지

## 참고 자료
- AI4I 2020 Dataset: https://archive.ics.uci.edu/dataset/601
- Bedrock Agents: https://docs.aws.amazon.com/bedrock/latest/userguide/agents.html
