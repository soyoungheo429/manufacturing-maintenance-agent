// [OrderTable] 발주 현황 — 역할분담서 Step 7 스펙
// 설비별 승인/거절 → 승인분(재고 부족분)만 통합 발주서 PDF에 포함
import { useRef, useState } from "react";
import { ChevronRight, Download, FileText, Info, Loader2, Lock, X } from "lucide-react";
import jsPDF from "jspdf";
// Tailwind v4의 oklch() 색상 함수를 지원하는 html2canvas 포크
import html2canvas from "html2canvas-pro";
import { ORDER_STATUS_CONFIG, PARTS_INVENTORY, getOrderQty } from "../constants.js";

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
  return (
    <div className="flex items-center gap-3">
      <div
        className={`flex-1 text-center text-sm font-semibold py-2 rounded-lg ${
          status === "approved" ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
        }`}
      >
        {status === "approved" ? "✓ 발주 승인 완료" : "✕ 발주에서 제외됨"}
      </div>
      {canApprove && (
        <button
          onClick={() => onAction(equipmentId, "pending")}
          className="px-3 py-2 rounded-lg bg-white/5 hover:bg-white/10 border border-border text-xs text-muted-foreground hover:text-foreground transition-colors"
        >
          대기로 되돌리기
        </button>
      )}
    </div>
  );
}

