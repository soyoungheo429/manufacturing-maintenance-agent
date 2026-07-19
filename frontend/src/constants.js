// 대시보드 전역 상수/유틸 — 판정 규칙, 색상 설정, 재고 계산 등
// 상태값 종류:
//   productType: "L" | "M" | "H"   faultType: "TWF" | "HDF" | "PWF" | "OSF" | "RNF"
//   status: "critical" | "warning" | "normal"   confidence: "high" | "medium" | "low"
//   orderStatus: "pending" | "approved" | "rejected"
import {
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Activity,
  Thermometer,
  Gauge,
  Timer,
} from "lucide-react";

export const MANUAL_REFRESH_COOLDOWN_SEC = 60;
export const AUTH_STORAGE_KEY = "pmd_auth";

// 부품 재고 현황 — 실제 연동 시 inventory_check Lambda가 DynamoDB parts-inventory 조회로 교체
// 정비 매뉴얼 기준 고장 유형별 부품: TWF→TW-101, HDF→HD-202, PWF→PW-303, OSF→OS-404
export const PARTS_INVENTORY = {
  "TW-101": 5, // 공구날 (예방 교체용, 재고 충분)
  "HD-202": 0, // 냉각장치 (재고 없음 → 발주)
  "PW-303": 1, // 전원장치 (재고 있음 → 충당)
  "OS-404": 0, // 베어링/과부하 (재고 없음 → 발주)
};

// 재고로 충당하고 남는 부족분만 발주 — 0이면 발주 불필요(재고 충당 또는 참고용)
export function getOrderQty(line) {
  if (line.referenceOnly) return 0;
  // Prefer the real parts-inventory stock attached by the backend (line.stock).
  // Fall back to the static PARTS_INVENTORY lookup — by part code first
  // (line.partId), then display name — for lines without a stock field.
  // Backward compatible: lines without stock behave exactly as before.
  const stock =
    typeof line.stock === "number"
      ? line.stock
      : PARTS_INVENTORY[(line.partId && line.partId) || line.part] ?? 0;
  return Math.max(0, line.qty - stock);
}

export const STATUS_CONFIG = {
  critical: {
    label: "확정 고장",
    bg: "bg-red-500/15",
    border: "border-red-500/40",
    text: "text-red-400",
    dot: "bg-red-400",
    badge: "bg-red-500/20 text-red-400 border border-red-500/30",
    icon: XCircle,
  },
  warning: {
    label: "예방점검 권고",
    bg: "bg-amber-500/15",
    border: "border-amber-500/40",
    text: "text-amber-400",
    dot: "bg-amber-400",
    badge: "bg-amber-500/20 text-amber-400 border border-amber-500/30",
    icon: AlertTriangle,
  },
  normal: {
    label: "정상",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/30",
    text: "text-emerald-400",
    dot: "bg-emerald-400",
    badge: "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30",
    icon: CheckCircle2,
  },
};

// 고장유형 배지 색상 — "확정 고장" 상태 배지와 동일한 빨강 계열로 통일
export const FAULT_COLORS = {
  TWF: "bg-red-500/20 text-red-300 border border-red-500/30",
  HDF: "bg-red-500/20 text-red-300 border border-red-500/30",
  PWF: "bg-red-500/20 text-red-300 border border-red-500/30",
  OSF: "bg-red-500/20 text-red-300 border border-red-500/30",
  RNF: "bg-red-500/20 text-red-300 border border-red-500/30",
};

export const CONFIDENCE_CONFIG = {
  high: { label: "HIGH", cls: "bg-red-500/20 text-red-400 border border-red-500/30" },
  medium: { label: "MEDIUM", cls: "bg-amber-500/20 text-amber-400 border border-amber-500/30" },
  low: { label: "LOW", cls: "bg-slate-500/20 text-slate-400 border border-slate-500/30" },
};

export const ORDER_STATUS_CONFIG = {
  pending: { label: "대기중", cls: "bg-slate-500/20 text-slate-300 border border-slate-500/30" },
  approved: { label: "승인", cls: "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30" },
  rejected: { label: "거절", cls: "bg-red-500/20 text-red-400 border border-red-500/30" },
  // 발주서 PDF 다운로드 완료 → "발주 완료" 섹션으로 이동
  ordered: { label: "발주완료", cls: "bg-sky-500/20 text-sky-400 border border-sky-500/30" },
};

