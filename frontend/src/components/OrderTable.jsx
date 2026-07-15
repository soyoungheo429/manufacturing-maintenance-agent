// [OrderTable] 발주 현황 — 역할분담서 Step 7 스펙
// 설비별 승인/거절 → 승인분(재고 부족분)만 통합 발주서 PDF에 포함
import { useRef, useState } from "react";
import { ChevronRight, Download, FileText, Info, Loader2, Lock, X } from "lucide-react";
import jsPDF from "jspdf";
// Tailwind v4의 oklch() 색상 함수를 지원하는 html2canvas 포크
import html2canvas from "html2canvas-pro";
import { ORDER_STATUS_CONFIG, PARTS_INVENTORY, getOrderQty } from "../constants.js";

// 부품 코드 우선 표기(다크 UI 행) — partId(부품 코드)가 있으면 코드를 강조(모노스페이스/주 텍스트)하고
// 품명을 작은 보조 텍스트로 표기. 코드가 없으면 기존처럼 품명만 표기한다.
function PartLabel({ line, className = "" }) {
  return <span className={className}>{line.partId || line.part}</span>;
}

// PDF eligibility is centralized so rows, totals, equipment IDs, and button counts stay aligned.
// Aggregate approved demand by PART CODE (not per-facility line) so a shared part's stock is
// subtracted once against the combined requirement across all approved facilities. This fixes the
// bug where the same stock was subtracted from every facility line independently, letting a shared
// short part vanish from the PDF (e.g. OS-404 needed by two facilities, stock 1 → each line 0).
export function buildOrderPdfGroups(order) {
  const approvedLines = order.lines.filter(
    (line) => order.decisions[line.equipmentId] === "approved" && !line.referenceOnly
  );

  const groups = new Map();
  for (const line of approvedLines) {
    const key = line.partId || line.part;
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(line);
  }

  return [...groups.entries()]
    .map(([key, lines]) => {
      const first = lines[0];
      const requiredQty = lines.reduce((sum, l) => sum + l.qty, 0);
      // Stock is per-part, so any line carrying a numeric backend stock is authoritative for the
      // whole group; otherwise fall back to the static inventory keyed by part code / name.
      const stockLine = lines.find((l) => typeof l.stock === "number");
      const stock = stockLine ? stockLine.stock : PARTS_INVENTORY[key] ?? 0;
      const orderQty = Math.max(0, requiredQty - stock);
      const facilities = [...new Set(lines.map((l) => l.equipmentId))].sort();
      return { key, partId: first.partId, part: first.part, requiredQty, stock, orderQty, facilities };
    })
    .filter((group) => group.orderQty > 0)
    .sort((a, b) => a.key.localeCompare(b.key));
}

// Union of all facilities across the included PDF groups (unique, sorted) — these are the
// facilities that transition to "ordered" once the PDF is successfully saved.
export function selectSavedFacilityIds(selectedLines) {
  return [...new Set(selectedLines.map((line) => line.equipmentId))];
}

export function finalizeSuccessfulPdfSave(onDownloaded, onClose, savedFacilityIds) {
  if (onDownloaded) onDownloaded(savedFacilityIds);
  if (onClose) onClose();
}

