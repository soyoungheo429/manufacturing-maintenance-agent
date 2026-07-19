// 공용 소형 배지 — 설비 상태 배지, 고장 유형 태그
import { STATUS_CONFIG, FAULT_COLORS } from "../constants.js";

export function StatusBadge({ status }) {
  const cfg = STATUS_CONFIG[status];
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-medium ${cfg.badge}`}>
      <Icon size={11} />
      {cfg.label}
    </span>
  );
}

export function FaultTag({ type }) {
  // NORMAL은 고장 유형이 아니므로 배지를 렌더링하지 않음
  // (구버전 백엔드가 faults에 "NORMAL"을 그대로 내려보내는 경우 방어)
  if (!type || String(type).toUpperCase() === "NORMAL") return null;
  // 미등록 유형(예: 콤마 결합 "PWF,OSF"가 그대로 내려온 경우)도 색상이 비지 않도록 폴백
  const cls = FAULT_COLORS[type] ?? "bg-red-500/20 text-red-300 border border-red-500/30";
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-mono font-semibold ${cls}`}>
      {type}
    </span>
  );
}
