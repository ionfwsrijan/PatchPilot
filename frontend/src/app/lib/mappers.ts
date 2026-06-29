import type { BackendFinding } from "./api";
import type { Finding } from "../data/sample-data";
import type { Tool } from "../components/tool-badge";

function mapSeverity(sev: BackendFinding["severity"]): Finding["severity"] {
  switch (sev) {
    case "CRITICAL":
      return "critical";
    case "HIGH":
      return "high";
    case "MEDIUM":
      return "medium";
    case "LOW":
      return "low";
    case "INFO":
    default:
      return "info";
  }
}

function mapTool(tool?: string): Tool {
  const allowedTools: Tool[] = ["semgrep", "osv", "gitleaks"];

  return allowedTools.includes(tool as Tool) ? (tool as Tool) : "semgrep";
}

export function mapBackendFindingToUi(f: BackendFinding): Finding {
  return {
    id: f.id,
    severity: mapSeverity(f.severity),
    category: f.category,
    title: f.title,

    file: f.location?.path ?? "Unknown file",
    lineNumber: f.location?.start_line ?? 1,
    tool: mapTool(f.metadata?.engine),

    confidence: f.confidence ?? 100,
    status: "open",
    description: f.description ?? "",
    code: f.code ?? "",
    suggestedFix: f.suggested_fix,
    references: f.references ?? [],
    ml_score: f.ml_score,
  };
}