# 🏭 manufacturing-maintenance-agent

AWS Bedrock Agent 기반 제조 설비 고장 예측 및 자율 정비 권고 시스템

---

## 1. 프로젝트 소개

### 프로젝트명 및 주제

**manufacturing-maintenance-agent** — AWS Bedrock Agent 기반 제조 설비 고장 예측 및 자율 정비 권고 시스템

제조 설비 센서 데이터를 AI Agent가 도구를 자율적으로 활용하여 고장을 사전 예측하고, RAG 기반 정비 권고부터 부품 발주까지 전 과정을 자동화하는 시스템입니다.

### 팀원 소개 및 역할

| 이름 | 역할 | 담당 |
|------|------|------|
| 허소영 | 클라우드 인프라 | AWS 리소스 구성, Lambda(sensor_read / calculator / range_check / dynamo_save), Bedrock Agent 배포·운영 |
| 임수희 | AI/ML | 데이터 전처리, Knowledge Base 구축, Bedrock Agent Instruction 설계 |
| 손재우 | 프론트엔드 | 웹 대시보드, Lambda(inventory_check / create_order / dashboard_data / refresh) |

### 프로젝트 목표

1. **100% 서버리스 아키텍처** — Lambda, DynamoDB, S3, Bedrock 등 완전관리형 서비스만으로 구성하여 VPC·서버 관리 오버헤드를 제거
2. **AI Agent 기반 자율 판단 워크플로우** — Bedrock Agent가 calculator, range_check, Knowledge Base 등 도구를 자율적으로 선택하여 고장을 진단
3. **RAG 기반 과거 이력 활용** — Knowledge Base에 축적된 과거 고장 이력과 정비 매뉴얼을 검색하여 유사 사례 기반 정비 권고를 생성
4. **이벤트 기반 알림 및 통합 대시보드** — DANGER 판정 시 SNS로 즉시 알림, 웹 대시보드에서 전체 현황을 한눈에 파악

---

## 2. 문제 정의

### 현황 및 배경

현재 대다수 제조 현장은 고장이 발생한 뒤 대응하는 **사후 정비**, 또는 일정 주기마다 부품을 교체하는 **예방 정비**에 의존하고 있습니다.

### 기존 서비스의 문제점

- 설비가 한 번 정지하면 피해 규모가 막대함 (예: 반도체 공장 정전 사고 시 단시간 정지에도 수백억 원 손실 사례)
- 예지 정비(Predictive Maintenance) 도입률이 극히 낮음 — 국내 제조 중소기업 중 AI 기반 스마트공장 도입률은 0.1% 수준
- 기존 예지 정비 시스템은 평균 구축비 7.5억 원, ML 전담 인력 보유율 0.9%로 GPU 서버와 별도 ML 파이프라인 구축이 필수적이라 중소기업이 감당하기 어려운 진입 장벽 존재

### 문제 해결 필요성

속도, 접근성, 비용을 모두 만족하는 새로운 방식의 예지 정비가 필요합니다. 이에 대한 해답으로, GPU 서버나 상시 운영 인프라 없이 **서버리스 AI Agent 기반 시스템**을 설계했습니다.

---

## 3. 서비스 소개

### 서비스 개요

설비 센서 데이터를 10분마다 자동 수집하고, 이상이 감지되면 Bedrock Agent가 자율적으로 원인을 진단하여 정비를 권고하며, 필요 부품의 재고 확인부터 발주까지 자동화합니다.

### 핵심 기능

- **자동 센서 수집**: EventBridge가 10분 주기로 설비 5대의 센서 데이터를 조회
- **Agent 자율 진단**: Bedrock Agent가 calculator(정밀 계산), range_check(정상범위 판정), Knowledge Base 검색(과거 이력/매뉴얼)을 상황에 맞게 자율적으로 호출해 고장 유형과 위험도를 판정
- **RAG 기반 정비 권고**: 과거 고장 이력과 정비 매뉴얼을 검색해 유사 사례 기반의 구체적인 권고안 생성
- **이벤트 기반 알림**: DANGER 판정 시 SNS를 통해 담당자에게 즉시 이메일 발송
- **재고 확인·발주 자동화**: 필요 부품의 재고를 조회하고, 부족 시 발주서(PDF)를 자동 생성
- **통합 대시보드**: 설비 현황, 센서 추이, 발주 승인/거절을 한 화면에서 관리

### 사용자 흐름

1. 설비 센서 데이터가 S3에 저장됨
2. EventBridge가 10분 주기로 `sensor_read` Lambda를 트리거
3. `sensor_read`가 5대 설비의 센서값을 Bedrock Agent에 전달
4. Agent가 calculator/range_check/Knowledge Base를 자율적으로 활용해 고장 유형·위험도 판정
5. 판정 결과를 `dynamo_save`가 DynamoDB에 저장, DANGER 시 SNS 이메일 발송
6. 필요 부품이 있으면 `inventory_check`로 재고 확인 → 부족 시 `create_order`로 발주서 생성
7. 현장 작업자가 대시보드에서 결과를 확인하고 발주를 승인/거절

