import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

// Vite's config-free SSR transform emits classic JSX references for this existing component.
globalThis.React = React;

function line(id, equipmentId, part, qty, { referenceOnly = false, stock, partId } = {}) {
  const built = { id, equipmentId, part, qty, referenceOnly };
  if (stock !== undefined) built.stock = stock;
  if (partId !== undefined) built.partId = partId;
  return built;
}

function keys(groups) {
  return groups.map((group) => group.key);
}

// Independent reference for the aggregation contract (mirrors buildOrderPdfGroups semantics).
function expectedGroups(order, PARTS_INVENTORY) {
  const approved = order.lines.filter(
    (candidate) =>
      order.decisions[candidate.equipmentId] === "approved" && !candidate.referenceOnly
  );
  const map = new Map();
  for (const candidate of approved) {
    const key = candidate.partId || candidate.part;
    if (!map.has(key)) map.set(key, []);
    map.get(key).push(candidate);
  }
  return [...map.entries()]
    .map(([key, lines]) => {
      const requiredQty = lines.reduce((sum, l) => sum + l.qty, 0);
      const stockLine = lines.find((l) => typeof l.stock === "number");
      const stock = stockLine ? stockLine.stock : PARTS_INVENTORY[key] ?? 0;
      return {
        key,
        orderQty: Math.max(0, requiredQty - stock),
        facilities: [...new Set(lines.map((l) => l.equipmentId))].sort(),
      };
    })
    .filter((group) => group.orderQty > 0)
    .sort((a, b) => a.key.localeCompare(b.key));
}

function generatedNonBugOrders() {
  const statuses = ["approved", "pending", "rejected"];
  const parts = ["OS-404", "PW-303", "TW-101", "UNKNOWN"];
  const quantities = [0, 1, 2, 6];
  const referenceOnlyValues = [false, true];
  const cases = [];

  for (const status of statuses) {
    for (const part of parts) {
      for (const qty of quantities) {
        for (const referenceOnly of referenceOnlyValues) {
          const equipmentId = cases.length % 2 === 0 ? "FAC-A" : "FAC-B";
          cases.push({
            name: `${status}:${part}:qty-${qty}:reference-${referenceOnly}`,
            decisions: { [equipmentId]: status },
            lines: [line(`generated-${cases.length}`, equipmentId, part, qty, { referenceOnly })],
          });
        }
      }
    }
  }

  return cases;
}

async function loadOrderModules(t) {
  const server = await createServer({
    root: fileURLToPath(new URL("../..", import.meta.url)),
    configFile: false,
    appType: "custom",
    logLevel: "silent",
    server: { middlewareMode: true },
  });
  t.after(() => server.close());

  const [orderTable, constants] = await Promise.all([
    server.ssrLoadModule("/src/components/OrderTable.jsx"),
    server.ssrLoadModule("/src/constants.js"),
  ]);
  return { ...orderTable, ...constants };
}

