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

export function mapBackendFindingToUi(f: any): Finding {
  const filePath = f.location?.path || f.file_path || "Unknown file";
  const startLine = f.location?.start_line || f.line_number || 1;
  const tool = f.metadata?.engine || f.scanner || "semgrep";

  return {
    id: f.id,
    severity: mapSeverity(f.severity),
    category: f.category,
    title: f.title || f.rule_id || "Vulnerability",

    file: filePath,
    lineNumber: startLine,
    tool: mapTool(tool),

    confidence: f.confidence ?? 100,
    status: f.status || "open",
    description: f.description ?? f.message ?? "",
    code: f.code ?? "",
    suggestedFix: f.suggested_fix,
    references: f.references ?? [],
    ml_score: f.ml_score,
  };
}