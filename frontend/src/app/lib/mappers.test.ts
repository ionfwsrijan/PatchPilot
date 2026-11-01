import test from "node:test";
import assert from "node:assert/strict";
import { mapStatus, mapBackendFindingToUi } from "./mappers.ts";
import type { BackendFinding } from "./api.ts";

test("mapStatus: preserves valid status values", () => {
  assert.equal(mapStatus("accepted"), "accepted");
  assert.equal(mapStatus("ignored"), "ignored");
  assert.equal(mapStatus("open"), "open");
});

test("mapStatus: safely falls back to 'open' for missing, null, or invalid values", () => {
  assert.equal(mapStatus(undefined), "open");
  assert.equal(mapStatus(null as any), "open");
  assert.equal(mapStatus(""), "open");
  assert.equal(mapStatus("resolved"), "open");
  assert.equal(mapStatus("in_progress"), "open");
  assert.equal(mapStatus("CLOSED" as any), "open");
});

test("mapBackendFindingToUi: preserves persisted status from backend", () => {
  const baseFinding: BackendFinding = {
    id: "finding-123",
    severity: "HIGH",
    category: "sast",
    title: "SQL Injection in User Controller",
    location: {
      path: "src/controllers/user.ts",
      start_line: 42,
    },
    metadata: {
      engine: "semgrep",
    },
  };

  // 1. Accepted status
  const acceptedUi = mapBackendFindingToUi({ ...baseFinding, status: "accepted" });
  assert.equal(acceptedUi.status, "accepted");
  assert.equal(acceptedUi.title, "SQL Injection in User Controller");
  assert.equal(acceptedUi.severity, "high");

  // 2. Ignored status
  const ignoredUi = mapBackendFindingToUi({ ...baseFinding, status: "ignored" });
  assert.equal(ignoredUi.status, "ignored");

  // 3. Open status
  const openUi = mapBackendFindingToUi({ ...baseFinding, status: "open" });
  assert.equal(openUi.status, "open");

  // 4. Missing status defaults safely to 'open'
  const missingStatusUi = mapBackendFindingToUi({ ...baseFinding });
  assert.equal(missingStatusUi.status, "open");

  // 5. Invalid status falls back to 'open'
  const invalidStatusUi = mapBackendFindingToUi({ ...baseFinding, status: "legacy_pending" });
  assert.equal(invalidStatusUi.status, "open");
});
