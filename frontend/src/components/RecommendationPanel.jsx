// [RecommendationPanel] 설비 상세 + AI 권고 — 역할분담서 Step 7 스펙
// 센서값 / 시계열 / 고장 원인 분석 / RAG 정비 권고 / Vision 교차검증 / 이 설비 발주 부품
import {
  Activity,
  AlertTriangle,
  Clock,
  FileText,
  Info,
  Package,
  ScanSearch,
  ShieldAlert,
  TrendingUp,
  Wrench,
} from "lucide-react";
import { CONFIDENCE_CONFIG, SENSOR_RANGES, STATUS_CONFIG } from "../constants.js";
import { StatusBadge, FaultTag } from "./badges.jsx";
import TrendChart from "./TrendChart.jsx";
import VisionPanel from "./VisionPanel.jsx";
import { EquipmentOrderPanel } from "./OrderTable.jsx";

function SensorCard({ label, value, unit, min, max, warn, Icon }) {
  const isAlert = value < min || value > max;
  const isWarn = !isAlert && warn !== undefined && value > warn;
  const pct = Math.max(0, Math.min(100, ((value - min) / (max - min)) * 100));
  return (
    <div
      className={`p-4 rounded-lg border ${
        isAlert
          ? "bg-red-500/8 border-red-500/30"
          : isWarn
          ? "bg-amber-500/8 border-amber-500/30"
          : "bg-muted border-border"
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5">
          <Icon
            size={13}
            className={isAlert ? "text-red-400" : isWarn ? "text-amber-400" : "text-muted-foreground"}
          />
          <span className="text-xs text-muted-foreground">{label}</span>
        </div>
        {isAlert && (
          <span className="text-[10px] font-mono text-red-400 bg-red-500/15 px-1.5 py-0.5 rounded">
            범위 이탈
          </span>
        )}
        {isWarn && (
          <span className="text-[10px] font-mono text-amber-400 bg-amber-500/15 px-1.5 py-0.5 rounded">
            주의 구간
          </span>
        )}
      </div>
      <div
        className={`font-mono text-xl font-semibold leading-none ${
          isAlert ? "text-red-400" : isWarn ? "text-amber-400" : "text-foreground"
        }`}
      >
        {typeof value === "number" && value % 1 !== 0 ? value.toFixed(1) : value}
        <span className="text-xs font-normal text-muted-foreground ml-1">{unit}</span>
      </div>
      <div className="mt-3 h-1 rounded-full bg-white/5 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${
            isAlert ? "bg-red-500" : isWarn ? "bg-amber-500" : "bg-primary/60"
          }`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <div className="flex justify-between mt-1">
        <span className="text-[10px] text-muted-foreground font-mono">{min}</span>
        <span className="text-[10px] text-muted-foreground font-mono">{max}</span>
      </div>
    </div>
  );
}

export default function RecommendationPanel({ eq, order, canApprove, onOrderAction, onViewConsolidated }) {
  const cfg = STATUS_CONFIG[eq.status];
  const confCfg = CONFIDENCE_CONFIG[eq.faultAnalysis.confidence];

  return (
    <div className="flex flex-col gap-5">
      {/* Header */}
      <div className={`p-5 rounded-xl border ${cfg.bg} ${cfg.border}`}>
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-3 mb-1">
              <h2 className="font-mono text-2xl font-bold text-foreground">{eq.id}</h2>
              <span className="text-sm font-mono text-muted-foreground bg-white/5 border border-border px-2 py-0.5 rounded">
                Type {eq.productType}
              </span>
            </div>
            <div className="flex items-center gap-2 mt-2">
              <StatusBadge status={eq.status} />
            </div>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground mt-1">
            <Clock size={12} />
            <span className="font-mono">{eq.lastUpdated}</span>
          </div>
        </div>
      </div>

      {/* Sensor Values */}
      <section>
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-3 flex items-center gap-2">
          <Activity size={12} />
          현재 센서값
        </h3>
        <div className="grid grid-cols-2 xl:grid-cols-3 gap-3">
          {Object.keys(SENSOR_RANGES).map((key) => {
            const r = SENSOR_RANGES[key];
            return (
              <SensorCard
                key={key}
                label={r.label}
                value={eq.sensors[key]}
                unit={r.unit}
                min={r.min}
                max={r.max}
                warn={r.warn}
                Icon={r.icon}
              />
            );
          })}
        </div>
      </section>

      {/* Sensor Trend */}
      <section>
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-3 flex items-center gap-2">
          <TrendingUp size={12} />
          센서 추이 (시계열)
        </h3>
        <TrendChart eq={eq} />
      </section>

      {/* Fault Analysis */}
      <section>
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-3 flex items-center gap-2">
          <ShieldAlert size={12} />
          고장 원인 분석
        </h3>
        <div className="bg-card border border-border rounded-xl p-5 space-y-4">
          <div className="flex items-center gap-3 flex-wrap">
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">감지 유형</span>
              {eq.faultAnalysis.faults.length > 0 ? (
                eq.faultAnalysis.faults.map((f) => <FaultTag key={f} type={f} />)
              ) : (
                <span className="text-xs text-emerald-400 font-mono">이상 없음</span>
              )}
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-muted-foreground">신뢰도</span>
              <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${confCfg.cls}`}>
                {confCfg.label}
              </span>
            </div>
          </div>

          <div className="bg-white/[0.03] border border-white/5 rounded-lg p-3.5">
            <p className="text-sm text-slate-300 leading-relaxed font-mono">{eq.faultAnalysis.diagnosis}</p>
          </div>

          {eq.faultAnalysis.derivedMetrics.length > 0 && (
            <div>
              <span className="text-xs text-muted-foreground mb-2 block">파생 지표</span>
              <div className="grid grid-cols-2 gap-2">
                {eq.faultAnalysis.derivedMetrics.map((m) => (
                  <div
                    key={m.label}
                    className={`flex items-center justify-between px-3 py-2 rounded-lg border text-xs ${
                      m.alert
                        ? "bg-red-500/10 border-red-500/25 text-red-300"
                        : "bg-white/[0.03] border-white/5 text-slate-400"
                    }`}
                  >
                    <span className="font-mono">{m.label}</span>
                    <span className={`font-mono font-semibold ${m.alert ? "text-red-400" : "text-slate-200"}`}>
                      {m.value}
                      {m.unit && <span className="text-[10px] ml-1 opacity-70">{m.unit}</span>}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Maintenance Recommendation */}
      <section>
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-3 flex items-center gap-2">
          <Wrench size={12} />
          RAG 기반 정비 권고
        </h3>
        <div className="bg-card border border-border rounded-xl p-5 space-y-4">
          {eq.maintenanceRec.similarCases.length > 0 ? (
            <div>
              <span className="text-xs text-muted-foreground mb-2 block">유사 과거 사례</span>
              <div className="space-y-2">
                {eq.maintenanceRec.similarCases.map((c) => (
                  <div key={c.id} className="bg-white/[0.03] border border-white/5 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[10px] font-mono text-primary bg-primary/10 px-1.5 py-0.5 rounded">
                        {c.id}
                      </span>
                      <span className="text-[10px] font-mono text-muted-foreground">{c.date}</span>
                    </div>
                    <p className="text-xs text-slate-400 leading-relaxed">{c.description}</p>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2 text-xs text-muted-foreground bg-white/[0.02] border border-white/5 rounded-lg px-3 py-2.5">
              <Info size={12} />
              유사 사례 없음
            </div>
          )}

          <div>
            <span className="text-xs text-muted-foreground mb-2 block">권고 조치</span>
            <div className="bg-white/[0.03] border border-white/5 rounded-lg p-3.5">
              <p className="text-sm text-slate-300 leading-relaxed">{eq.maintenanceRec.recommendation}</p>
            </div>
          </div>

          {eq.maintenanceRec.parts.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5 mb-2">
                <Package size={11} className="text-muted-foreground" />
                <span className="text-xs text-muted-foreground">예상 필요 부품</span>
              </div>
              <div className="flex flex-wrap gap-2">
                {eq.maintenanceRec.parts.map((p) => (
                  <span
                    key={p}
                    className="text-xs font-mono px-2.5 py-1 rounded-full bg-primary/10 text-primary border border-primary/20"
                  >
                    {p}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      </section>

      {/* Bedrock Vision Cross-validation */}
      <section>
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-3 flex items-center gap-2">
          <ScanSearch size={12} />
          Bedrock Vision 교차 검증
        </h3>
        <VisionPanel key={eq.id} eq={eq} />
      </section>

      {/* Order / Action */}
      {eq.status === "warning" ? (
        <div className="bg-amber-500/8 border border-amber-500/25 rounded-xl p-5 flex items-start gap-3">
          <AlertTriangle size={16} className="text-amber-400 flex-shrink-0 mt-0.5" />
          <div>
            <p className="text-sm font-semibold text-amber-300 mb-1">예방 점검 권고</p>
            <p className="text-xs text-amber-400/80 leading-relaxed">
              현재 약한 고장 신호(TWF)만 감지되었습니다. 즉각적인 발주는 필요하지 않으나, 다음 정기보전 시 점검 일정을 반드시 확보하세요.
            </p>
          </div>
        </div>
      ) : eq.status === "critical" ? (
        <section>
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-widest mb-3 flex items-center gap-2">
            <FileText size={12} />
            발주 부품 정보
          </h3>
          <EquipmentOrderPanel
            eq={eq}
            order={order}
            canApprove={canApprove}
            onAction={onOrderAction}
            onViewConsolidated={onViewConsolidated}
          />
        </section>
      ) : null}
    </div>
  );
}
