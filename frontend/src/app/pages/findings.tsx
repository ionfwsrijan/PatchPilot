import { useEffect, useMemo, useState } from "react";
import {
  Search,
  Filter,
  Download,
  Plus,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Card, CardContent } from "../components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "../components/ui/table";
import { Checkbox } from "../components/ui/checkbox";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "../components/ui/sheet";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "../components/ui/tabs";
import { SeverityChip } from "../components/severity-chip";
import { ToolBadge } from "../components/tool-badge";
import { CodeBlock } from "../components/code-block";
import { FilterChips } from "../components/filter-chips";
import type { Finding } from "../data/sample-data";
import { loadLastScan } from "../lib/scan-store";
import { mapBackendFindingToUi } from "../lib/mappers";
import { cn } from "../components/ui/utils";
import { downloadFindingsCsv } from "../lib/api";
import { saveBlob } from "../lib/download";

export function Findings() {
  const navigate = useNavigate();

  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const onExportCsv = async () => {
    if (!scan?.job_id) {
      setExportError("No active scan job found to export.");
      return;
    }
    setExporting(true);
    setExportError(null);
    try {
      const { blob, filename } = await downloadFindingsCsv(scan.job_id);
      saveBlob(blob, filename);
    } catch (e: any) {
      setExportError(e?.message || "Failed to export CSV report.");
    } finally {
      setExporting(false);
    }
  };

  const scan = useMemo(() => loadLastScan(), []);
  const findings: Finding[] = useMemo(
    () => (scan ? scan.findings.map(mapBackendFindingToUi) : []),
    [scan],
  );

  useEffect(() => {
    if (!scan) {
    }
  }, [scan, navigate]);

  const [selectedFindings, setSelectedFindings] = useState<Set<string>>(
    new Set(),
  );
  const [detailFinding, setDetailFinding] = useState<Finding | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [filters, setFilters] = useState([
    { id: "critical", label: "Critical", active: false },
    { id: "high", label: "High", active: false },
    { id: "medium", label: "Medium", active: false },
    { id: "low", label: "Low", active: false },
  ]);

  const toggleFinding = (id: string) => {
    const next = new Set(selectedFindings);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedFindings(next);
  };

  const toggleFilter = (id: string) => {
    setFilters((prev) =>
      prev.map((f) => (f.id === id ? { ...f, active: !f.active } : f)),
    );
  };

  const selectAll = () => {
    if (selectedFindings.size === findings.length) {
      setSelectedFindings(new Set());
    } else {
      setSelectedFindings(new Set(findings.map((f) => f.id)));
    }
  };

  const activeSeverities = useMemo(
    () => new Set(filters.filter((f) => f.active).map((f) => f.id)),
    [filters],
  );

  const filteredFindings = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();

    return findings.filter((f) => {
      const matchesQuery =
        q.length === 0 ||
        f.title.toLowerCase().includes(q) ||
        f.category.toLowerCase().includes(q) ||
        f.file.toLowerCase().includes(q);

      const matchesSeverity =
        activeSeverities.size === 0 || activeSeverities.has(f.severity);

      return matchesQuery && matchesSeverity;
    });
  }, [findings, searchQuery, activeSeverities]);

  if (!scan) {
    return (
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 max-w-7xl pb-20 md:pb-8">
        <div className="mb-6">
          <h1 className="mb-2">Findings</h1>
          <p className="text-muted-foreground">
            No scan results yet. Go to the Dashboard and upload a ZIP to start a
            scan.
          </p>
          <div className="mt-4">
            <Button onClick={() => navigate("/")}>Go to Dashboard</Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 max-w-7xl pb-20 md:pb-8">
      <div className="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="mb-2">Findings</h1>
          <p className="text-muted-foreground">
            {findings.length} vulnerabilities detected in {scan.project_name}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            onClick={onExportCsv}
            disabled={exporting}
            variant="outline"
            size="sm"
            className="w-full sm:w-auto"
          >
            <Download className="h-4 w-4 mr-2" />
            {exporting ? "Exporting CSV..." : "Export CSV"}
          </Button>
        </div>
      </div>

      {exportError && (
        <div className="p-3 mb-6 rounded-lg bg-destructive/10 text-destructive text-sm border border-destructive/20 font-medium">
          {exportError}
        </div>
      )}

      <Card className="mb-6">
        <CardContent className="p-4">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search findings..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9"
              />
            </div>
            <Button variant="outline">
              <Filter className="h-4 w-4 mr-2" />
              More Filters
            </Button>
          </div>
          <div className="mt-4">
            <FilterChips filters={filters} onToggle={toggleFilter} />
          </div>
        </CardContent>
      </Card>

      {selectedFindings.size > 0 && (
        <Card className="mb-4 bg-primary/5 border-primary/20">
          <CardContent className="p-4">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">
                {selectedFindings.size} finding
                {selectedFindings.size !== 1 ? "s" : ""} selected
              </span>
              <div className="flex gap-2">
                <Link to="/fix">
                  <Button size="sm">Propose Fixes</Button>
                </Link>
                <Button variant="outline" size="sm" disabled>
                  <Download className="h-4 w-4 mr-2" />
                  Export
                </Button>
                <Button variant="outline" size="sm" disabled>
                  <Plus className="h-4 w-4 mr-2" />
                  Add to Evidence
                </Button>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      <Card className="hidden md:block">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-12">
                <Checkbox
                  checked={
                    findings.length > 0 &&
                    selectedFindings.size === findings.length
                  }
                  onCheckedChange={selectAll}
                />
              </TableHead>
              <TableHead>Severity</TableHead>
              <TableHead>Title</TableHead>
              <TableHead>File</TableHead>
              <TableHead>Tool</TableHead>
              <TableHead className="text-right">Confidence</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredFindings.map((finding) => (
              <TableRow
                key={finding.id}
                className="cursor-pointer hover:bg-muted/50"
                onClick={() => setDetailFinding(finding)}
              >
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <Checkbox
                    checked={selectedFindings.has(finding.id)}
                    onCheckedChange={() => toggleFinding(finding.id)}
                  />
                </TableCell>
                <TableCell>
                  <SeverityChip severity={finding.severity} />
                </TableCell>
                <TableCell>
                  <div className="font-medium max-w-md truncate">
                    {finding.title}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {finding.category}
                  </div>
                </TableCell>
                <TableCell>
                  <div className="font-mono text-xs">{finding.file}</div>
                  <div className="text-xs text-muted-foreground">
                    Line {finding.lineNumber}
                  </div>
                </TableCell>
                <TableCell>
                  <ToolBadge tool={finding.tool} />
                </TableCell>
                <TableCell className="text-right">
                  <span className="text-sm font-medium">
                    {finding.confidence}%
                  </span>
                </TableCell>
                <TableCell>
                  <span
                    className={cn(
                      "inline-flex items-center gap-1 text-xs font-medium",
                      finding.status === "open" && "text-foreground",
                      finding.status === "accepted" && "text-status-success",
                      finding.status === "ignored" && "text-muted-foreground",
                    )}
                  >
                    {finding.status === "accepted" && (
                      <CheckCircle2 className="h-3 w-3" />
                    )}
                    {finding.status === "ignored" && (
                      <XCircle className="h-3 w-3" />
                    )}
                    {finding.status.charAt(0).toUpperCase() +
                      finding.status.slice(1)}
                  </span>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      <div className="md:hidden space-y-3">
        {filteredFindings.map((finding) => (
          <Card
            key={finding.id}
            className="hover:bg-muted/50 transition-colors cursor-pointer"
            onClick={() => setDetailFinding(finding)}
          >
            <CardContent className="p-4">
              <div className="flex items-start gap-3">
                <Checkbox
                  checked={selectedFindings.has(finding.id)}
                  onCheckedChange={() => toggleFinding(finding.id)}
                  onClick={(e) => e.stopPropagation()}
                />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-2">
                    <SeverityChip severity={finding.severity} />
                    <ToolBadge tool={finding.tool} />
                  </div>
                  <div className="font-medium mb-1 line-clamp-2">
                    {finding.title}
                  </div>
                  <div className="text-xs text-muted-foreground font-mono truncate">
                    {finding.file}:{finding.lineNumber}
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Sheet open={!!detailFinding} onOpenChange={() => setDetailFinding(null)}>
        <SheetContent className="w-full sm:max-w-2xl overflow-y-auto">
          {detailFinding && (
            <>
              <SheetHeader>
                <SheetTitle>{detailFinding.title}</SheetTitle>
              </SheetHeader>

              <div className="mt-6 space-y-6">
                <div className="flex flex-wrap gap-2">
                  <SeverityChip severity={detailFinding.severity} />
                  <ToolBadge tool={detailFinding.tool} />
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border border-border text-xs font-medium">
                    {detailFinding.confidence}% confidence
                  </span>
                </div>

                <Tabs defaultValue="details" className="w-full">
                  <TabsList className="w-full">
                    <TabsTrigger value="details" className="flex-1">
                      Details
                    </TabsTrigger>
                    <TabsTrigger value="fix" className="flex-1">
                      Suggested Fix
                    </TabsTrigger>
                    <TabsTrigger value="references" className="flex-1">
                      References
                    </TabsTrigger>
                  </TabsList>

                  <TabsContent value="details" className="space-y-4">
                    <div>
                      <h4 className="mb-2">Description</h4>
                      <p className="text-sm text-muted-foreground">
                        {detailFinding.description}
                      </p>
                    </div>

                    <div>
                      <h4 className="mb-2">Location</h4>
                      <div className="text-sm">
                        <div className="font-mono text-xs mb-1">
                          {detailFinding.file}
                        </div>
                        <div className="text-muted-foreground">
                          Line {detailFinding.lineNumber}
                        </div>
                      </div>
                    </div>

                    <div>
                      <h4 className="mb-3">Code Evidence</h4>
                      <CodeBlock
                        code={detailFinding.code}
                        language="typescript"
                        startLine={detailFinding.lineNumber}
                        highlightLines={[detailFinding.lineNumber + 1]}
                      />
                    </div>
                  </TabsContent>

                  <TabsContent value="fix" className="space-y-4">
                    {detailFinding.suggestedFix ? (
                      <>
                        <p className="text-sm text-muted-foreground">
                          Recommended code change to address this vulnerability:
                        </p>
                        <CodeBlock
                          code={detailFinding.suggestedFix}
                          language="typescript"
                          startLine={detailFinding.lineNumber}
                        />
                        <div className="flex gap-2">
                          <Link to="/fix">
                            <Button>Apply Fix</Button>
                          </Link>
                          <Button variant="outline" disabled>
                            Copy Patch
                          </Button>
                        </div>
                      </>
                    ) : (
                      <p className="text-sm text-muted-foreground">
                        No automated fix available for this finding.
                      </p>
                    )}
                  </TabsContent>

                  <TabsContent value="references" className="space-y-4">
                    {detailFinding.references &&
                    detailFinding.references.length > 0 ? (
                      <ul className="space-y-2">
                        {detailFinding.references.map((ref, index) => (
                          <li key={index} className="text-sm">
                            <a
                              href="#"
                              className="text-primary hover:underline"
                            >
                              {ref}
                            </a>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="text-sm text-muted-foreground">
                        No references available.
                      </p>
                    )}
                  </TabsContent>
                </Tabs>

                <div className="flex gap-2 pt-4 border-t border-border">
                  <Button variant="outline" className="flex-1" disabled>
                    <CheckCircle2 className="h-4 w-4 mr-2" />
                    Accept
                  </Button>
                  <Button variant="outline" className="flex-1" disabled>
                    <XCircle className="h-4 w-4 mr-2" />
                    Ignore
                  </Button>
                </div>
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
