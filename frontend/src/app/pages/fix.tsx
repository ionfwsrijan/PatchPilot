import { useEffect, useState } from "react";
import { GitPullRequest, Download, Copy, AlertTriangle, CheckCircle2, Loader2 } from "lucide-react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { DiffViewer } from "../components/diff-viewer";
import { SeverityChip } from "../components/severity-chip";
import { Badge } from "../components/ui/badge";
import { loadLastScan } from "../lib/scan-store";
import { getJobFindings, fix as fixApi } from "../lib/api";
import { mapBackendFindingToUi } from "../lib/mappers";

interface DiffLine {
  type: "added" | "removed" | "context";
  content: string;
  oldLine?: number;
  newLine?: number;
}

function parseUnifiedDiff(diffStr: string): DiffLine[] {
  if (!diffStr) return [];
  const lines = diffStr.split("\n");
  const diffLines: DiffLine[] = [];
  let oldLineNum = 0;
  let newLineNum = 0;

  for (const line of lines) {
    if (line.startsWith("---") || line.startsWith("+++")) {
      continue;
    }
    if (line.startsWith("@@")) {
      const match = line.match(/^@@ -(\d+),?\d* \+(\d+),?\d* @@/);
      if (match) {
        oldLineNum = parseInt(match[1], 10);
        newLineNum = parseInt(match[2], 10);
      }
      continue;
    }
    
    if (line.startsWith("+")) {
      diffLines.push({
        type: "added",
        content: line.substring(1),
        newLine: newLineNum++
      });
    } else if (line.startsWith("-")) {
      diffLines.push({
        type: "removed",
        content: line.substring(1),
        oldLine: oldLineNum++
      });
    } else {
      diffLines.push({
        type: "context",
        content: line.startsWith(" ") ? line.substring(1) : line,
        oldLine: oldLineNum++,
        newLine: newLineNum++
      });
    }
  }

  return diffLines;
}

function generateDiff(oldCode: string, newCode: string): DiffLine[] {
  const oldLines = (oldCode || "").split("\n");
  const newLines = (newCode || "").split("\n");
  const diffLines: DiffLine[] = [];

  if (!oldCode && !newCode) {
    return [
      { type: "context", content: "No code changes required for this remediation step." }
    ];
  }

  let i = 0;
  let j = 0;
  while (i < oldLines.length || j < newLines.length) {
    if (i < oldLines.length && j < newLines.length && oldLines[i] === newLines[j]) {
      diffLines.push({
        type: "context",
        content: oldLines[i],
        oldLine: i + 1,
        newLine: j + 1
      });
      i++;
      j++;
    } else {
      let matchIdx = -1;
      for (let k = i; k < oldLines.length; k++) {
        if (oldLines[k] === newLines[j]) {
          matchIdx = k;
          break;
        }
      }
      
      if (matchIdx !== -1) {
        for (let k = i; k < matchIdx; k++) {
          diffLines.push({
            type: "removed",
            content: oldLines[k],
            oldLine: k + 1
          });
        }
        i = matchIdx;
      } else {
        if (i < oldLines.length) {
          diffLines.push({
            type: "removed",
            content: oldLines[i],
            oldLine: i + 1
          });
          i++;
        }
        if (j < newLines.length) {
          diffLines.push({
            type: "added",
            content: newLines[j],
            newLine: j + 1
          });
          j++;
        }
      }
    }
  }

  return diffLines;
}

