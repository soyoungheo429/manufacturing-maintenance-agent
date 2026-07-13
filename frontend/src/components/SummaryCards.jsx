// [SummaryCards] 설비 현황 요약 — 역할분담서 Step 7 스펙
// 전체 설비(파랑) / 위험 설비(빨강) / 탐지(주황) / 미처리 발주(초록)
export default function SummaryCards({ total, criticalCount, detectedCount, pendingOrderCount }) {
  const cards = [
    { label: "전체 설비", value: total, dot: "bg-sky-400", text: "text-sky-400" },
    { label: "위험 설비", value: criticalCount, dot: "bg-red-400 animate-pulse", text: "text-red-400" },
    { label: "탐지", value: detectedCount, dot: "bg-amber-400", text: "text-amber-400" },
    { label: "미처리 발주", value: pendingOrderCount, dot: "bg-emerald-400", text: "text-emerald-400" },
  ];
  return (
    <div className="flex items-center gap-4 text-xs text-muted-foreground">
      {cards.map((c) => (
        <div key={c.label} className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${c.dot}`} />
          <span>
            {c.label} <span className={`font-mono font-semibold ${c.text}`}>{c.value}</span>
          </span>
        </div>
      ))}
    </div>
  );
}