// 설비별 발주 승인/거절/되돌리기 액션 — 설비 상세 패널과 통합 발주서 탭에서 공용으로 사용
function OrderDecisionActions({ equipmentId, status, canApprove, onAction }) {
  if (status === "pending" && !canApprove) {
    return (
      <div className="flex items-center gap-2 text-xs text-muted-foreground bg-white/[0.03] border border-border rounded-lg px-3 py-2.5">
        <Lock size={12} className="flex-shrink-0" />
        발주 승인/거절은 관리자(admin) 권한입니다. 조회만 가능합니다.
      </div>
    );
  }
  if (status === "pending") {
    return (
      <div className="flex gap-3">
        <button
          onClick={() => onAction(equipmentId, "approved")}
          className="flex-1 py-2.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-white text-sm font-semibold transition-colors"
        >
          이 설비 발주 승인
        </button>
        <button
          onClick={() => onAction(equipmentId, "rejected")}
          className="flex-1 py-2.5 rounded-lg bg-red-500/20 hover:bg-red-500/30 text-red-400 border border-red-500/30 text-sm font-semibold transition-colors"
        >
          발주 제외 (거절)
        </button>
      </div>
    );
  }
  const isOrdered = status === "ordered";
  return (
    <div className="flex items-center gap-3">
      <div
        className={`flex-1 text-center text-sm font-semibold py-2 rounded-lg ${
          status === "approved"
            ? "bg-emerald-500/10 text-emerald-400"
            : isOrdered
            ? "bg-sky-500/10 text-sky-400"
            : "bg-red-500/10 text-red-400"
        }`}
      >
        {status === "approved"
          ? "✓ 발주 승인 완료"
          : isOrdered
          ? "✓ 발주 완료 · PDF 다운로드됨"
          : "✕ 발주에서 제외됨"}
      </div>
      {canApprove && (
        <button
          // 발주완료는 승인 상태로, 그 외(승인/거절)는 대기로 되돌림
          onClick={() => onAction(equipmentId, isOrdered ? "approved" : "pending")}
          className="px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 border border-border text-xs text-muted-foreground hover:text-foreground transition-colors whitespace-nowrap"
        >
          {isOrdered ? "발주 취소" : "대기로 되돌리기"}
        </button>
      )}
    </div>
  );
}

