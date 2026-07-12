import type { Finding } from "../data/sample-data";
import { saveBlob } from "./download";
/**
 * Escapes a single CSV field per RFC 4180: wraps the value in double quotes
 * whenever it contains a comma, double quote, or newline, and doubles any
 * embedded double quotes.
 */
function escapeCsvField(value: string | number): string {
  const stringValue = String(value ?? "");
  if (/[",\n\r]/.test(stringValue)) {
    return `"${stringValue.replace(/"/g, '""')}"`;
  }
  return stringValue;
}

const CSV_COLUMNS = ["Finding ID", "Scanner Name", "Severity", "Title", "Status"] as const;

/**
 * Builds a CSV string (with header row) from a list of findings, covering
 * the fields needed for reporting / compliance documentation:
 * Finding ID, Scanner Name, Severity, Title, Status.
 */
export function findingsToCsv(findings: Finding[]): string {
  const rows = findings.map((f) =>
    [f.id, f.tool, f.severity, f.title, f.status].map(escapeCsvField).join(","),
  );
  return [CSV_COLUMNS.join(","), ...rows].join("\r\n");
}

/**
 * Triggers a browser download of the given findings as a CSV file.
 */
export function downloadFindingsAsCsv(findings: Finding[], filename = "findings.csv"): void {
  const csv = findingsToCsv(findings);
  // Prepend a UTF-8 BOM so Excel opens the file with correct encoding.
  const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
  saveBlob(blob, filename);
}