export const SENSOR_RANGES = {
  airTemp: { min: 295, max: 304, label: "대기온도", unit: "K", icon: Thermometer },
  processTemp: { min: 305, max: 315, label: "공정온도", unit: "K", icon: Thermometer },
  rotationSpeed: { min: 1168, max: 2886, label: "회전속도", unit: "rpm", icon: Gauge },
  torque: { min: 3.8, max: 77, label: "토크", unit: "Nm", icon: Activity },
  // 200~240 min은 주의 관찰 구간(TWF 약한 신호), 240 초과부터 확정 이탈
  toolWear: { min: 0, warn: 200, max: 240, label: "공구마모", unit: "min", icon: Timer },
};

export const ROLE_CONFIG = {
  admin: { label: "관리자", cls: "bg-primary/15 text-primary border-primary/30" },
  operator: { label: "운영자", cls: "bg-slate-500/15 text-slate-300 border-slate-500/30" },
};

// ─── Bedrock Vision 목응답 ──────────────────────────────────────
export const VISION_TEXT = {
  OSF: "이미지에서 인서트 공구의 치핑 및 과도한 플랭크 마모가 관찰됩니다. 센서 1차 진단(OSF, 과부하)과 시각적 증거가 일치하여 고장으로 최종 확진합니다.",
  PWF: "스핀들 구동부 주변에서 그을음 흔적이 관찰됩니다. 센서 1차 진단(PWF, 전력 이상)과 부합하는 시각적 증거로 고장으로 최종 확진합니다.",
  HDF: "냉각 라인 주변 슬러지 퇴적 및 변색이 관찰됩니다. 센서 1차 진단(HDF, 방열 실패)과 일치하여 고장으로 최종 확진합니다.",
  TWF: "공구 날 부위에 마모 흔적이 관찰되나 파손 수준은 아닙니다. 센서 신호(TWF)와 종합하면 예방점검 권고 수준을 유지합니다.",
  RNF: "이미지 상 뚜렷한 이상 부위를 특정하기 어렵습니다. 정밀 점검을 권고합니다.",
};

export function mockVisionResult(eq) {
  const primary = eq.faultAnalysis.faults[0];
  if (!primary) {
    return {
      verdict: "clear",
      text: "업로드된 이미지에서 시각적 이상이 발견되지 않았습니다. 센서 데이터와 일치 — 정상 운전 유지.",
    };
  }
  if (eq.status === "warning") {
    return { verdict: "caution", text: VISION_TEXT[primary] };
  }
  return { verdict: "confirmed", text: VISION_TEXT[primary] };
}

export const VISION_VERDICT_CONFIG = {
  confirmed: {
    label: "고장 확진",
    cls: "bg-red-500/15 border-red-500/30 text-red-300",
    icon: XCircle,
  },
  caution: {
    label: "주의 관찰",
    cls: "bg-amber-500/15 border-amber-500/30 text-amber-300",
    icon: AlertTriangle,
  },
  clear: {
    label: "이상 없음",
    cls: "bg-emerald-500/15 border-emerald-500/30 text-emerald-300",
    icon: CheckCircle2,
  },
};

// ─── 시계열 목데이터 생성 (렌더마다 값이 바뀌지 않도록 설비 ID 기반 시드) ───
export function seededNoise(seed, i) {
  let h = 2166136261;
  const s = `${seed}:${i}`;
  for (let c = 0; c < s.length; c++) {
    h ^= s.charCodeAt(c);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 1000) / 1000 - 0.5;
}

export function buildHistory(eq, key) {
  const r = SENSOR_RANGES[key];
  const rawCurrent = eq.sensors ? eq.sensors[key] : undefined;
  const mid = (r.min + r.max) / 2;
  const span = r.max - r.min;
  // sensor_values가 비어 있거나 잘못된 경우 midpoint로 대체 — 차트가 평평한 선으로 렌더되도록 보장
  const hasValidCurrent =
    typeof rawCurrent === "number" && Number.isFinite(rawCurrent);
  const current = hasValidCurrent ? rawCurrent : mid;
  const points = [];
  for (let i = 0; i < 7; i++) {
    const t = i / 6;
    // 정상 중앙값 부근에서 출발해 현재값으로 수렴 — 이상 설비는 이탈 추세가 드러남
    const base = mid + (current - mid) * (0.4 + 0.6 * t);
    const noise = seededNoise(eq.id + key, i) * span * 0.04;
    const v = i === 6 ? current : base + noise;
    points.push({
      time: i === 6 ? "현재" : `-${(6 - i) * 10}분`,
      value: Number(
        (i === 6
          ? (typeof current === "number" && Number.isFinite(current) ? current : mid)
          : v
        ).toFixed(1)
      ),
    });
  }
  return points;
}

export function formatTimestamp(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(
    date.getHours()
  )}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}
