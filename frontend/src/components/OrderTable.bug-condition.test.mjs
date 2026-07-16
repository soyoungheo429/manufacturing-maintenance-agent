import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { createServer } from "vite";

const NO_NEW_TARGET_MESSAGE = "새로 승인된 발주 대상이 없습니다.";

// Lines now carry optional partId/stock so aggregation-by-part-code can be exercised.
function line(id, equipmentId, part, qty, { referenceOnly = false, stock, partId } = {}) {
  const built = { id, equipmentId, part, qty, referenceOnly };
  if (stock !== undefined) built.stock = stock;
  if (partId !== undefined) built.partId = partId;
  return built;
}

// Independent reference implementation of the aggregation contract: approved, non-reference lines
// grouped by part code, stock subtracted once against the summed requirement, only positive groups
// survive, sorted by part code.
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

function summarize(groups) {
  return groups.map((group) => ({
    key: group.key,
    orderQty: group.orderQty,
    facilities: group.facilities,
  }));
}

function buildGeneratedMatrix() {
  const statuses = ["approved", "ordered", "pending", "rejected"];
  const parts = ["OS-404", "PW-303", "UNKNOWN"];
  const quantities = [0, 1, 2, 6];
  const referenceOnlyValues = [false, true];
  const cases = [];

  for (const status of statuses) {
    for (const part of parts) {
      for (const qty of quantities) {
        for (const referenceOnly of referenceOnlyValues) {
          const equipmentId = cases.length % 2 === 0 ? "FAC-A" : "FAC-B";
          cases.push({
            name: `generated:${status}:${part}:qty-${qty}:reference-${referenceOnly}:${equipmentId}`,
            order: {
              decisions: { [equipmentId]: status },
              lines: [line(`generated-${cases.length}`, equipmentId, part, qty, { referenceOnly })],
            },
          });
        }
      }
    }
  }

  return cases;
}

// Property 1: Bug Condition - Aggregated Part Demand Is Reorderable Exactly Once
// **Validates: Requirements 1.1, 1.2, 2.1, 2.2, 2.5**
test("PDF groups equal exactly the parts with aggregate orderQty > 0 from approved facilities", async (t) => {
  const server = await createServer({
    root: fileURLToPath(new URL("../..", import.meta.url)),
    configFile: false,
    appType: "custom",
    logLevel: "silent",
    server: { middlewareMode: true },
  });
  t.after(() => server.close());

  const [{ buildOrderPdfGroups }, { PARTS_INVENTORY }] = await Promise.all([
    server.ssrLoadModule("/src/components/OrderTable.jsx"),
    server.ssrLoadModule("/src/constants.js"),
  ]);

  const deterministicCases = [
    {
      // The core regression: OS-404 needed by two approved facilities, shared stock 1.
      // Per-line subtraction produced 0 on every line (part vanished); aggregation yields one
      // group with orderQty 1 listing both facilities.
      name: "shared-stock-os404-two-approved-facilities",
      order: {
        decisions: { "TEST-001": "approved", facility1: "approved" },
        lines: [
          line("os-test", "TEST-001", "OS-404", 1, { stock: 1 }),
          line("os-fac1", "facility1", "OS-404", 1, { stock: 1 }),
        ],
      },
    },
    {
      name: "completed-only-excluded",
      order: {
        decisions: { L47340: "ordered" },
        lines: [line("completed-os", "L47340", "OS-404", 1, { stock: 0 })],
      },
    },
    {
      name: "mixed-ordered-approved-facilities",
      order: {
        decisions: { L47340: "ordered", M52891: "approved" },
        lines: [
          line("completed-os", "L47340", "OS-404", 1, { stock: 0 }),
          line("new-power", "M52891", "PW-303", 2, { stock: 1 }),
        ],
      },
    },
    {
      name: "approved-zero-and-reference-only",
      order: {
        decisions: { H31204: "approved", M52891: "approved" },
        lines: [
          line("reference", "H31204", "TW-101", 10, { referenceOnly: true }),
          line("stock-covered", "M52891", "PW-303", 1, { stock: 1 }),
        ],
      },
    },
    {
      name: "repeated-save-after-line-is-completed",
      order: {
        decisions: { L47340: "ordered" },
        lines: [line("saved-snapshot", "L47340", "OS-404", 1, { stock: 0 })],
      },
    },
  ];

  const violations = [];
  for (const scenario of [...deterministicCases, ...buildGeneratedMatrix()]) {
    const expected = expectedGroups(scenario.order, PARTS_INVENTORY);
    const actual = buildOrderPdfGroups(scenario.order);
    const saveEnabled = actual.length > 0;

    if (
      JSON.stringify(summarize(actual)) !== JSON.stringify(summarize(expected)) ||
      saveEnabled !== (expected.length > 0)
    ) {
      violations.push(
        `${scenario.name}: expected groups/save=${JSON.stringify(summarize(expected))}/${
          expected.length > 0
        }, observed=${JSON.stringify(summarize(actual))}/${saveEnabled}`
      );
    }
  }

  // Explicit assertions for the OS-404 shared-stock regression.
  const shared = buildOrderPdfGroups(deterministicCases[0].order);
  assert.equal(shared.length, 1, "shared OS-404 collapses to one group");
  assert.equal(shared[0].key, "OS-404");
  assert.equal(shared[0].requiredQty, 2);
  assert.equal(shared[0].stock, 1);
  assert.equal(shared[0].orderQty, 1);
  assert.deepEqual(shared[0].facilities, ["TEST-001", "facility1"]);

  // Ordered facilities are excluded so completed parts are not re-orderable.
  assert.deepEqual(buildOrderPdfGroups(deterministicCases[1].order), []);

  // Empty group set disables save and surfaces the amber empty-state copy.
  const emptyCase = deterministicCases.find((s) => s.name === "approved-zero-and-reference-only");
  assert.deepEqual(buildOrderPdfGroups(emptyCase.order), []);
  const source = await (await import("node:fs/promises")).readFile(
    new URL("./OrderTable.jsx", import.meta.url),
    "utf8"
  );
  if (!source.includes(NO_NEW_TARGET_MESSAGE)) {
    violations.push(
      `approved-zero-and-reference-only: expected visible message ${JSON.stringify(
        NO_NEW_TARGET_MESSAGE
      )}, observed none`
    );
  }

  assert.deepEqual(violations, [], `Bug-condition counterexamples:\n${violations.join("\n")}`);
});
