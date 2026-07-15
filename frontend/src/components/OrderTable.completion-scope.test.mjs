import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { createServer } from "vite";

async function loadCompletionModules(t) {
  const server = await createServer({
    root: fileURLToPath(new URL("../..", import.meta.url)),
    configFile: false,
    appType: "custom",
    logLevel: "silent",
    server: { middlewareMode: true },
  });
  t.after(() => server.close());

  const [orderTable, app] = await Promise.all([
    server.ssrLoadModule("/src/components/OrderTable.jsx"),
    server.ssrLoadModule("/src/App.jsx"),
  ]);
  return { ...orderTable, ...app };
}

// Property 3: Completion Scope - Only Included Facilities Transition
// **Validates: Requirements 2.5, 3.5, 3.6**
test("successful PDF completion passes the union of group facilities and scopes transitions", async (t) => {
  const {
    finalizeSuccessfulPdfSave,
    buildOrderPdfGroups,
    transitionSavedFacilitiesToOrdered,
  } = await loadCompletionModules(t);

  // Two approved facilities share OS-404 (aggregated into one group) and FAC-A also needs a
  // distinct short part. The facilities to mark ordered are the UNION across included groups.
  const order = {
    decisions: { "FAC-A": "approved", "FAC-B": "approved", "FAC-C": "rejected" },
    lines: [
      { id: "os-a", equipmentId: "FAC-A", part: "OS-404", qty: 1, stock: 1 },
      { id: "os-b", equipmentId: "FAC-B", part: "OS-404", qty: 1, stock: 1 },
      { id: "hd-a", equipmentId: "FAC-A", part: "HD-202", qty: 2, stock: 0 },
      { id: "os-c", equipmentId: "FAC-C", part: "OS-404", qty: 5, stock: 1 },
    ],
  };
  const groups = buildOrderPdfGroups(order);
  const savedFacilityIds = [...new Set(groups.flatMap((g) => g.facilities))].sort();
  assert.deepEqual(savedFacilityIds, ["FAC-A", "FAC-B"]);

  const calls = [];
  finalizeSuccessfulPdfSave(
    (facilityIds) => calls.push(["completed", facilityIds]),
    () => calls.push(["closed"]),
    savedFacilityIds
  );
  assert.deepEqual(calls, [
    ["completed", ["FAC-A", "FAC-B"]],
    ["closed"],
  ]);

  const decisions = {
    "FAC-A": "approved",
    "FAC-B": "ordered",
    "FAC-C": "approved",
    "FAC-D": "pending",
    "FAC-E": "rejected",
  };
  assert.deepEqual(transitionSavedFacilitiesToOrdered(decisions, savedFacilityIds), {
    "FAC-A": "ordered",
    "FAC-B": "ordered",
    "FAC-C": "approved",
    "FAC-D": "pending",
    "FAC-E": "rejected",
  });
  assert.deepEqual(decisions, {
    "FAC-A": "approved",
    "FAC-B": "ordered",
    "FAC-C": "approved",
    "FAC-D": "pending",
    "FAC-E": "rejected",
  });
});

// Property 3: Completion Scope - Only Included Facilities Transition
// **Validates: Requirements 2.5, 3.5, 3.6**
test("for every saved subset, only matching facilities still approved become ordered", async (t) => {
  const { transitionSavedFacilitiesToOrdered } = await loadCompletionModules(t);
  const statuses = ["approved", "ordered", "pending", "rejected"];
  const facilityIds = ["FAC-A", "FAC-B", "FAC-C"];

  for (const statusA of statuses) {
    for (const statusB of statuses) {
      for (const statusC of statuses) {
        const decisions = {
          "FAC-A": statusA,
          "FAC-B": statusB,
          "FAC-C": statusC,
        };
        for (let mask = 0; mask < 1 << facilityIds.length; mask += 1) {
          const saved = facilityIds.filter((_, index) => mask & (1 << index));
          const actual = transitionSavedFacilitiesToOrdered(decisions, [
            ...saved,
            ...saved,
            "UNKNOWN",
          ]);
          const expected = Object.fromEntries(
            Object.entries(decisions).map(([id, status]) => [
              id,
              saved.includes(id) && status === "approved" ? "ordered" : status,
            ])
          );
          assert.deepEqual(actual, expected, JSON.stringify({ decisions, saved }));
        }
      }
    }
  }

  const cancelled = { "FAC-A": "approved", "FAC-B": "ordered" };
  assert.deepEqual(transitionSavedFacilitiesToOrdered(cancelled, ["FAC-A"]), {
    "FAC-A": "ordered",
    "FAC-B": "ordered",
  });
});
