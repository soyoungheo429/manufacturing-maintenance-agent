// [RefreshButton] 수동 새로고침 + 1분 쿨다운 — 역할분담서 Step 7 스펙
// 쿨다운 상태 관리는 App(자동 갱신 스케줄과 공유)에서, 이 컴포넌트는 표시만 담당
import { RefreshCw } from "lucide-react";

export default function RefreshButton({ cooldownRemaining, refreshing, onClick }) {
  const disabled = cooldownRemaining > 0;
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={disabled ? `쿨다운 중 (${cooldownRemaining}초 남음)` : "지금 새로고침"}
      className={`flex items-center gap-1.5 px-2 py-1 rounded-md border transition-colors ${
        disabled
          ? "bg-white/5 border-border text-muted-foreground/50 cursor-not-allowed"
          : "bg-white/5 border-border text-foreground hover:border-primary/50 hover:text-primary"
      }`}
    >
      <RefreshCw size={11} className={refreshing ? "animate-spin" : ""} />
      <span>
        {refreshing ? "분석중" : disabled ? `${cooldownRemaining}초 후 가능` : "새로고침"}
      </span>
    </button>
  );
}