// 발주서 PDF 모달 — 승인된 설비의 재고 부족분만 포함
// 인쇄 대화상자 없이 html2canvas+jsPDF로 발주서 영역을 PDF 파일로 바로 다운로드
// 실제 연동 시 create_order Lambda가 생성한 PDF(S3 presigned URL) 다운로드로 교체
export function OrderPdfModal({ order, onClose, onDownloaded }) {
  const printRef = useRef(null);
  const [saving, setSaving] = useState(false);
  const groups = buildOrderPdfGroups(order);
  // Facilities to mark ordered = union of every included group's facilities (unique, sorted).
  const equipmentIds = [...new Set(groups.flatMap((g) => g.facilities))].sort();
  const totalQty = groups.reduce((sum, g) => sum + g.orderQty, 0);

  const handleSave = async () => {
    if (groups.length === 0 || !printRef.current || saving) return;
    const savedFacilityIds = equipmentIds;
    setSaving(true);
    try {
      // 발주서 영역을 캔버스로 렌더 → A4 PDF에 배치 (긴 문서는 여러 페이지로 분할)
      const canvas = await html2canvas(printRef.current, { scale: 2, backgroundColor: "#ffffff" });
      const imgData = canvas.toDataURL("image/png");
      const pdf = new jsPDF({ orientation: "portrait", unit: "mm", format: "a4" });
      const pageW = pdf.internal.pageSize.getWidth();
      const pageH = pdf.internal.pageSize.getHeight();
      const imgH = (canvas.height * pageW) / canvas.width;
      let heightLeft = imgH;
      let position = 0;
      pdf.addImage(imgData, "PNG", 0, position, pageW, imgH);
      heightLeft -= pageH;
      while (heightLeft > 0) {
        position -= pageH;
        pdf.addPage();
        pdf.addImage(imgData, "PNG", 0, position, pageW, imgH);
        heightLeft -= pageH;
      }
      pdf.save(`${order.id}.pdf`);
      // 저장과 완료 콜백이 모두 성공한 뒤 모달을 닫아 동일 스냅샷의 반복 저장을 막음
      finalizeSuccessfulPdfSave(onDownloaded, onClose, savedFacilityIds);
    } catch (err) {
      // 실패 시 완료 처리나 성공한 저장처럼 모달 닫기를 수행하지 않음
      console.error("PDF 저장 실패:", err);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6">
      <div className="w-full max-w-2xl max-h-full flex flex-col">
        <div className="flex items-center justify-end gap-2 mb-3">
          <button
            onClick={handleSave}
            disabled={saving || groups.length === 0}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-semibold transition-colors ${
              saving
                ? "bg-primary/10 text-primary/60 border-primary/20 cursor-wait"
                : groups.length === 0
                ? "bg-white/[0.02] border-border text-muted-foreground/50 cursor-not-allowed"
                : "bg-primary/20 hover:bg-primary/30 text-primary border-primary/30"
            }`}
          >
            {saving ? <Loader2 size={13} className="animate-spin" /> : <Download size={13} />}
            {saving ? "저장 중..." : "PDF 저장"}
          </button>
          <button
            onClick={onClose}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/15 text-slate-200 text-xs font-semibold transition-colors"
          >
            <X size={13} />
            닫기
          </button>
        </div>

        {groups.length === 0 && (
          <p className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-center text-xs font-semibold text-amber-300" role="status">
            새로 승인된 발주 대상이 없습니다.
          </p>
        )}

        <div ref={printRef} className="bg-white text-slate-900 rounded-lg shadow-2xl overflow-y-auto p-10">
          <div className="flex items-start justify-between pb-4 border-b-2 border-slate-800">
            <div>
              <h2 className="text-2xl font-bold tracking-tight">발 주 서</h2>
              <p className="text-xs text-slate-500 mt-1">Purchase Order — 예지보전 시스템 자동 생성</p>
            </div>
            <div className="text-right text-xs text-slate-600 font-mono space-y-0.5">
              <p>
                문서번호: <span className="font-semibold text-slate-900">{order.id}</span>
              </p>
              <p>발행일시: {order.createdAt}</p>
              <p>
                포함 설비: <span className="font-semibold">{equipmentIds.length}대 (승인 완료분)</span>
              </p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 py-4 text-xs border-b border-slate-200">
            <div>
              <p className="text-slate-500 mb-1">발주 사유</p>
              <p className="font-medium">
                Bedrock Agent 고장 확진 및 관리자 승인 완료 ({equipmentIds.join(", ")}) — 정비
                부품 통합 발주
              </p>
            </div>
            <div>
              <p className="text-slate-500 mb-1">요청 부서</p>
              <p className="font-medium">설비보전팀 (자동 생성 — create_order Lambda)</p>
            </div>
          </div>

          <table className="w-full mt-4 text-xs border-collapse">
            <thead>
              <tr className="bg-slate-100 text-slate-600">
                <th className="border border-slate-300 px-3 py-2 text-left font-semibold w-10">No</th>
                <th className="border border-slate-300 px-3 py-2 text-left font-semibold w-40">품명 / 규격</th>
                <th className="border border-slate-300 px-3 py-2 text-right font-semibold w-14">필요</th>
                <th className="border border-slate-300 px-3 py-2 text-right font-semibold w-14">재고</th>
                <th className="border border-slate-300 px-3 py-2 text-right font-semibold w-20 whitespace-nowrap">발주 수량</th>
                <th className="border border-slate-300 px-3 py-2 text-left font-semibold">대상 설비</th>
              </tr>
            </thead>
            <tbody>
              {groups.map((group, i) => (
                <tr key={group.key}>
                  <td className="border border-slate-300 px-3 py-2 text-slate-500">{i + 1}</td>
                  <td className="border border-slate-300 px-3 py-2">{group.partId || group.part}</td>
                  <td className="border border-slate-300 px-3 py-2 text-right font-mono">{group.requiredQty}</td>
                  <td className="border border-slate-300 px-3 py-2 text-right font-mono">{group.stock}</td>
                  <td className="border border-slate-300 px-3 py-2 text-right font-mono font-semibold">
                    {group.orderQty}
                  </td>
                  <td className="border border-slate-300 px-3 py-2 font-mono">{group.facilities.join(", ")}</td>
                </tr>
              ))}
              <tr className="bg-slate-50 font-semibold">
                <td className="border border-slate-300 px-3 py-2 text-right" colSpan={4}>
                  발주 합계
                </td>
                <td className="border border-slate-300 px-3 py-2 text-right font-mono">{totalQty}</td>
                <td className="border border-slate-300 px-3 py-2" />
              </tr>
            </tbody>
          </table>

          <p className="text-[10px] text-slate-500 mt-3 leading-relaxed">
            ※ 본 발주서는 AWS Bedrock Agent의 고장 확진 결과에 따라 자동 생성되었으며, 보유
            재고로 충당 가능한 품목은 발주 대상에서 자동 제외되었습니다(부족분만 발주). 단가 및
            공급업체 정보는 구매팀 확정 후 기입됩니다. 승인 이력은 DynamoDB 및 CloudTrail에
            기록됩니다.
          </p>

          <div className="grid grid-cols-2 gap-8 mt-8 pt-4 border-t border-slate-200 text-xs">
            <div>
              <p className="text-slate-500 mb-6">담당자 (설비보전팀)</p>
              <p className="border-b border-slate-400 pb-1 text-slate-400">(서명)</p>
            </div>
            <div>
              <p className="text-slate-500 mb-6">승인자 (관리자)</p>
              <p className="border-b border-slate-400 pb-1 text-slate-400">
                {equipmentIds.length > 0 ? "승인 완료 — Slack/대시보드" : "(서명)"}
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// 설비 상세 패널에 표시하는 스코프 — 이 설비에서 사용되는 부품 정보만 포함
export function EquipmentOrderPanel({ eq, order, canApprove, onAction, onViewConsolidated }) {
  const myLines = order.lines.filter((l) => l.equipmentId === eq.id);
  const myStatus = order.decisions[eq.id] ?? "pending";
  const myCfg = ORDER_STATUS_CONFIG[myStatus];
  const stockCoveredCount = myLines.filter((l) => !l.referenceOnly && getOrderQty(l) === 0).length;
  const referenceCount = myLines.filter((l) => l.referenceOnly).length;

  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="font-mono text-sm font-semibold text-foreground">{eq.id}</span>
            <span className="text-[10px] font-mono text-muted-foreground bg-white/5 px-1.5 py-0.5 rounded">
              발주 필요 부품
            </span>
          </div>
          <span className="text-xs text-muted-foreground font-mono">
            {myLines.length}개 품목 · 통합 발주서 {order.id}의 일부
          </span>
        </div>
        <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${myCfg.cls}`}>
          {myCfg.label}
        </span>
      </div>

      {/* Line items (이 설비 것만) */}
      <div className="rounded-lg border border-white/5 overflow-hidden mb-4">
        <div className="grid grid-cols-[1fr_40px_40px_48px] gap-2 px-3 py-2 bg-white/[0.04] text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
          <span>부품</span>
          <span className="text-right">필요</span>
          <span className="text-right">재고</span>
          <span className="text-right">발주</span>
        </div>
        {myLines.map((line) => {
          const stock =
            typeof line.stock === "number"
              ? line.stock
              : PARTS_INVENTORY[(line.partId && line.partId) || line.part] ?? 0;
          const orderQty = getOrderQty(line);
          return (
            <div
              key={line.partId ? `${line.partId}-${line.part}` : line.part}
              className="grid grid-cols-[1fr_40px_40px_48px] gap-2 px-3 py-2 text-xs font-mono border-t border-white/5 items-center text-slate-300"
            >
              <PartLabel line={line} />
              <span className="text-right">{line.qty}</span>
              <span className="text-right">{stock}</span>
              <span
                className={`text-right ${
                  line.referenceOnly
                    ? "text-slate-500"
                    : orderQty === 0
                    ? "text-emerald-400"
                    : "font-semibold text-foreground"
                }`}
              >
                {line.referenceOnly ? "참고" : orderQty === 0 ? "재고" : orderQty}
              </span>
            </div>
          );
        })}
      </div>
      {(stockCoveredCount > 0 || referenceCount > 0) && (
        <p className="text-[10px] text-muted-foreground mb-4 flex items-center gap-1.5">
          <Info size={11} className="flex-shrink-0" />
          재고로 충당 가능한 부품({stockCoveredCount}종)과 예방 교체 참고용 부품(
          {referenceCount}종, TWF 약한 신호)은 발주에서 자동 제외됩니다.
        </p>
      )}

      <OrderDecisionActions
        equipmentId={eq.id}
        status={myStatus}
        canApprove={canApprove}
        onAction={onAction}
      />

      <button
        onClick={onViewConsolidated}
        className="w-full mt-3 flex items-center justify-center gap-1.5 py-2 rounded-lg text-xs text-muted-foreground hover:text-primary hover:bg-white/5 transition-colors"
      >
        다른 설비 포함 통합 발주서 전체보기
        <ChevronRight size={12} />
      </button>
    </div>
  );
}

