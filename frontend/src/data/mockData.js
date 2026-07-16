// MVP 목데이터 — dashboard_data Lambda 연동 전까지 사용
// 실제 연동 시 api/index.js의 getDashboardData()가 이 구조로 데이터를 내려줍니다.

export const equipmentData = [
  {
    id: "L47340",
    productType: "L",
    status: "critical",
    lastUpdated: "2026-07-09 14:23:07",
    sensors: { airTemp: 298.4, processTemp: 309.8, rotationSpeed: 1421, torque: 68.3, toolWear: 192 },
    faultAnalysis: {
      faults: ["OSF"],
      confidence: "high",
      diagnosis: "strain = tool_wear × torque = 13,113.6으로 Type L 임계값(11,000) 초과 → OSF 확정. 온도·회전속도 등 기타 파생 지표는 정상 범위.",
      derivedMetrics: [
        { label: "Strain", value: "13,113.6", unit: "Nm·min", alert: true },
        { label: "Power", value: "10.18", unit: "kW", alert: true },
        { label: "Temp Δ", value: "11.4", unit: "K" },
        { label: "OSF 임계값", value: "11,000", unit: "Nm·min" },
      ],
    },
    maintenanceRec: {
      similarCases: [
        { id: "CASE-2024-0821", date: "2024-08-21", description: "L형 설비 공구마모 과부하로 인한 OSF — 공구 즉시 교체 후 정상화" },
        { id: "CASE-2023-1103", date: "2023-11-03", description: "유사 strain 값에서 스핀들 베어링 손상 선행 발생" },
      ],
      recommendation: "즉시 가동 중단 후 절삭공구 교체 필요. 스핀들 베어링 상태 점검 병행 권고. 교체 후 브레이크인 사이클 실행.",
      parts: ["OS-404"],
    },
  },
  {
    id: "M52891",
    productType: "M",
    status: "critical",
    lastUpdated: "2026-07-09 14:21:44",
    sensors: { airTemp: 301.2, processTemp: 308.1, rotationSpeed: 2700, torque: 12.0, toolWear: 87 },
    faultAnalysis: {
      faults: ["PWF"],
      confidence: "high",
      diagnosis: "power = torque × rpm / 9549 = 3.39 kW로 정상 하한(3.5 kW) 미달 → PWF 확정. 전력 공급 불안정 또는 구동계 저항 증가 의심.",
      derivedMetrics: [
        { label: "Power", value: "3.39", unit: "kW", alert: true },
        { label: "Power 하한", value: "3.5", unit: "kW" },
        { label: "Strain", value: "1,044.0", unit: "Nm·min" },
        { label: "Temp Δ", value: "6.9", unit: "K" },
      ],
    },
    maintenanceRec: {
      similarCases: [
        { id: "CASE-2025-0214", date: "2025-02-14", description: "M형 전력 저하 — 전력 드라이버 열화 원인 확인, 드라이버 교체 후 정상화" },
      ],
      recommendation: "전력 계통 점검 우선 시행. 전력 드라이버 출력 전압/전류 파형 측정. 이상 지속 시 구동 모터 절연저항 측정 및 교체 검토.",
      parts: ["PW-303"],
    },
  },
  {
    id: "H31204",
    productType: "H",
    status: "critical",
    lastUpdated: "2026-07-09 14:20:11",
    sensors: { airTemp: 296.7, processTemp: 303.9, rotationSpeed: 1198, torque: 74.1, toolWear: 218 },
    faultAnalysis: {
      faults: ["HDF", "TWF"],
      confidence: "high",
      diagnosis: "공정온도-대기온도 차 7.2K < 임계값 8.6K, 회전속도 1,198 rpm < 1,380 rpm 동시 충족 → HDF 확정. 공구마모 218 min으로 주의 관찰 구간(200~240 min) 진입 → TWF 약한 신호 동반 감지.",
      derivedMetrics: [
        { label: "Temp Δ", value: "7.2", unit: "K", alert: true },
        { label: "Temp 임계값", value: "8.6", unit: "K" },
        { label: "Tool Wear", value: "218", unit: "min", alert: true },
        { label: "TWF 주의 구간", value: "200~240", unit: "min" },
        { label: "Power", value: "9.32", unit: "kW" },
      ],
    },
    maintenanceRec: {
      similarCases: [
        { id: "CASE-2025-0609", date: "2025-06-09", description: "H형 열분산 실패 — 냉각팬 정지 및 방열판 분진 퇴적, 팬·방열판 교체 후 정상화" },
        { id: "CASE-2024-1201", date: "2024-12-01", description: "HDF+TWF 복합 발생, 가동 중단 없이 방치하여 주축 손상까지 진행됨" },
      ],
      recommendation: "즉시 가동 중단. 냉각팬·방열판·냉각수 펌프 점검 및 교체. 공구마모 주의 구간 진입으로 절삭공구 예방 교체 병행 권고. 재가동 전 열화상 점검 필수.",
      parts: ["HD-202", "TW-101"],
    },
  },
  {
    id: "L89012",
    productType: "L",
    status: "warning",
    lastUpdated: "2026-07-09 14:18:33",
    sensors: { airTemp: 299.1, processTemp: 309.4, rotationSpeed: 1876, torque: 42.7, toolWear: 178 },
    faultAnalysis: {
      faults: ["TWF"],
      confidence: "medium",
      diagnosis: "공구마모 178 min으로 Type L 임계값(200 min)의 89% 수준. 약한 TWF 신호 감지. 즉시 교체는 불필요하나 예방점검 시점 도달.",
      derivedMetrics: [
        { label: "Tool Wear", value: "178", unit: "min", alert: false },
        { label: "TWF 임계값", value: "200", unit: "min" },
        { label: "잔여 수명", value: "~11%", unit: "" },
        { label: "Power", value: "8.40", unit: "kW" },
        { label: "Strain", value: "7,600.6", unit: "Nm·min" },
      ],
    },
    maintenanceRec: {
      similarCases: [],
      recommendation: "다음 정기보전 시 절삭공구 교체 스케줄링 권고. 현재 가동 유지 가능. 마모 진행 속도 모니터링 강화.",
      parts: ["TW-101"],
    },
  },
  {
    id: "M23456",
    productType: "M",
    status: "normal",
    lastUpdated: "2026-07-09 14:17:05",
    sensors: { airTemp: 297.8, processTemp: 309.2, rotationSpeed: 2241, torque: 28.4, toolWear: 52 },
    faultAnalysis: {
      faults: [],
      confidence: "high",
      diagnosis: "모든 센서값 정상 범위 이내. 파생 지표 이상 없음.",
      derivedMetrics: [
        { label: "Power", value: "6.66", unit: "kW" },
        { label: "Strain", value: "1,476.8", unit: "Nm·min" },
        { label: "Temp Δ", value: "11.4", unit: "K" },
      ],
    },
    maintenanceRec: {
      similarCases: [],
      recommendation: "정상 운전 중. 다음 정기보전일 준수.",
      parts: [],
    },
  },
  {
    id: "H78901",
    productType: "H",
    status: "normal",
    lastUpdated: "2026-07-09 14:16:22",
    sensors: { airTemp: 300.3, processTemp: 311.1, rotationSpeed: 1654, torque: 55.2, toolWear: 93 },
    faultAnalysis: {
      faults: [],
      confidence: "high",
      diagnosis: "모든 센서값 정상 범위 이내. 파생 지표 이상 없음.",
      derivedMetrics: [
        { label: "Power", value: "9.57", unit: "kW" },
        { label: "Strain", value: "5,133.6", unit: "Nm·min" },
        { label: "Temp Δ", value: "10.8", unit: "K" },
      ],
    },
    maintenanceRec: {
      similarCases: [],
      recommendation: "정상 운전 중. 다음 정기보전일 준수.",
      parts: [],
    },
  },
  {
    id: "L45678",
    productType: "L",
    status: "normal",
    lastUpdated: "2026-07-09 14:15:48",
    sensors: { airTemp: 295.9, processTemp: 307.3, rotationSpeed: 2589, torque: 18.7, toolWear: 31 },
    faultAnalysis: {
      faults: [],
      confidence: "high",
      diagnosis: "모든 센서값 정상 범위 이내. 파생 지표 이상 없음.",
      derivedMetrics: [
        { label: "Power", value: "5.08", unit: "kW" },
        { label: "Strain", value: "579.7", unit: "Nm·min" },
        { label: "Temp Δ", value: "11.4", unit: "K" },
      ],
    },
    maintenanceRec: {
      similarCases: [],
      recommendation: "정상 운전 중. 다음 정기보전일 준수.",
      parts: [],
    },
  },
];

// 확진(critical) 설비 3대의 부품을 병합한 통합 발주서 — 실제 연동 시 create_order Lambda가 생성
export const consolidatedOrderData = {
  id: "PO-2026-4721",
  createdAt: "2026-07-09 14:23:41",
  // 설비별 승인 상태 — 승인된 설비의 라인만 최종 발주서(PDF)에 포함
  decisions: { L47340: "pending", M52891: "pending", H31204: "pending" },
  lines: [
    // 매뉴얼 기준 고장 유형별 부품 1종: OSF→OS-404, PWF→PW-303, HDF→HD-202, TWF→TW-101
    { equipmentId: "L47340", part: "OS-404", qty: 1 }, // OSF
    { equipmentId: "M52891", part: "PW-303", qty: 1 }, // PWF
    { equipmentId: "H31204", part: "HD-202", qty: 1 }, // HDF
    // TWF 동반 신호 → 예방 교체분은 참고용 기재 (requires_purchase_order=false)
    { equipmentId: "H31204", part: "TW-101", qty: 1, referenceOnly: true },
  ],
};
