// [FacilityHeatmap] 설비별 상태 목록 — 역할분담서 Step 7 스펙
// 설비별 위험도를 색상(🔴 확정 고장 / 🟡 예방점검 / 🟢 정상)으로 표시하는 사이드바
import { ChevronRight, Search, X } from "lucide-react";
import { STATUS_CONFIG } from "../constants.js";
import { StatusBadge, FaultTag } from "./badges.jsx";

function EquipmentCard({ eq, selected, onClick }) {
  const cfg = STATUS_CONFIG[eq.status];
  return (
    <button
      onClick={onClick}
      className={`w-full text-left p-3.5 rounded-lg border transition-all duration-150 group ${
        selected
          ? `${cfg.bg} ${cfg.border} ring-1 ${
              eq.status === "critical"
                ? "ring-red-500/30"
                : eq.status === "warning"
                ? "ring-amber-500/30"
                : "ring-emerald-500/30"
            }`
          : "bg-card border-border hover:border-white/15 hover:bg-white/[0.03]"
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span
            className={`w-2 h-2 rounded-full flex-shrink-0 ${cfg.dot} ${
              eq.status === "critical" ? "animate-pulse" : ""
            }`}
          />
          <span className="font-mono text-sm font-semibold text-foreground">{eq.id}</span>
          <span className="text-xs font-mono text-muted-foreground bg-white/5 px-1.5 py-0.5 rounded">
            Type {eq.productType}
          </span>
        </div>
        <ChevronRight
          size={14}
          className={`text-muted-foreground transition-transform ${selected ? "rotate-90 text-primary" : "group-hover:translate-x-0.5"}`}
        />
      </div>
      <div className="flex items-center gap-2 flex-wrap">
        <StatusBadge status={eq.status} />
        {eq.faultAnalysis.faults.map((f) => (
          <FaultTag key={f} type={f} />
        ))}
      </div>
    </button>
  );
}

export default function FacilityHeatmap({
  activeTab,
  onTabChange,
  searchQuery,
  onSearchChange,
  displayList,
  anomalyCount,
  totalCount,
  selectedId,
  onSelect,
}) {
  return (
    <aside className="flex-shrink-0 w-72 flex flex-col border-r border-border bg-card/30">
      {/* Tabs */}
      <div className="flex border-b border-border">
        <button
          onClick={() => onTabChange("anomaly")}
          className={`flex-1 py-3 text-xs font-semibold transition-colors relative ${
            activeTab === "anomaly" ? "text-foreground" : "text-muted-foreground hover:text-foreground"
          }`}
        >
          이상 설비
          <span
            className={`ml-1.5 inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-mono font-bold ${
              activeTab === "anomaly" ? "bg-red-500/20 text-red-400" : "bg-white/5 text-muted-foreground"
            }`}
          >
            {anomalyCount}
          </span>
          {activeTab === "anomaly" && (
            <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary rounded-full" />
          )}
        </button>
        <button
          onClick={() => onTabChange("all")}
          className={`flex-1 py-3 text-xs font-semibold transition-colors relative ${
            activeTab === "all" ? "text-foreground" : "text-muted-foreground hover:text-foreground"
          }`}
        >
          전체 설비
          <span
            className={`ml-1.5 inline-flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-mono font-bold ${
              activeTab === "all" ? "bg-primary/20 text-primary" : "bg-white/5 text-muted-foreground"
            }`}
          >
            {totalCount}
          </span>
          {activeTab === "all" && (
            <span className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary rounded-full" />
          )}
        </button>
      </div>

      {/* Search */}
      <div className="px-3 py-2.5 border-b border-border">
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground pointer-events-none" />
          <input
            type="text"
            placeholder="설비 ID 검색..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full bg-white/5 border border-border rounded-lg pl-8 pr-8 py-2 text-xs font-mono text-foreground placeholder:text-muted-foreground focus:outline-none focus:border-primary/50 focus:bg-white/8 transition-colors"
          />
          {searchQuery && (
            <button
              onClick={() => onSearchChange("")}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
            >
              <X size={12} />
            </button>
          )}
        </div>
        {searchQuery && (
          <p className="text-[10px] text-muted-foreground mt-1.5 font-mono">
            {displayList.length}개 결과
          </p>
        )}
      </div>

      {/* Equipment List */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2" style={{ scrollbarWidth: "none" }}>
        {displayList.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-32 text-center gap-1">
            <Search size={20} className="text-muted-foreground/40 mb-1" />
            <p className="text-xs text-muted-foreground">
              {searchQuery ? `"${searchQuery}" 검색 결과 없음` : "이상 설비 없음"}
            </p>
          </div>
        ) : (
          displayList.map((eq) => (
            <EquipmentCard
              key={eq.id}
              eq={eq}
              selected={selectedId === eq.id}
              onClick={() => onSelect(eq.id)}
            />
          ))
        )}
      </div>
    </aside>
  );
}
