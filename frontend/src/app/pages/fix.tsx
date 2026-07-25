import { useState, useEffect } from "react";
import { GitPullRequest, Download, Copy, AlertTriangle, CheckCircle2 } from "lucide-react";
import { Link, useLocation } from "react-router";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { DiffViewer } from "../components/diff-viewer";
import { SeverityChip } from "../components/severity-chip";
import { Badge } from "../components/ui/badge";
import { loadLastScan } from "../lib/scan-store";
import { fix } from "../lib/api";
import { getJobFindings } from "../lib/api";
import { mapBackendFindingToUi } from "../lib/mappers";

export function Fix() {

  const location = useLocation();

  const findingIds =
    (location.state as { findingIds?: string[] } | null)?.findingIds ?? [];

  const scan = loadLastScan();
  const [selectedFixes, setSelectedFixes] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [backendFixes, setBackendFixes] = useState<any[]>([]);
  const [findings, setFindings] = useState<any[]>([]);

  
  const displayedFixes = backendFixes.map((backendFix, index) => {
  const finding = findings.find(
    (f) => f.id === backendFix.finding_id
  );

  return {
    id: index,
    backendFix,
    finding,
  };
});

  const fixes = displayedFixes.map(({ backendFix, finding }) => ({
  id: backendFix.finding_id,

  title: finding?.title ?? backendFix.summary,

  severity: (finding?.severity?.toLowerCase() ?? "low") as
    | "critical"
    | "high"
    | "medium"
    | "low",

  file: finding?.file ?? "Unknown file",

  risk: "Unknown",

  effort: "-",

  filesAffected: backendFix.files_changed?.length ?? 0,

  diff: backendFix.diff,

  summary: backendFix.summary,

  notes: backendFix.notes,
}));


    const toggleFix = (id: string) => {
    const newSelected = new Set(selectedFixes);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else {
      newSelected.add(id);
    }
    setSelectedFixes(newSelected);
  };

  useEffect(() => {
  if (!scan?.job_id || findingIds.length === 0) {
    return;
  }

  const fetchFixes = async () => {
    try {
      setLoading(true);
      setError("");

      const response = await fix(scan.job_id, findingIds);

      setBackendFixes(response.fixes || []);
      const findingsResponse: any = await getJobFindings(scan.job_id);

      const actualFindings = Array.isArray(findingsResponse)
        ? findingsResponse
        : findingsResponse.findings ?? [];

      setFindings(
        actualFindings.map((bf: any) =>
          mapBackendFindingToUi(bf)
        )      
      );

    } catch (err) {
      console.error(err);
      setError("Failed to generate fixes.");
    } finally {
      setLoading(false);
    }
  };

  fetchFixes();

  
}, [scan?.job_id, findingIds]);


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
          <CardDescription>
            {fixes.length} finding{fixes.length !== 1 ? "s" : ""} with available automated fixes
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div>
              <div className="text-2xl font-semibold mb-1">
                {fixes.length}
              </div>
              <div className="text-sm text-muted-foreground">
                Proposed Fixes
              </div>
            </div>

            <div>
              <div className="text-2xl font-semibold mb-1">
                {fixes.reduce((sum, fix) => sum + fix.filesAffected, 0)}
              </div>
              <div className="text-sm text-muted-foreground">
                Files Affected
              </div>
            </div>

            <div>
              <div className="text-2xl font-semibold mb-1">-</div>
              <div className="text-sm text-muted-foreground">
                Est. Time
              </div>
            </div>

            <div>
              <div className="text-2xl font-semibold mb-1">-</div>
              <div className="text-sm text-muted-foreground">
                Risk Level
              </div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Fix Cards */}
      <div className="space-y-6 mb-6">
{loading ? (
  <Card>
    <CardContent className="p-8 text-center">
      <p className="text-muted-foreground">
        Generating proposed fixes...
      </p>
    </CardContent>
  </Card>
) : error ? (
  <Card>
    <CardContent className="p-8 text-center">
      <h3 className="font-semibold text-red-600 mb-2">
        Failed to generate fixes
      </h3>
      <p className="text-sm text-muted-foreground">
        {error}
      </p>
    </CardContent>
  </Card>
) : fixes.length === 0 ? (
    
    <Card>
      <CardContent className="p-8 text-center">
        <h3 className="font-semibold mb-2">No fixes available</h3>
        <p className="text-sm text-muted-foreground">
          PatchPilot couldn't generate any proposed fixes for the selected findings.
        </p>
      </CardContent>
    </Card>
  ) : (
    fixes.map((fix) => (
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

          {fix.diff ? (
            <DiffViewer
              diff={fix.diff}
              filename={fix.file}
              className="mb-4"
            />
          ) : (
            <Card className="mb-4">
              <CardContent className="pt-4">
                <p className="font-medium">{fix.summary}</p>

                {fix.notes.length > 0 && (
                  <ul className="list-disc ml-5 mt-2 space-y-1 text-sm text-muted-foreground">
                    {fix.notes.map((note: string, index: number) => (
                      <li key={index}>{note}</li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          )}
          <div className="flex flex-wrap gap-2">
            <Link to="/verify">
              <Button>Apply Patch</Button>
            </Link>
            <Button variant="outline" disabled>
              <GitPullRequest className="h-4 w-4 mr-2" />
              Open PR
              <Badge variant="secondary" className="ml-2 text-xs">
                Not configured
              </Badge>
            </Button>
            <Button variant="outline">
              <Copy className="h-4 w-4 mr-2" />
              Copy Patch
            </Button>
          </div>
        </CardContent>
      </Card>
    ))
  )}
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
              <Button variant="outline">
                <Download className="h-4 w-4 mr-2" />
                Download All
              </Button>
              <Link to="/verify">
                <Button disabled={selectedFixes.size === 0}>
                  Apply Selected Fixes
                </Button>
              </Link>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
