// 예지보전 통합 웹 대시보드 — 메인 레이아웃/상태 관리
// 화면 구성: 로그인 → [설비 모니터링(사이드바+상세) | 통합 발주서] 탭 전환
import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, Gauge, LogOut, User } from "lucide-react";
import {
  AUTH_STORAGE_KEY,
  MANUAL_REFRESH_COOLDOWN_SEC,
  ROLE_CONFIG,
  formatTimestamp,
} from "./constants.js";
import { equipmentData, consolidatedOrderData } from "./data/mockData.js";
import { getDashboardData } from "./api/index.js";
import LoginScreen from "./components/LoginScreen.jsx";
import SummaryCards from "./components/SummaryCards.jsx";
import FacilityHeatmap from "./components/FacilityHeatmap.jsx";
import RecommendationPanel from "./components/RecommendationPanel.jsx";
import ConsolidatedOrderView from "./components/OrderTable.jsx";
import RefreshButton from "./components/RefreshButton.jsx";

export default function App() {
  const [user, setUser] = useState(() => {
    try {
      return JSON.parse(sessionStorage.getItem(AUTH_STORAGE_KEY) ?? "null");
    } catch {
      return null;
    }
  });
  const [mainView, setMainView] = useState("dashboard"); // "dashboard" | "orders"
  const [activeTab, setActiveTab] = useState("anomaly");
  const [selectedId, setSelectedId] = useState("L47340");
  const [equipments, setEquipments] = useState(equipmentData);
  const [order, setOrder] = useState(consolidatedOrderData);
  const [searchQuery, setSearchQuery] = useState("");
  const [lastUpdated, setLastUpdated] = useState(() => formatTimestamp(new Date()));
  const [cooldownUntil, setCooldownUntil] = useState(null);
  const [cooldownRemaining, setCooldownRemaining] = useState(0);
  const [dataSource, setDataSource] = useState("mock");
  const [refreshing, setRefreshing] = useState(false);
  // 자동 갱신 스케줄 추적(마지막 실행된 10분 슬롯) — 수동 쿨다운과 완전히 독립
  const lastAutoSlotRef = useRef(null);

  // VITE_API_GATEWAY_URL 설정 시 GET /dashboard 조회, 미설정/실패 시 목데이터 유지
  const refreshData = useCallback(async () => {
    setRefreshing(true);
    try {
      const data = await getDashboardData();
      if (data) {
        // dashboard_data Lambda 응답 매핑 지점 — 백엔드 스키마 확정 시 여기만 수정
        if (data.equipments) setEquipments(data.equipments);
        if (data.order) setOrder(data.order);
        setDataSource("live");
      }
    } catch (err) {
      console.warn("API Gateway 조회 실패 — 기존 데이터 유지:", err);
      setDataSource("mock");
    } finally {
      setLastUpdated(formatTimestamp(new Date()));
      setRefreshing(false);
    }
  }, []);

  // 자동 갱신: 매시 0/10/20/30/40/50분 고정 스케줄에서만 실행
  useEffect(() => {
    const checkSchedule = () => {
      const now = new Date();
      if (now.getMinutes() % 10 !== 0) return;
      const slot = Math.floor(now.getTime() / 60000); // 분 단위 슬롯 — 같은 분 중복 실행 방지
      if (lastAutoSlotRef.current === slot) return;
      lastAutoSlotRef.current = slot;
      refreshData();
    };
    checkSchedule();
    const timer = setInterval(checkSchedule, 5000);
    return () => clearInterval(timer);
  }, [refreshData]);

  // 수동 새로고침 쿨다운 (자동 스케줄에는 영향 없음)
  // 마감 시각(wall-clock) 기준으로 계산해 백그라운드 탭 타이머 스로틀링에도 정확
  useEffect(() => {
    if (cooldownUntil === null) return;
    const tick = () => {
      const remaining = Math.max(0, Math.ceil((cooldownUntil - Date.now()) / 1000));
      setCooldownRemaining(remaining);
      if (remaining <= 0) setCooldownUntil(null);
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, [cooldownUntil]);

  const handleManualRefresh = () => {
    if (cooldownRemaining > 0) return;
    refreshData();
    setCooldownUntil(Date.now() + MANUAL_REFRESH_COOLDOWN_SEC * 1000);
  };

  const anomalyList = equipments.filter((e) => e.status !== "normal");
  const allList = [...equipments].sort((a, b) => {
    const rank = { critical: 0, warning: 1, normal: 2 };
    return rank[a.status] - rank[b.status];
  });

  const baseList = activeTab === "anomaly" ? anomalyList : allList;
  const displayList = searchQuery.trim()
    ? baseList.filter((e) => e.id.toLowerCase().includes(searchQuery.trim().toLowerCase()))
    : baseList;
  const selectedEq = equipments.find((e) => e.id === selectedId) ?? null;
  const orderEquipmentIds = [...new Set(order.lines.map((l) => l.equipmentId))];
  const pendingOrderCount = orderEquipmentIds.filter(
    (id) => (order.decisions[id] ?? "pending") === "pending"
  ).length;

  const handleOrderAction = (equipmentId, action) => {
    setOrder((prev) => ({
      ...prev,
      decisions: { ...prev.decisions, [equipmentId]: action },
    }));
  };

  const handleLogin = (u) => {
    sessionStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(u));
    setUser(u);
  };

  const handleLogout = () => {
    sessionStorage.removeItem(AUTH_STORAGE_KEY);
    setUser(null);
  };

  if (!user) {
    return <LoginScreen onLogin={handleLogin} />;
  }

  return (
    <div className="size-full flex flex-col bg-background" style={{ fontFamily: "'Inter', sans-serif" }}>
      {/* Header */}
      <header className="flex-shrink-0 h-14 flex items-center justify-between px-6 border-b border-border bg-card/60 backdrop-blur-sm">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-lg bg-primary/20 border border-primary/30 flex items-center justify-center">
            <Activity size={14} className="text-primary" />
          </div>
          <div>
            <h1 className="text-sm font-semibold text-foreground leading-none">
              예지보전 모니터링 시스템
            </h1>
            <span className="text-[10px] text-muted-foreground font-mono">
              Predictive Maintenance Dashboard
            </span>
          </div>
          <div className="flex items-center gap-1 bg-white/5 rounded-lg p-0.5 ml-2">
            <button
              onClick={() => setMainView("dashboard")}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${
                mainView === "dashboard"
                  ? "bg-primary/20 text-primary"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              설비 모니터링
            </button>
            <button
              onClick={() => setMainView("orders")}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-colors ${
                mainView === "orders"
                  ? "bg-primary/20 text-primary"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              통합 발주서
              {pendingOrderCount > 0 && (
                <span
                  className={`inline-flex items-center justify-center w-4 h-4 rounded-full text-[9px] font-bold ${
                    mainView === "orders"
                      ? "bg-primary/30 text-primary"
                      : "bg-white/10 text-muted-foreground"
                  }`}
                >
                  {pendingOrderCount}
                </span>
              )}
            </button>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <SummaryCards
            total={equipments.length}
            criticalCount={equipments.filter((e) => e.status === "critical").length}
            detectedCount={anomalyList.length}
            pendingOrderCount={pendingOrderCount}
          />
          <div className="flex items-center gap-2 text-[11px] text-muted-foreground font-mono border-l border-border pl-4">
            <RefreshButton
              cooldownRemaining={cooldownRemaining}
              refreshing={refreshing}
              onClick={handleManualRefresh}
            />
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] font-bold border ${
                dataSource === "live"
                  ? "bg-emerald-500/15 text-emerald-400 border-emerald-500/30"
                  : "bg-slate-500/15 text-slate-400 border-slate-500/30"
              }`}
              title={
                dataSource === "live"
                  ? "API Gateway 연동 데이터"
                  : "목데이터 (VITE_API_GATEWAY_URL 미설정 또는 API 실패)"
              }
            >
              {dataSource === "live" ? "LIVE" : "MOCK"}
            </span>
            <span>마지막 업데이트: {lastUpdated}</span>
          </div>
          <div className="flex items-center gap-2 border-l border-border pl-4">
            <div className="flex items-center gap-1.5">
              <User size={13} className="text-muted-foreground" />
              <span className="text-xs font-mono text-foreground">{user.username}</span>
              <span
                className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${ROLE_CONFIG[user.role].cls}`}
              >
                {ROLE_CONFIG[user.role].label}
              </span>
            </div>
            <button
              onClick={handleLogout}
              title="로그아웃"
              className="flex items-center justify-center w-6 h-6 rounded-md text-muted-foreground hover:text-foreground hover:bg-white/5 transition-colors"
            >
              <LogOut size={12} />
            </button>
          </div>
        </div>
      </header>

      {mainView === "orders" ? (
        <div className="flex-1 min-h-0 overflow-y-auto" style={{ scrollbarWidth: "none" }}>
          <ConsolidatedOrderView
            order={order}
            canApprove={user.role === "admin"}
            onAction={handleOrderAction}
          />
        </div>
      ) : (
        <div className="flex flex-1 min-h-0">
          <FacilityHeatmap
            activeTab={activeTab}
            onTabChange={setActiveTab}
            searchQuery={searchQuery}
            onSearchChange={setSearchQuery}
            displayList={displayList}
            anomalyCount={anomalyList.length}
            totalCount={equipments.length}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />

          {/* Detail Panel */}
          <main className="flex-1 min-w-0 overflow-y-auto" style={{ scrollbarWidth: "none" }}>
            {selectedEq ? (
              <div className="p-6 max-w-4xl">
                <RecommendationPanel
                  eq={selectedEq}
                  order={order}
                  canApprove={user.role === "admin"}
                  onOrderAction={handleOrderAction}
                  onViewConsolidated={() => setMainView("orders")}
                />
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
                <div className="w-14 h-14 rounded-2xl bg-white/5 border border-border flex items-center justify-center mb-2">
                  <Gauge size={24} className="text-muted-foreground" />
                </div>
                <p className="text-sm font-medium text-muted-foreground">왼쪽에서 설비를 선택하세요</p>
                <p className="text-xs text-muted-foreground/60">설비 클릭 시 상세 진단 정보가 표시됩니다</p>
              </div>
            )}
          </main>
        </div>
      )}
    </div>
  );
}