### 차별점

| 항목 | 기존 예지 정비 시스템 | 본 프로젝트 |
|------|----------------------|-------------|
| 인프라 | GPU 서버, 상시 운영 ML 파이프라인 필요 | 100% 서버리스, 즉시 도입 가능 |
| 처리 범위 | 이상 탐지까지만 | 원인 진단 → 정비 권고 → 발주까지 자동화 |
| 판단 방식 | 사전에 고정된 파이프라인 | Agent가 상황별로 도구를 자율 선택 |
| 근거 제시 | 결과값만 제공 | 계산 근거 + 과거 유사사례(RAG) 함께 제시 |
| 초기 구축비 | 평균 7.5억 원 | 완전관리형 서비스 사용량 기반 과금 |

---

## 4. 구현 내역 및 AWS 아키텍처

### 기술 스택

**AI/모델**
- Amazon Bedrock (Claude Opus 4.8) — Agent 오케스트레이션 및 추론
- Bedrock Knowledge Base + OpenSearch Serverless — RAG 벡터 검색

**데이터**
- AI4I 2020 Predictive Maintenance Dataset (10,000건, 설비 5대 상정)
- 과거 고장 이력 데이터, 정비 매뉴얼 (Knowledge Base 색인용)

**인프라 / 백엔드**
- AWS Lambda (Python) — Agent Action Group 및 데이터 파이프라인
- Amazon DynamoDB — 분석 결과, 재고, 발주 데이터 저장
- Amazon S3 — 센서 원본 데이터, Knowledge Base 문서 저장
- Amazon EventBridge — 10분 주기 자동 트리거
- Amazon SNS — DANGER 판정 시 이메일 알림
- Amazon API Gateway — 대시보드 연동 REST API
- AWS IAM — 최소 권한 정책
- Amazon CloudWatch — Lambda 실행 로그, Agent trace 모니터링

**프론트엔드**
- React + Vite

### 주요 기능 구현 (Lambda 8종)

**Bedrock Agent Action Group (5개)**
- `sensor_read` — S3에서 센서 데이터를 조회해 Bedrock Agent를 호출하는 트리거
- `range_check` — 개별 센서값의 정상 범위 이탈 여부와 이탈률을 반환 (예: 정상 범위 12.6~70.0 대비 63% 이탈)
- `calculator` — 전력, Strain, 온도차 등 복합 사칙연산을 정밀 계산. LLM이 직접 계산 시 발생할 수 있는 오차를 방지하기 위해 별도 도구로 분리
- `dynamo_save` — 분석 결과를 DynamoDB에 저장하고, 위험도 DANGER 확정 시 SNS 알림 발송
- `inventory_check` — 필요 부품의 재고 수량 조회

**발주/대시보드 연동**
- `create_order` — 재고 부족 시 발주서 PDF 생성
- `dashboard_data` — API Gateway를 통해 DynamoDB의 설비별 분석 결과를 대시보드에 전달
- `refresh` — 대시보드의 수동 새로고침 버튼 요청을 받아 `sensor_read`를 즉시 트리거

### 서비스 아키텍처

```
[제조 설비 센서 데이터]
        │  저장
        ▼
   [Amazon S3] ──(10분 주기)── [EventBridge] ──▶ [sensor_read Lambda]
                                                        │ invoke_agent (설비 5대)
                                                        ▼
                                            ┌─────────────────────────┐
                                            │     Bedrock Agent        │
                                            │  (Claude Opus 4.8)       │
                                            │                          │
                                            │  ── 자율적으로 도구 호출 ── │
                                            │  · calculator            │
                                            │  · range_check           │
                                            │  · Knowledge Base 검색   │
                                            └───────────┬──────────────┘
                                                        │
                                    ┌───────────────────┼───────────────────┐
                                    ▼                   ▼                   ▼
                            [dynamo_save]      [inventory_check]     [create_order]
                                    │                   │                   │
                                    ▼                   ▼                   ▼
                            [DynamoDB]          (재고 조회)          (발주서 PDF)
                                    │
                          DANGER 판정 시
                                    ▼
                              [Amazon SNS]
                            (이메일 알림)

                                    │
                                    ▼
                    [API Gateway] ──▶ [dashboard_data] ──▶ [웹 대시보드]
                                              ▲
                                    [refresh] ─┘ (수동 새로고침)
```

### AWS 서비스 구성