// 통합 발주서 탭의 설비 1대 카드 (진행 중 / 발주 완료 섹션 공용)
function EquipmentOrderCard({ eqId, order, canApprove, onAction }) {
  const lines = order.lines.filter((l) => l.equipmentId === eqId);
  const status = order.decisions[eqId] ?? "pending";
  const statusCfg = ORDER_STATUS_CONFIG[status];
  const dimmed = status === "rejected";
  return (
    <div className="bg-card border border-border rounded-xl p-5">
      <div className="flex items-center justify-between mb-3">
        <span className="font-mono text-sm font-semibold text-foreground">{eqId}</span>
        <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${statusCfg.cls}`}>
          {statusCfg.label}
        </span>
      </div>
      <div className="rounded-lg border border-white/5 overflow-hidden mb-4">
        <div className="grid grid-cols-[1fr_40px_40px_48px] gap-2 px-3 py-2 bg-white/[0.04] text-[10px] font-mono text-muted-foreground uppercase tracking-wider">
          <span>부품</span>
          <span className="text-right">필요</span>
          <span className="text-right">재고</span>
          <span className="text-right">발주</span>
        </div>
        {lines.map((line) => {
          const stock =
            typeof line.stock === "number"
              ? line.stock
              : PARTS_INVENTORY[(line.partId && line.partId) || line.part] ?? 0;
          const orderQty = getOrderQty(line);
          return (
            <div
              key={line.partId ? `${line.partId}-${line.part}` : line.part}
              className={`grid grid-cols-[1fr_40px_40px_48px] gap-2 px-3 py-2 text-xs font-mono border-t border-white/5 items-center ${
                dimmed ? "opacity-40" : "text-slate-300"
              }`}
            >
              <PartLabel line={line} className={dimmed ? "line-through" : ""} />
              <span className="text-right">{line.qty}</span>
              <span className="text-right">{stock}</span>
              <span
                className={`text-right ${
                  line.referenceOnly
                    ? "text-slate-500"
                    : orderQty === 0
                    ? "text-emerald-400"
                    : "font-semibold text-foreground"
                }`}
              >
                {line.referenceOnly ? "참고" : orderQty === 0 ? "재고" : orderQty}
              </span>
            </div>
          );
        })}
      </div>
      <OrderDecisionActions
        equipmentId={eqId}
        status={status}
        canApprove={canApprove}
        onAction={onAction}
      />
    </div>
  );
}

// 상단 "통합 발주서" 탭 전용 — 확진된 모든 설비의 부품을 한 화면에서 관리
export default function ConsolidatedOrderView({ order, canApprove, onAction, onMarkOrdered }) {
  const [showPdf, setShowPdf] = useState(false);
  const equipmentIds = [...new Set(order.lines.map((l) => l.equipmentId))];
  const statusOf = (id) => order.decisions[id] ?? "pending";

  const approvedCount = equipmentIds.filter((id) => statusOf(id) === "approved").length;
  const orderedCount = equipmentIds.filter((id) => statusOf(id) === "ordered").length;
  const rejectedCount = equipmentIds.filter((id) => statusOf(id) === "rejected").length;
  const pendingCount = equipmentIds.length - approvedCount - orderedCount - rejectedCount;

  // 진행 중(발주완료 아님) / 발주 완료 섹션 분리
  const activeIds = equipmentIds.filter((id) => statusOf(id) !== "ordered");
  const orderedIds = equipmentIds.filter((id) => statusOf(id) === "ordered");

  // PDF modal과 동일한 집계 결과를 버튼 활성/카운트에 사용 — 부품 코드 단위 그룹 수
  const orderGroups = buildOrderPdfGroups(order);
  const orderableLineCount = orderGroups.length;
  const stockCoveredCount = order.lines.filter(
    (l) => !l.referenceOnly && getOrderQty(l) === 0
  ).length;
  const referenceCount = order.lines.filter((l) => l.referenceOnly).length;

  return (
    <div className="p-6 max-w-4xl mx-auto flex flex-col gap-5">
      <div className="bg-card border border-border rounded-xl p-5">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <span className="font-mono text-lg font-semibold text-foreground">{order.id}</span>
            <span className="text-[10px] font-mono text-muted-foreground bg-white/5 px-1.5 py-0.5 rounded">
              통합 발주서
            </span>
          </div>
          <button
            onClick={() => setShowPdf(true)}
            disabled={orderableLineCount === 0}
            title={
              orderableLineCount === 0
                ? "승인된 설비가 없습니다 — 승인된 설비의 부품만 발주서에 포함됩니다"
                : "승인된 설비 부품으로 구성된 발주서 보기 · 다운로드 시 발주 완료 처리"
            }
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-semibold transition-colors ${
              orderableLineCount === 0
                ? "bg-white/[0.02] border-border text-muted-foreground/50 cursor-not-allowed"
                : "bg-white/5 hover:bg-white/10 border-border text-foreground"
            }`}
          >
            <FileText size={12} />
            발주서 PDF{orderableLineCount > 0 ? ` (${orderableLineCount})` : ""}
          </button>
        </div>
        {orderableLineCount === 0 && (
          <p className="mt-3 rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs font-semibold text-amber-300" role="status">
            새로 승인된 발주 대상이 없습니다.
          </p>
        )}
        <span className="text-xs text-muted-foreground font-mono">
          {equipmentIds.length}개 설비 · {order.lines.length}개 라인 · 생성 {order.createdAt}
        </span>
        <div className="flex items-center gap-1.5 text-[10px] font-mono mt-3 flex-wrap">
          <span className="px-1.5 py-1 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/25">
            승인 {approvedCount}
          </span>
          <span className="px-1.5 py-1 rounded bg-slate-500/15 text-slate-300 border border-slate-500/25">
            대기 {pendingCount}
          </span>
          <span className="px-1.5 py-1 rounded bg-red-500/15 text-red-400 border border-red-500/25">
            거절 {rejectedCount}
          </span>
          <span className="px-1.5 py-1 rounded bg-sky-500/15 text-sky-400 border border-sky-500/25">
            발주완료 {orderedCount}
          </span>
        </div>
        <p className="text-[10px] text-muted-foreground mt-3 flex items-center gap-1.5">
          <Info size={11} className="flex-shrink-0" />
          설비별로 승인/거절을 결정하며, 재고로 충당 가능한 부품({stockCoveredCount}종)과 예방
          교체 참고용 부품({referenceCount}종, TWF 약한 신호)은 발주에서 자동 제외됩니다. 발주서
          PDF를 다운로드하면 승인 설비가 "발주 완료"로 이동합니다.
        </p>
      </div>

      {/* 진행 중 섹션 */}
      {activeIds.length > 0 ? (
        activeIds.map((eqId) => (
          <EquipmentOrderCard
            key={eqId}
            eqId={eqId}
            order={order}
            canApprove={canApprove}
            onAction={onAction}
          />
        ))
      ) : (
        <div className="text-center text-xs text-muted-foreground py-6">
          진행 중인 발주 항목이 없습니다.
        </div>
      )}

      {/* 발주 완료 섹션 */}
      {orderedIds.length > 0 && (
        <div className="flex flex-col gap-5">
          <div className="flex items-center gap-2 mt-2">
            <span className="text-xs font-semibold text-sky-400 uppercase tracking-widest">
              발주 완료
            </span>
            <span className="text-[10px] font-mono text-sky-400/70 bg-sky-500/10 px-1.5 py-0.5 rounded">
              {orderedIds.length}
            </span>
            <div className="flex-1 h-px bg-border" />
          </div>
          {orderedIds.map((eqId) => (
            <EquipmentOrderCard
              key={eqId}
              eqId={eqId}
              order={order}
              canApprove={canApprove}
              onAction={onAction}
            />
          ))}
        </div>
      )}

      {showPdf && (
        <OrderPdfModal
          order={order}
          onClose={() => setShowPdf(false)}
          onDownloaded={onMarkOrdered}
        />
      )}
    </div>
  );
}
