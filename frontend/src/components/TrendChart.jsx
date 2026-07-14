// 센서 시계열 차트 — 최근 60분(10분 주기 폴링) 추이 + 주의/이탈 임계선
import { useMemo, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { SENSOR_RANGES, buildHistory } from "../constants.js";

export default function TrendChart({ eq }) {
  const [metric, setMetric] = useState("toolWear");
  const r = SENSOR_RANGES[metric];
  const data = useMemo(() => buildHistory(eq, metric), [eq, metric]);
  const current = eq.sensors[metric];
  const isAlert = current < r.min || current > r.max;
  const isWarn = !isAlert && r.warn !== undefined && current > r.warn;
  const lineColor = isAlert ? "#f87171" : isWarn ? "#fbbf24" : "#38bdf8";
  const pad = (r.max - r.min) * 0.12;

  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <div className="flex items-center gap-2 flex-wrap mb-4">
        {Object.keys(SENSOR_RANGES).map((key) => (
          <button
            key={key}
            onClick={() => setMetric(key)}
            className={`px-2.5 py-1 rounded-md text-xs font-mono border transition-colors ${
              metric === key
                ? "bg-primary/15 border-primary/40 text-primary"
                : "bg-white/5 border-border text-muted-foreground hover:text-foreground"
            }`}
          >
            {SENSOR_RANGES[key].label}
          </button>
        ))}
        <span className="ml-auto text-[10px] text-muted-foreground font-mono">
          최근 60분 · 10분 주기 폴링
        </span>
      </div>
      <div className="h-44">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 5, right: 10, bottom: 0, left: -10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
            <XAxis
              dataKey="time"
              tick={{ fontSize: 10, fill: "rgba(148,163,184,0.7)", fontFamily: "monospace" }}
              axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
              tickLine={false}
            />
            <YAxis
              domain={[Math.max(0, Math.floor(r.min - pad)), Math.ceil(r.max + pad)]}
              tick={{ fontSize: 10, fill: "rgba(148,163,184,0.7)", fontFamily: "monospace" }}
              axisLine={false}
              tickLine={false}
            />
            <Tooltip
              contentStyle={{
                background: "#0f172a",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: 8,
                fontSize: 11,
                fontFamily: "monospace",
              }}
              labelStyle={{ color: "#94a3b8" }}
              formatter={(v) => [`${v} ${r.unit}`, r.label]}
            />
            {r.warn !== undefined && (
              <ReferenceLine y={r.warn} stroke="#fbbf24" strokeDasharray="4 4" strokeOpacity={0.5} />
            )}
            <ReferenceLine y={r.max} stroke="#f87171" strokeDasharray="4 4" strokeOpacity={0.5} />
            <Line
              type="monotone"
              dataKey="value"
              stroke={lineColor}
              strokeWidth={2}
              dot={{ r: 3, fill: lineColor, strokeWidth: 0 }}
              activeDot={{ r: 4 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
