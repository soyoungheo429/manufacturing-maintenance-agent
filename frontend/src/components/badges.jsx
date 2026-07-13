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
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-mono font-semibold ${FAULT_COLORS[type]}`}>
      {type}
    </span>
  );
}