// 발주서 PDF 모달 — 승인된 설비의 재고 부족분만 포함
// 인쇄 대화상자 없이 html2canvas+jsPDF로 발주서 영역을 PDF 파일로 바로 다운로드
// 실제 연동 시 create_order Lambda가 생성한 PDF(S3 presigned URL) 다운로드로 교체
function OrderPdfModal({ order, onClose }) {
  const printRef = useRef(null);
  const [saving, setSaving] = useState(false);
  const approvedLines = order.lines.filter(
    (l) => order.decisions[l.equipmentId] === "approved" && getOrderQty(l) > 0
  );
  const equipmentIds = [...new Set(approvedLines.map((l) => l.equipmentId))];
  const totalQty = approvedLines.reduce((sum, l) => sum + getOrderQty(l), 0);

  const handleSave = async () => {
    if (!printRef.current || saving) return;
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
    } catch (err) {
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
            disabled={saving}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-semibold transition-colors ${
              saving
                ? "bg-primary/10 text-primary/60 border-primary/20 cursor-wait"
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
                <th className="border border-slate-300 px-3 py-2 text-left font-semibold w-24">대상 설비</th>
                <th className="border border-slate-300 px-3 py-2 text-left font-semibold">품명 / 규격</th>
                <th className="border border-slate-300 px-3 py-2 text-right font-semibold w-14">필요</th>
                <th className="border border-slate-300 px-3 py-2 text-right font-semibold w-14">재고</th>
                <th className="border border-slate-300 px-3 py-2 text-right font-semibold w-16">발주 수량</th>
              </tr>
            </thead>
            <tbody>
              {approvedLines.map((line, i) => (
                <tr key={`${line.equipmentId}-${line.part}`}>
                  <td className="border border-slate-300 px-3 py-2 text-slate-500">{i + 1}</td>
                  <td className="border border-slate-300 px-3 py-2 font-mono">{line.equipmentId}</td>
                  <td className="border border-slate-300 px-3 py-2">{line.part}</td>
                  <td className="border border-slate-300 px-3 py-2 text-right font-mono">{line.qty}</td>
                  <td className="border border-slate-300 px-3 py-2 text-right font-mono">
                    {PARTS_INVENTORY[line.part] ?? 0}
                  </td>
                  <td className="border border-slate-300 px-3 py-2 text-right font-mono font-semibold">
                    {getOrderQty(line)}
                  </td>
                </tr>
              ))}
              <tr className="bg-slate-50 font-semibold">
                <td colSpan={5} className="border border-slate-300 px-3 py-2 text-right">
                  발주 합계
                </td>
                <td className="border border-slate-300 px-3 py-2 text-right font-mono">{totalQty}</td>
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
          const stock = PARTS_INVENTORY[line.part] ?? 0;
          const orderQty = getOrderQty(line);
          return (
            <div
              key={line.part}
              className="grid grid-cols-[1fr_40px_40px_48px] gap-2 px-3 py-2 text-xs font-mono border-t border-white/5 items-center text-slate-300"
            >
              <span>{line.part}</span>
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

// 상단 "통합 발주서" 탭 전용 — 확진된 모든 설비의 부품을 한 화면에서 관리
export default function ConsolidatedOrderView({ order, canApprove, onAction }) {
  const [showPdf, setShowPdf] = useState(false);
  const equipmentIds = [...new Set(order.lines.map((l) => l.equipmentId))];
  const approvedCount = equipmentIds.filter((id) => order.decisions[id] === "approved").length;
  const rejectedCount = equipmentIds.filter((id) => order.decisions[id] === "rejected").length;
  const pendingCount = equipmentIds.length - approvedCount - rejectedCount;
  const approvedLineCount = order.lines.filter(
    (l) => order.decisions[l.equipmentId] === "approved" && getOrderQty(l) > 0
  ).length;
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
            disabled={approvedLineCount === 0}
            title={
              approvedLineCount === 0
                ? "승인된 설비가 없습니다 — 승인된 설비의 부품만 발주서에 포함됩니다"
                : "승인된 설비 부품으로 구성된 발주서 보기"
            }
            className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-semibold transition-colors ${
              approvedLineCount === 0
                ? "bg-white/[0.02] border-border text-muted-foreground/50 cursor-not-allowed"
                : "bg-white/5 hover:bg-white/10 border-border text-foreground"
            }`}
          >
            <FileText size={12} />
            발주서 PDF{approvedLineCount > 0 ? ` (${approvedLineCount})` : ""}
          </button>
        </div>
        <span className="text-xs text-muted-foreground font-mono">
          {equipmentIds.length}개 설비 · {order.lines.length}개 라인 · 생성 {order.createdAt}
        </span>
        <div className="flex items-center gap-1.5 text-[10px] font-mono mt-3">
          <span className="px-1.5 py-1 rounded bg-emerald-500/15 text-emerald-400 border border-emerald-500/25">
            승인 {approvedCount}
          </span>
          <span className="px-1.5 py-1 rounded bg-slate-500/15 text-slate-300 border border-slate-500/25">
            대기 {pendingCount}
          </span>
          <span className="px-1.5 py-1 rounded bg-red-500/15 text-red-400 border border-red-500/25">
            거절 {rejectedCount}
          </span>
        </div>
        <p className="text-[10px] text-muted-foreground mt-3 flex items-center gap-1.5">
          <Info size={11} className="flex-shrink-0" />
          설비별로 승인/거절을 결정하며, 재고로 충당 가능한 부품({stockCoveredCount}종)과 예방
          교체 참고용 부품({referenceCount}종, TWF 약한 신호)은 발주에서 자동 제외됩니다. 승인된
          설비의 부족분만 발주서 PDF에 포함됩니다.
        </p>
      </div>

      {equipmentIds.map((eqId) => {
        const lines = order.lines.filter((l) => l.equipmentId === eqId);
        const status = order.decisions[eqId] ?? "pending";
        const statusCfg = ORDER_STATUS_CONFIG[status];
        return (
          <div key={eqId} className="bg-card border border-border rounded-xl p-5">
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
                const stock = PARTS_INVENTORY[line.part] ?? 0;
                const orderQty = getOrderQty(line);
                return (
                  <div
                    key={line.part}
                    className={`grid grid-cols-[1fr_40px_40px_48px] gap-2 px-3 py-2 text-xs font-mono border-t border-white/5 items-center ${
                      status === "rejected" ? "opacity-40" : "text-slate-300"
                    }`}
                  >
                    <span className={status === "rejected" ? "line-through" : ""}>{line.part}</span>
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
      })}

      {showPdf && <OrderPdfModal order={order} onClose={() => setShowPdf(false)} />}
    </div>
  );
}
