import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

globalThis.React = React;

function emptyOrder() {
  return {
    id: "PO-EMPTY",
    createdAt: "2025-01-01",
    // Only an already-ordered facility → no approved lines → no groups.
    decisions: { "FAC-A": "ordered" },
    lines: [{ id: "saved", equipmentId: "FAC-A", part: "OS-404", qty: 1, stock: 0 }],
  };
}

function nonEmptyOrder() {
  return {
    id: "PO-LIVE",
    createdAt: "2025-01-01",
    decisions: { "FAC-A": "approved" },
    lines: [{ id: "shortage", equipmentId: "FAC-A", part: "OS-404", qty: 2, stock: 0 }],
  };
}

test("empty groups are guarded, and only successful completion closes the modal", async (t) => {
  const server = await createServer({
    root: fileURLToPath(new URL("../..", import.meta.url)),
    configFile: false,
    appType: "custom",
    logLevel: "silent",
    server: { middlewareMode: true },
  });
  t.after(() => server.close());
  const {
    OrderPdfModal,
    finalizeSuccessfulPdfSave,
    buildOrderPdfGroups,
    default: ConsolidatedOrderView,
  } = await server.ssrLoadModule("/src/components/OrderTable.jsx");

  const empty = emptyOrder();
  assert.deepEqual(buildOrderPdfGroups(empty), []);

  const modal = renderToStaticMarkup(
    React.createElement(OrderPdfModal, {
      order: empty,
      onClose: () => {},
      onDownloaded: () => {},
    })
  );
  assert.match(modal, /새로 승인된 발주 대상이 없습니다\./);
  assert.match(modal, /<button[^>]*disabled=""[^>]*>.*PDF 저장/s);

  const consolidated = renderToStaticMarkup(
    React.createElement(ConsolidatedOrderView, {
      order: empty,
      canApprove: true,
      onAction: () => {},
      onMarkOrdered: () => {},
    })
  );
  assert.match(consolidated, /새로 승인된 발주 대상이 없습니다\./);
  assert.match(consolidated, /<button[^>]*disabled=""[^>]*>.*발주서 PDF/s);

  // A non-empty order enables save and shows the group count in the consolidated PDF button.
  const live = nonEmptyOrder();
  assert.equal(buildOrderPdfGroups(live).length, 1);
  const liveModal = renderToStaticMarkup(
    React.createElement(OrderPdfModal, {
      order: live,
      onClose: () => {},
      onDownloaded: () => {},
    })
  );
  assert.doesNotMatch(liveModal, /새로 승인된 발주 대상이 없습니다\./);
  assert.doesNotMatch(liveModal, /<button[^>]*disabled=""[^>]*>.*PDF 저장/s);
  const liveConsolidated = renderToStaticMarkup(
    React.createElement(ConsolidatedOrderView, {
      order: live,
      canApprove: true,
      onAction: () => {},
      onMarkOrdered: () => {},
    })
  );
  assert.match(liveConsolidated, /발주서 PDF \(1\)/);

  // Success path: completion then close, in order.
  const calls = [];
  finalizeSuccessfulPdfSave(
    () => calls.push("completed"),
    () => calls.push("closed")
  );
  assert.deepEqual(calls, ["completed", "closed"]);

  // Error path: a failing completion propagates and never closes the modal.
  assert.throws(
    () =>
      finalizeSuccessfulPdfSave(
        () => {
          throw new Error("completion failed");
        },
        () => calls.push("incorrectly closed")
      ),
    /completion failed/
  );
  assert.deepEqual(calls, ["completed", "closed"]);
});