// Property 2: Preservation - Existing Eligibility Rules Remain Unchanged
// **Validates: Requirements 3.1, 3.2, 3.3, 3.4**
test("non-bug inputs preserve group eligibility, quantities, and distinct independent parts", async (t) => {
  const { buildOrderPdfGroups, PARTS_INVENTORY } = await loadOrderModules(t);

  const explicitCases = [
    {
      name: "approved positive shortage is included with unchanged total",
      decisions: { "FAC-A": "approved" },
      lines: [line("approved-shortage", "FAC-A", "OS-404", 3, { stock: 0 })],
    },
    {
      name: "pending and rejected lines are excluded",
      decisions: { "FAC-A": "pending", "FAC-B": "rejected" },
      lines: [
        line("pending", "FAC-A", "OS-404", 2),
        line("rejected", "FAC-B", "UNKNOWN", 4),
      ],
    },
    {
      name: "stock-covered and reference-only lines remain excluded",
      decisions: { "FAC-A": "approved", "FAC-B": "approved" },
      lines: [
        line("stock-covered", "FAC-A", "PW-303", 1, { stock: 1 }),
        line("reference", "FAC-B", "TW-101", 20, { referenceOnly: true }),
      ],
    },
    {
      name: "independent distinct parts remain distinct groups",
      decisions: { "FAC-A": "approved", "FAC-B": "approved" },
      lines: [
        line("facility-a", "FAC-A", "OS-404", 1, { stock: 0 }),
        line("facility-b", "FAC-B", "HD-202", 2, { stock: 0 }),
      ],
    },
  ];

  for (const order of [...explicitCases, ...generatedNonBugOrders()]) {
    const expected = expectedGroups(order, PARTS_INVENTORY);
    const actual = buildOrderPdfGroups(order);
    assert.deepEqual(keys(actual), keys(expected), order.name);
    assert.equal(
      actual.reduce((sum, group) => sum + group.orderQty, 0),
      expected.reduce((sum, group) => sum + group.orderQty, 0),
      `${order.name}: total order quantity`
    );
    for (const group of actual) {
      const match = expected.find((e) => e.key === group.key);
      assert.ok(match, `${order.name}: unexpected group ${group.key}`);
      assert.equal(group.orderQty, match.orderQty, `${order.name}: ${group.key} orderQty`);
      assert.deepEqual(group.facilities, match.facilities, `${order.name}: ${group.key} facilities`);
    }
  }

  // referenceOnly + fully stock-covered parts are excluded → no groups here.
  const covered = explicitCases.find((c) => c.name.startsWith("stock-covered"));
  assert.deepEqual(buildOrderPdfGroups(covered), []);

  // Two different parts across independent facilities stay distinct groups.
  const independent = explicitCases.find((c) => c.name.startsWith("independent distinct"));
  assert.deepEqual(keys(buildOrderPdfGroups(independent)), ["HD-202", "OS-404"]);
});

// Property 2: Preservation - Existing Eligibility Rules Remain Unchanged
// **Validates: Requirements 3.3, 3.5, 3.6**
test("detail visibility, decision actions, permissions, and explicit cancellation are preserved", async (t) => {
  const { EquipmentOrderPanel, buildOrderPdfGroups } = await loadOrderModules(t);
  const eq = { id: "FAC-A" };
  const lines = [
    line("shortage", "FAC-A", "OS-404", 2, { stock: 0 }),
    line("stock-covered", "FAC-A", "PW-303", 1, { stock: 1 }),
    line("reference", "FAC-A", "TW-101", 10, { referenceOnly: true }),
  ];
  const renderPanel = (status, canApprove) =>
    renderToStaticMarkup(
      React.createElement(EquipmentOrderPanel, {
        eq,
        order: { id: "PO-OBSERVE", decisions: { "FAC-A": status }, lines },
        canApprove,
        onAction: () => {},
        onViewConsolidated: () => {},
      })
    );

  const pendingAdmin = renderPanel("pending", true);
  assert.match(pendingAdmin, /OS-404/);
  assert.match(pendingAdmin, /PW-303/);
  assert.match(pendingAdmin, /TW-101/);
  assert.match(pendingAdmin, />재고</);
  assert.match(pendingAdmin, />참고</);
  assert.match(pendingAdmin, /이 설비 발주 승인/);
  assert.match(pendingAdmin, /발주 제외 \(거절\)/);

  const pendingOperator = renderPanel("pending", false);
  assert.match(pendingOperator, /관리자\(admin\) 권한입니다/);
  assert.doesNotMatch(pendingOperator, /이 설비 발주 승인/);

  assert.match(renderPanel("approved", true), /발주 승인 완료/);
  assert.match(renderPanel("approved", true), /대기로 되돌리기/);
  assert.match(renderPanel("rejected", true), /발주에서 제외됨/);
  assert.match(renderPanel("rejected", true), /대기로 되돌리기/);
  assert.match(renderPanel("ordered", true), /발주 완료 · PDF 다운로드됨/);
  assert.match(renderPanel("ordered", true), /발주 취소/);
  assert.doesNotMatch(renderPanel("ordered", false), /발주 취소/);

  // Explicit ordered → approved cancellation makes the part orderable again.
  const beforeCancellation = {
    decisions: { "FAC-A": "ordered" },
    lines: [line("cancelled-order", "FAC-A", "OS-404", 2, { stock: 0 })],
  };
  const afterCancellation = {
    ...beforeCancellation,
    decisions: { ...beforeCancellation.decisions, "FAC-A": "approved" },
  };
  assert.deepEqual(buildOrderPdfGroups(beforeCancellation), []);
  assert.deepEqual(keys(buildOrderPdfGroups(afterCancellation)), ["OS-404"]);
});