| 서비스 | 역할 |
|--------|------|
| Amazon Bedrock (Agent + Knowledge Base) | 자율 진단 오케스트레이션, RAG 검색 |
| AWS Lambda | 8종의 Action Group / 데이터 파이프라인 실행 |
| Amazon DynamoDB | 분석 결과·재고·발주 데이터 저장 |
| Amazon S3 | 센서 원본 데이터, Knowledge Base 원본 문서 저장 |
| Amazon EventBridge | 10분 주기 자동 트리거 |
| Amazon SNS | DANGER 판정 시 이메일 알림 발송 |
| Amazon API Gateway | 대시보드-백엔드 연동 REST API |
| AWS IAM | Lambda·Agent 최소 권한 정책 |
| Amazon CloudWatch | Lambda 로그 및 Agent trace 모니터링 |

---

## 5. 프로젝트 결과 및 시연

### 구현 결과

- Bedrock Agent가 calculator/range_check/Knowledge Base를 상황에 따라 자율적으로 호출하여 고장 유형과 위험도를 판정하는 워크플로우 구현 완료
- 단일 고장뿐 아니라 복합 고장(예: PWF+OSF 동시 발생)도 정확히 탐지
- 판정부터 DynamoDB 저장, SNS 알림, 재고 확인, 발주서 생성까지 전 과정 자동화 확인
- 대시보드에서 설비 현황 조회, 발주 승인/거절, 수동 새로고침 기능 정상 동작 확인

### 주요 화면

- 관리자 로그인 화면
- 설비 현황 대시보드 (정상/이상 설비 분리 조회, 설비별 센서 추이)
- 발주 승인/거절 화면 및 발주서 PDF
- 긴급 알림 이메일 (예: `[긴급] FAC-005 장비 중대한 위험 발견`)

### 시연 영상

`docs/` 폴더 내 시연 영상 링크 참고 (별도 첨부)

### 테스트 결과

정상, 단일 고장, 복합 고장 등 총 8개 시나리오를 전수 테스트하여 전부 기대값과 일치함을 확인했습니다.

예시 (FAC-004, L등급, torque 65.7Nm, tool_wear 191min 입력 시):

1. `calculator`를 3회 호출하여 전력 9.70kW, Strain 12,548, 온도차 10.1K를 정밀 계산
2. 전력 9.70kW가 임계값 9.0kW를 초과 → PWF(전력 고장) 판정
3. Strain 12,548이 L등급 임계값 11,000을 초과 → OSF(과부하 고장) 동시 판정
4. Knowledge Base 검색으로 과거 유사 사례(동일 유형 복합 고장 이력) 확인
5. 위험도 88, DANGER로 최종 판정, 필요 부품 PW-303 / OS-404 지정
6. `dynamo_save`로 결과 저장, `inventory_check`로 재고 확인(PW-303 재고 1개, OS-404 재고 0개) → OS-404만 발주 필요로 판단

센서 수신부터 재고 확인까지 모든 단계를 Agent가 자율적으로 수행했으며, 사람의 개입 없이 전 과정이 완료되었습니다.

---

## 6. 기대 효과 및 향후 계획

### 기대 효과

- 고장 대응 시간을 수 시간에서 수 분으로 단축
- 전문 인력 의존도를 낮춰 비숙련자도 AI 권고 기반 대응 가능
- 서버리스 구조로 인프라 도입·운영 비용 최소화
- 복합 고장 탐지와 RAG 교차 검증으로 정비 정확도 향상

### 한계점

- 고장 판정 로직이 규칙(임계값) 기반이라 학습 기반 예측 대비 정밀도에 한계
- 단일 데이터셋(AI4I 2020) 기반으로 검증되어 실제 현장 데이터와의 차이 존재 가능
- 재고/발주 처리가 조건 분기 로직에 의존
- 10분 주기 배치 방식으로 실시간성에 제한

### 고도화 계획

1. **SageMaker ML 모델 도입** — 규칙 기반 진단을 데이터 학습 기반 이상 탐지로 전환
2. **Kinesis Data Streams 도입** — 배치 방식에서 실시간 스트리밍 처리로 전환
3. **재고/발주 로직 분리** — Agent와 재고·발주 처리 책임을 분리해 역할 명확화
4. **Bedrock Guardrails 적용** — Human-in-the-loop 강화로 안전성 확보

### 확장 가능성

- 멀티모달 진단 (이미지·음향 데이터 결합)
- 제조업 외 다른 산업 도메인으로 확장
- 서버리스 구조를 활용한 설비 수 확장 (5대 → N대)
- 시계열 데이터 축적 후 고장 확률 예측 모델로 발전

---

## 브랜치 전략

- `main`: 최종 완성본
- `soyoung`: 허소영
- `suhee`: 임수희
- `jaewoo`: 손재우
- `agent`: Agentic 아키텍처 전환 작업 브랜치

## 시작하기

```bash
cp .env.example .env
# .env에 값 입력 후 개발 시작
```

## 주의사항

- `.env` 파일 절대 커밋 금지

## 참고 자료

- AI4I 2020 Dataset: https://archive.ics.uci.edu/dataset/601
- Bedrock Agents: https://docs.aws.amazon.com/bedrock/latest/userguide/agents.html