export function Fix() {
  const navigate = useNavigate();
  const location = useLocation();
  const state = location.state as { findingIds?: string[] } | null;
  const findingIds = state?.findingIds || [];

  const scan = loadLastScan();
  const jobId = scan?.job_id;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mappedFixes, setMappedFixes] = useState<any[]>([]);
  const [selectedFixes, setSelectedFixes] = useState<Set<string>>(new Set());
  const [copiedId, setCopiedId] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) {
      setError("No active scan job found. Go to the Dashboard and upload a ZIP to start a scan.");
      setLoading(false);
      return;
    }
    if (findingIds.length === 0) {
      setError("No findings selected. Please select findings from the list to propose fixes.");
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);

    getJobFindings(jobId)
      .then((allFindings: any[]) => {
        const findingsList = allFindings.map(mapBackendFindingToUi);
        const selectedFindingsObjects = findingsList.filter(f => findingIds.includes(f.id));

        if (selectedFindingsObjects.length === 0) {
          setError("No matching findings found in current scan.");
          setLoading(false);
          return;
        }

        const prefixedIds = selectedFindingsObjects.map(f => {
          const tool = f.tool || "semgrep";
          const ruleId = f.title || "";
          const file = f.file || "";
          const line = f.lineNumber || 1;

          if (tool === "osv") {
            const rawFinding = allFindings.find(rf => rf.id === f.id);
            const pName = rawFinding?.package_name || "pkg";
            return `osv:${ruleId}:${pName}`;
          } else if (tool === "gitleaks") {
            return `gitleaks:${ruleId}:${file}:${line}`;
          } else {
            return `semgrep:${ruleId}:${file}:${line}`;
          }
        });

        fixApi(jobId, prefixedIds)
          .then((res: any) => {
            const proposedFixes = res?.fixes || [];

            const uiFixes = proposedFixes.map((pf: any, idx: number) => {
              const finding = selectedFindingsObjects[idx] || selectedFindingsObjects[0];
              
              let diffLines: DiffLine[] = [];
              if (pf.diff) {
                diffLines = parseUnifiedDiff(pf.diff);
              } else if (finding) {
                diffLines = generateDiff(finding.code, finding.suggestedFix || finding.code);
              }

              return {
                id: pf.finding_id,
                title: pf.summary || finding?.title || "Apply security patch",
                severity: (finding?.severity || "medium"),
                file: finding?.file || pf.files_changed?.[0] || "Unknown file",
                risk: finding?.severity === "critical" || finding?.severity === "high" ? "Medium" : "Low",
                effort: finding?.tool === "osv" ? "15 min" : "5 min",
                filesAffected: pf.files_changed?.length || 1,
                diff: diffLines,
                rawDiffText: pf.diff || "",
                notes: pf.notes || []
              };
            });

            setMappedFixes(uiFixes);
            setSelectedFixes(new Set(uiFixes.map(uf => uf.id)));
          })
          .catch((err) => {
            console.error("Failed to fetch backend fixes:", err);
            setError("Failed to load proposed fixes from the backend.");
          })
          .finally(() => {
            setLoading(false);
          });
      })
      .catch((err) => {
        console.error("Failed to load scan findings:", err);
        setError("Failed to fetch scan findings list.");
        setLoading(false);
      });
  }, [jobId, JSON.stringify(findingIds)]);

  const toggleFix = (id: string) => {
    const newSelected = new Set(selectedFixes);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedFixes(newSelected);
  };

  const handleApplyFixes = (targetFindingIds: string[]) => {
    // Navigate to /verify with applied fixes metadata
    navigate("/verify", {
      state: {
        appliedFixIds: targetFindingIds,
        jobId: jobId,
        timestamp: new Date().toISOString()
      }
    });
  };

  const handleCopyPatch = async (id: string, diffLines: DiffLine[]) => {
    const diffText = diffLines
      .map((line) => {
        const prefix = line.type === "added" ? "+ " : line.type === "removed" ? "- " : "  ";
        return prefix + line.content;
      })
      .join("\n");

    try {
      await navigator.clipboard.writeText(diffText);
      setCopiedId(id);
      setTimeout(() => setCopiedId(null), 2000);
    } catch (err) {
      console.error("Failed to copy patch:", err);
    }
  };

  if (loading) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-7xl flex justify-center items-center h-64">
        <div className="flex flex-col items-center gap-4 text-muted-foreground">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p>Loading proposed fixes...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 max-w-7xl pb-20 md:pb-8">
        <div className="mb-6">
          <h1 className="mb-2">Proposed Fixes</h1>
          <p className="text-muted-foreground">{error}</p>
          <div className="mt-4">
            <Link to="/findings">
              <Button>Go to Findings</Button>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const filesAffectedCount = new Set(mappedFixes.flatMap(f => f.file)).size;

  return (
    <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 max-w-7xl pb-20 md:pb-8">
      <div className="mb-6">
        <h1 className="mb-2">Proposed Fixes</h1>
        <p className="text-muted-foreground">
          Review and apply automated fixes for detected vulnerabilities
        </p>
      </div>

      {/* Summary Card */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Fix Summary</CardTitle>
          <CardDescription>{mappedFixes.length} findings with available automated fixes</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-2xl font-semibold mb-1">{mappedFixes.length}</div>
              <div className="text-sm text-muted-foreground">Proposed Fixes</div>
            </div>
            <div>
              <div className="text-2xl font-semibold mb-1">{filesAffectedCount}</div>
              <div className="text-sm text-muted-foreground">Files Affected</div>
            </div>
            <div>
              <div className="text-2xl font-semibold mb-1">~{mappedFixes.length * 5}m</div>
              <div className="text-sm text-muted-foreground">Est. Time</div>
            </div>
            <div>
              <div className="text-2xl font-semibold mb-1">Low-Med</div>
              <div className="text-sm text-muted-foreground">Risk Level</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Fix Cards */}
      <div className="space-y-6 mb-6">
        {mappedFixes.map((fix) => (
          <Card key={fix.id} className={selectedFixes.has(fix.id) ? "border-primary" : ""}>
            <CardHeader>
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-2">
                    <SeverityChip severity={fix.severity} />
                    <Badge variant="outline" className="text-xs">
                      {fix.filesAffected} file{fix.filesAffected !== 1 ? "s" : ""}
                    </Badge>
                  </div>
                  <CardTitle className="text-lg mb-1">{fix.title}</CardTitle>
                  <CardDescription className="font-mono text-xs">{fix.file}</CardDescription>
                </div>
                <input
                  type="checkbox"
                  checked={selectedFixes.has(fix.id)}
                  onChange={() => toggleFix(fix.id)}
                  className="h-5 w-5 rounded border-border"
                />
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-3 gap-4 mb-4 p-3 rounded-lg bg-muted">
                <div>
                  <div className="text-xs text-muted-foreground mb-1">Risk Level</div>
                  <div className="text-sm font-medium flex items-center gap-1">
                    <AlertTriangle className="h-3 w-3" />
                    {fix.risk}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground mb-1">Est. Effort</div>
                  <div className="text-sm font-medium">{fix.effort}</div>
                </div>
                <div>
                  <div className="text-xs text-muted-foreground mb-1">Auto-fix</div>
                  <div className="text-sm font-medium flex items-center gap-1">
                    <CheckCircle2 className="h-3 w-3 text-status-success" />
                    Available
                  </div>
                </div>
              </div>

              <DiffViewer diff={fix.diff} filename={fix.file} className="mb-4" />

              <div className="flex flex-wrap gap-2">
                <Button onClick={() => handleApplyFixes([fix.id])}>Apply Patch</Button>
                <Button variant="outline" disabled>
                  <GitPullRequest className="h-4 w-4 mr-2" />
                  Open PR
                  <Badge variant="secondary" className="ml-2 text-xs">
                    Not configured
                  </Badge>
                </Button>
                <Button variant="outline" onClick={() => handleCopyPatch(fix.id, fix.diff)}>
                  <Copy className="h-4 w-4 mr-2" />
                  {copiedId === fix.id ? "Copied!" : "Copy Patch"}
                </Button>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Actions */}
      <Card>
        <CardContent className="p-6">
          <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
            <div>
              <div className="font-medium mb-1">Ready to apply {selectedFixes.size} fix{selectedFixes.size !== 1 ? "es" : ""}</div>
              <div className="text-sm text-muted-foreground">
                Changes will be validated before being applied
              </div>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" disabled>
                <Download className="h-4 w-4 mr-2" />
                Download All
              </Button>
              <Button disabled={selectedFixes.size === 0} onClick={() => handleApplyFixes(Array.from(selectedFixes))}>
                Apply Selected Fixes
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
