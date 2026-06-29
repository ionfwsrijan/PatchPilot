import { useEffect, useMemo, useState, useRef } from "react";
import {
  Search,
  Filter,
  Download,
  Plus,
  CheckCircle2,
  XCircle,
  Loader2,
  AlertTriangle,
  ThumbsUp,
  ThumbsDown,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { downloadAuditReport } from "../lib/api";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
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
  SheetDescription,
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
import { getJobFindings, updateFindingStatus, labelFinding } from "../lib/api";

type UiFinding = Finding & { false_positive?: boolean | null, version?: number };
import { mapBackendFindingToUi } from "../lib/mappers";
import { cn } from "../components/ui/utils";

function ExportReportButton({ scanId }: { scanId: string }) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [status, setStatus] = useState<"idle" | "success" | "error">("idle");

  const handleDownload = async () => {
    setIsGenerating(true);
    setStatus("idle");

    try {
      const { blob, filename } = await downloadAuditReport(scanId);
      
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(url);

      setStatus("success");
      setTimeout(() => setStatus("idle"), 4000);
    } catch (error) {
      setStatus("error");
      setTimeout(() => setStatus("idle"), 5000);
    } finally {
      setIsGenerating(false);
    }
  };

  return (
    <div className="relative inline-block text-left">
      <Button
        variant="outline"
        onClick={handleDownload}
        disabled={isGenerating}
        className="flex items-center gap-2"
      >
        {isGenerating ? (
          <Loader2 className="w-4 h-4 animate-spin" />
        ) : (
          <Download className="w-4 h-4" />
        )}
        {isGenerating ? "Generating..." : "Export Audit PDF"}
      </Button>

      {status === "success" && (
        <div className="absolute top-full right-0 mt-2 z-50 flex items-center gap-2 p-3 bg-slate-900 border border-emerald-800 text-slate-200 shadow-xl rounded min-w-[220px] animate-in fade-in slide-in-from-top-2">
          <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
          <div className="flex flex-col">
            <span className="text-xs font-semibold text-slate-200">Report Downloaded</span>
          </div>
        </div>
      )}

      {status === "error" && (
        <div className="absolute top-full right-0 mt-2 z-50 flex items-center gap-2 p-3 bg-slate-900 border border-rose-800 text-slate-200 shadow-xl rounded min-w-[220px] animate-in fade-in slide-in-from-top-2">
          <AlertTriangle className="w-4 h-4 text-rose-500 shrink-0" />
          <div className="flex flex-col">
            <span className="text-xs font-semibold text-slate-200">Export Failed</span>
          </div>
        </div>
      )}
    </div>
  );
}

export function MlScorePill({ score }: { score: number }) {
  const percentage = Math.round(score * 100);

  let colorClasses = "";
  if (score >= 0.75) {
    colorClasses = "bg-rose-500/10 border-rose-500/20 text-rose-600 dark:bg-rose-500/20 dark:border-rose-500/30 dark:text-rose-400";
  } else if (score >= 0.5) {
    colorClasses = "bg-amber-500/10 border-amber-500/20 text-amber-600 dark:bg-amber-500/20 dark:border-amber-500/30 dark:text-amber-400";
  } else {
    colorClasses = "bg-slate-500/10 border-slate-500/20 text-slate-600 dark:bg-slate-500/20 dark:border-slate-500/30 dark:text-slate-400";
  }

  return (
    <span
      className={cn(
        "inline-flex items-center px-1.5 py-0.5 rounded border text-[10px] font-bold font-mono tracking-wide shadow-sm select-none",
        colorClasses
      )}
    >
      {percentage}%
    </span>
  );
}

export function Findings() {
  const navigate = useNavigate();

  const [scan, setScan] = useState<any>(null);
  const [findings, setFindings] = useState<UiFinding[]>([]);
  const [isLoadingFindings, setIsLoadingFindings] = useState(true);

  useEffect(() => {
    const storedScan = loadLastScan();
    if (!storedScan?.job_id) {
      setIsLoadingFindings(false);
      return;
    }
    setScan(storedScan);
    getJobFindings(storedScan.job_id)
      .then((response: any) => {
        const actualFindings = Array.isArray(response) 
          ? response 
          : (response.findings || response.data || []);
          
        setFindings(actualFindings.map((bf: any) => ({
          ...mapBackendFindingToUi(bf),
          false_positive: bf.false_positive === 1 || bf.false_positive === true ? true : (bf.false_positive === 0 || bf.false_positive === false ? false : null)
        })));
      })
      .catch((err) => console.error("Failed to fetch findings", err))
      .finally(() => setIsLoadingFindings(false));
  }, []);

  const [selectedFindings, setSelectedFindings] = useState<Set<string>>(new Set());
  const [detailFinding, setDetailFinding] = useState<UiFinding | null>(null);
  const [isUpdatingStatus, setIsUpdatingStatus] = useState(false);
  const [sortBy, setSortBy] = useState<"severity" | "ml_score">("severity");
  
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 50;
  const abortControllers = useRef<Record<string, AbortController>>({});
  const [labelingId, setLabelingId] = useState<string | null>(null);

  const handleLabelFalsePositive = async (findingId: string, isFalsePositive: boolean, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    
    if (abortControllers.current[findingId]) {
      abortControllers.current[findingId].abort();
    }
    const controller = new AbortController();
    abortControllers.current[findingId] = controller;
    
    const previousFinding = findings.find(f => f.id === findingId);
    const previousValue = previousFinding?.false_positive;
    const currentVersion = previousFinding?.version || 1;

    setLabelingId(findingId);
    setFindings((prev) => prev.map((f) => f.id === findingId ? { ...f, false_positive: isFalsePositive } : f));
    if (detailFinding && detailFinding.id === findingId) {
      setDetailFinding((prev) => prev ? { ...prev, false_positive: isFalsePositive } : null);
    }
    
    try {
      await labelFinding(findingId, isFalsePositive, currentVersion, controller.signal);
      setFindings((prev) => prev.map((f) => f.id === findingId ? { ...f, version: currentVersion + 1 } : f));
      if (detailFinding && detailFinding.id === findingId) {
        setDetailFinding((prev) => prev ? { ...prev, version: currentVersion + 1 } : null);
      }
    } catch (err: any) {
      if (err.name === 'AbortError') return;
      
      console.error("Failed to label finding", err);
      setFindings((prev) => prev.map((f) => f.id === findingId ? { ...f, false_positive: previousValue } : f));
      if (detailFinding && detailFinding.id === findingId) {
        setDetailFinding((prev) => prev ? { ...prev, false_positive: previousValue } : null);
      }
      
      if (err.message?.includes('409') || err.status === 409) {
        alert("This finding has been modified by another user. Your changes were not saved.");
      } else {
        alert("Failed to update finding label. Please try again.");
      }
    } finally {
      setLabelingId((prev) => prev === findingId ? null : prev);
    }
  };

  const handleStatusUpdate = async (findingId: string, newStatus: "open" | "accepted" | "ignored") => {
    setIsUpdatingStatus(true);
    try {
      await updateFindingStatus(findingId, newStatus);
      setFindings((prev) => 
        prev.map((f) => f.id === findingId ? { ...f, status: newStatus } : f)
      );
      if (detailFinding && detailFinding.id === findingId) {
        setDetailFinding({ ...detailFinding, status: newStatus });
      }
    } catch (err) {
      console.error("Failed to update status", err);
    } finally {
      setIsUpdatingStatus(false);
    }
  };

  const [searchParams, setSearchParams] = useSearchParams();

  const [searchQuery, setSearchQuery] = useState(() =>
    (searchParams.get("q") ?? "").toString(),
  );

  const baseFilters = [
    { id: "critical", label: "Critical", active: false },
    { id: "high", label: "High", active: false },
    { id: "medium", label: "Medium", active: false },
    { id: "low", label: "Low", active: false },
  ];

  const [filters, setFilters] = useState(() => {
    const param = searchParams.get("severity");
    const active = new Set(param ? param.split(",") : []);
    return baseFilters.map((f) => ({ ...f, active: active.has(f.id) }));
  });

  const toggleFinding = (id: string) => {
    const next = new Set(selectedFindings);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelectedFindings(next);
  };

  const toggleFilter = (id: string) => {
    setFilters((prev) => {
      const next = prev.map((f) => (f.id === id ? { ...f, active: !f.active } : f));
      const activeIds = next.filter((f) => f.active).map((f) => f.id);
      const params = new URLSearchParams();
      if (activeIds.length) params.set("severity", activeIds.join(","));
      if (searchQuery.trim()) params.set("q", searchQuery.trim());
      setSearchParams(params, { replace: true });
      return next;
    });
  };

  const updateQueryParam = (q: string) => {
    setSearchQuery(q);
    const activeIds = filters.filter((f) => f.active).map((f) => f.id);
    const params = new URLSearchParams();
    if (activeIds.length) params.set("severity", activeIds.join(","));
    if (q.trim()) params.set("q", q.trim());
    setSearchParams(params, { replace: true });
  };

  const selectAll = () => {
    if (selectedFindings.size === findings.length) {
      setSelectedFindings(new Set());
    } else {
      setSelectedFindings(new Set(findings.map((f) => f.id)));
    }
  };

  const [isFilterSheetOpen, setIsFilterSheetOpen] = useState(false);
  const [selectedStatuses, setSelectedStatuses] = useState<Set<string>>(new Set());
  const [selectedTools, setSelectedTools] = useState<Set<string>>(new Set());

  const availableTools = useMemo(() => Array.from(new Set(findings.map(f => f.tool).filter(Boolean))), [findings]);
  const availableStatuses = ["open", "accepted", "ignored"];

  const activeSeverities = useMemo(
    () => new Set(filters.filter((f) => f.active).map((f) => f.id)),
    [filters],
  );

  useEffect(() => {
    setCurrentPage(1);
  }, [searchQuery, filters, sortBy, selectedStatuses, selectedTools]);

  const filteredFindings = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();

    const filtered = findings.filter((f) => {
      const matchesQuery =
        q.length === 0 ||
        f.title.toLowerCase().includes(q) ||
        f.category.toLowerCase().includes(q) ||
        (f.file ?? "").toLowerCase().includes(q);

      const matchesSeverity =
        activeSeverities.size === 0 || activeSeverities.has(f.severity);
        
      const matchesStatus = 
        selectedStatuses.size === 0 || selectedStatuses.has(f.status);
        
      const matchesTool = 
        selectedTools.size === 0 || selectedTools.has(f.tool);

      return matchesQuery && matchesSeverity && matchesStatus && matchesTool;
    });

    const severityOrder: Record<string, number> = {
      critical: 4,
      high: 3,
      medium: 2,
      low: 1,
      info: 0,
    };

    if (sortBy === "ml_score") {
      filtered.sort((a, b) => {
        const scoreA = a.ml_score ?? 0;
        const scoreB = b.ml_score ?? 0;
        if (scoreB !== scoreA) {
          return scoreB - scoreA;
        }
        // secondary sort: severity
        const sevA = severityOrder[a.severity] ?? 0;
        const sevB = severityOrder[b.severity] ?? 0;
        return sevB - sevA;
      });
    } else {
      filtered.sort((a, b) => {
        const sevA = severityOrder[a.severity] ?? 0;
        const sevB = severityOrder[b.severity] ?? 0;
        if (sevB !== sevA) {
          return sevB - sevA;
        }
        // secondary sort: ml_score
        const scoreA = a.ml_score ?? 0;
        const scoreB = b.ml_score ?? 0;
        return scoreB - scoreA;
      });
    }

    return filtered;
  }, [findings, searchQuery, activeSeverities, sortBy, selectedStatuses, selectedTools]);

  if (isLoadingFindings) {
    return (
      <div className="container mx-auto px-4 py-8 max-w-7xl flex justify-center items-center h-64">
        <div className="flex flex-col items-center gap-4 text-muted-foreground">
          <Loader2 className="h-8 w-8 animate-spin text-primary" />
          <p>Loading scan results...</p>
        </div>
      </div>
    );
  }

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
            <Button onClick={() => navigate("/dashboard")}>Go to Dashboard</Button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 max-w-7xl pb-20 md:pb-8">
      <div className="mb-6 flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="mb-2">Findings</h1>
          <p className="text-muted-foreground">
            {findings.length} vulnerabilities detected in {scan.project_name}
          </p>
        </div>
        <ExportReportButton scanId={scan.job_id} />
      </div>

      <Card className="mb-6">
        <CardContent className="p-4">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Search findings..."
                value={searchQuery}
                onChange={(e) => updateQueryParam(e.target.value)}
                className="pl-9"
              />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <div className="inline-flex items-center rounded-lg border border-border bg-muted/20 p-1 text-muted-foreground">
                <button
                  type="button"
                  onClick={() => setSortBy("severity")}
                  className={cn(
                    "inline-flex items-center justify-center rounded-md px-3 py-1.5 text-xs font-semibold ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 cursor-pointer",
                    sortBy === "severity"
                      ? "bg-background text-foreground shadow-sm"
                      : "hover:bg-muted/50 hover:text-foreground"
                  )}
                >
                  Severity
                </button>
                <button
                  type="button"
                  onClick={() => setSortBy("ml_score")}
                  className={cn(
                    "inline-flex items-center justify-center rounded-md px-3 py-1.5 text-xs font-semibold ring-offset-background transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50 cursor-pointer",
                    sortBy === "ml_score"
                      ? "bg-background text-foreground shadow-sm"
                      : "hover:bg-muted/50 hover:text-foreground"
                  )}
                >
                  ML Score
                </button>
              </div>
              <Button variant="outline" onClick={() => setIsFilterSheetOpen(true)}>
                <Filter className="h-4 w-4 mr-2" />
                More Filters
              </Button>
            </div>
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
              <TableHead className="text-center" title="Mark as True Positive or False Positive">Label ⓘ</TableHead>
              <TableHead className="text-right">Confidence</TableHead>
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filteredFindings.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage).map((finding) => (
              <TableRow
                key={finding.id}
                className={cn("cursor-pointer hover:bg-muted/50", finding.false_positive && "opacity-60 bg-muted/20")}
                onClick={() => setDetailFinding(finding)}
              >
                <TableCell onClick={(e) => e.stopPropagation()}>
                  <Checkbox
                    checked={selectedFindings.has(finding.id)}
                    onCheckedChange={() => toggleFinding(finding.id)}
                  />
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-2">
                    <SeverityChip severity={finding.severity} />
                    {finding.ml_score !== undefined && finding.ml_score !== null && (
                      <MlScorePill score={finding.ml_score} />
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  <div className="font-medium max-w-md truncate flex items-center gap-2">
                    {finding.title}
                    {finding.false_positive && (
                      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-rose-500/10 text-rose-500 border border-rose-500/20 shrink-0">
                        FP
                      </span>
                    )}
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
                <TableCell className="text-center">
                  <div className="flex items-center justify-center gap-1" onClick={(e) => e.stopPropagation()}>
                    <Button variant="ghost" size="icon" disabled={labelingId === finding.id} className={cn("h-7 w-7", finding.false_positive === false && "text-emerald-500 bg-emerald-500/10 hover:bg-emerald-500/20 hover:text-emerald-500")} onClick={(e) => handleLabelFalsePositive(finding.id, false, e)} title="True Positive">
                      <ThumbsUp className="h-3.5 w-3.5" />
                    </Button>
                    <Button variant="ghost" size="icon" disabled={labelingId === finding.id} className={cn("h-7 w-7", finding.false_positive === true && "text-rose-500 bg-rose-500/10 hover:bg-rose-500/20 hover:text-rose-500")} onClick={(e) => handleLabelFalsePositive(finding.id, true, e)} title="False Positive">
                      <ThumbsDown className="h-3.5 w-3.5" />
                    </Button>
                  </div>
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
        {filteredFindings.slice((currentPage - 1) * itemsPerPage, currentPage * itemsPerPage).map((finding) => (
          <Card
            key={finding.id}
            className={cn("hover:bg-muted/50 transition-colors cursor-pointer", finding.false_positive && "opacity-60 bg-muted/20")}
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
                  <div className="flex items-center flex-wrap gap-2 mb-2">
                    <SeverityChip severity={finding.severity} />
                    {finding.ml_score !== undefined && finding.ml_score !== null && (
                      <MlScorePill score={finding.ml_score} />
                    )}
                    <ToolBadge tool={finding.tool} />
                    {finding.false_positive && (
                      <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-rose-500/10 text-rose-500 border border-rose-500/20">
                        FP
                      </span>
                    )}
                  </div>
                  <div className="font-medium mb-1 line-clamp-2">
                    {finding.title}
                  </div>
                  <div className="text-xs text-muted-foreground font-mono truncate">
                    {finding.file}:{finding.lineNumber}
                  </div>
                </div>
              </div>
              
              <div className="flex items-center justify-end mt-3 pt-3 border-t border-border/50">
                <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                  <span className="text-xs text-muted-foreground mr-2" title="Mark as True Positive or False Positive">Accurate? ⓘ</span>
                  <Button variant="ghost" size="icon" disabled={labelingId === finding.id} aria-label="True Positive" title="True Positive" className={cn("h-7 w-7", finding.false_positive === false && "text-emerald-500 bg-emerald-500/10 hover:bg-emerald-500/20 hover:text-emerald-500")} onClick={(e) => handleLabelFalsePositive(finding.id, false, e)}>
                    <ThumbsUp className="h-3.5 w-3.5" />
                  </Button>
                  <Button variant="ghost" size="icon" disabled={labelingId === finding.id} aria-label="False Positive" title="False Positive" className={cn("h-7 w-7", finding.false_positive === true && "text-rose-500 bg-rose-500/10 hover:bg-rose-500/20 hover:text-rose-500")} onClick={(e) => handleLabelFalsePositive(finding.id, true, e)}>
                    <ThumbsDown className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {Math.ceil(filteredFindings.length / itemsPerPage) > 1 && (
        <Card className="mt-4">
          <CardContent className="flex items-center justify-between p-4">
            <span className="text-sm text-muted-foreground">
              Showing {((currentPage - 1) * itemsPerPage) + 1} to {Math.min(currentPage * itemsPerPage, filteredFindings.length)} of {filteredFindings.length} findings
            </span>
            <div className="flex items-center gap-2">
              <Button 
                variant="outline" 
                size="sm" 
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
              >
                <ChevronLeft className="h-4 w-4 mr-1" /> Prev
              </Button>
              <span className="text-sm font-medium px-2">Page {currentPage} of {Math.ceil(filteredFindings.length / itemsPerPage)}</span>
              <Button 
                variant="outline" 
                size="sm" 
                onClick={() => setCurrentPage(p => Math.min(Math.ceil(filteredFindings.length / itemsPerPage), p + 1))}
                disabled={currentPage === Math.ceil(filteredFindings.length / itemsPerPage)}
              >
                Next <ChevronRight className="h-4 w-4 ml-1" />
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

    <Sheet open={!!detailFinding} onOpenChange={() => setDetailFinding(null)}>
        <SheetContent className="w-full sm:max-w-2xl overflow-y-auto flex flex-col p-6 sm:p-8">
          {detailFinding && (
            <>
              <SheetHeader className="pb-4 border-b border-border/50">
                <SheetTitle className="text-xl font-semibold tracking-tight flex items-center flex-wrap gap-3">
                  {detailFinding.title}
                  {detailFinding.false_positive && (
                    <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-rose-500/10 text-rose-500 border border-rose-500/20">
                      Marked as False Positive
                    </span>
                  )}
                </SheetTitle>
                <SheetDescription className="text-sm text-muted-foreground mt-1">
                  Finding ID: <span className="font-mono">{detailFinding.id}</span>
                </SheetDescription>
              </SheetHeader>

              <div className="flex-1 overflow-y-auto mt-6 space-y-8">
                <div className="flex flex-wrap items-center gap-3">
                  <SeverityChip severity={detailFinding.severity} />
                  {detailFinding.ml_score !== undefined && detailFinding.ml_score !== null && (
                    <MlScorePill score={detailFinding.ml_score} />
                  )}
                  <ToolBadge tool={detailFinding.tool} />
                  <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md bg-muted/30 text-muted-foreground text-[11px] font-bold uppercase tracking-wider">
                    {detailFinding.confidence}% Confidence
                  </span>
                </div>

                <Tabs defaultValue="details" className="w-full flex flex-col gap-6">
                  <TabsList className="w-full grid grid-cols-3 bg-muted/20 p-1 rounded-lg">
                    <TabsTrigger value="details" className="rounded-md data-[state=active]:bg-background data-[state=active]:shadow-sm">Details</TabsTrigger>
                    <TabsTrigger value="fix" className="rounded-md data-[state=active]:bg-background data-[state=active]:shadow-sm">Suggested Fix</TabsTrigger>
                    <TabsTrigger value="references" className="rounded-md data-[state=active]:bg-background data-[state=active]:shadow-sm">References</TabsTrigger>
                  </TabsList>

                  <TabsContent value="details" className="flex flex-col gap-8 animate-in fade-in duration-300 mt-0 outline-none">
                    <div className="flex flex-col gap-3">
                      <h4 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground">Description</h4>
                      <div className="bg-muted/5 rounded-lg p-5 border border-border/40 shadow-sm">
                        <p className="text-sm leading-relaxed text-foreground/90">
                          {detailFinding.description}
                        </p>
                      </div>
                    </div>

                    <div className="flex flex-col gap-3">
                      <h4 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground">Location</h4>
                      <div className="bg-muted/5 rounded-lg p-5 border border-border/40 flex flex-col gap-2 shadow-sm">
                        <div className="font-mono text-sm text-primary break-all">
                          {detailFinding.file}
                        </div>
                        <div className="text-sm text-muted-foreground font-medium">
                          Line {detailFinding.lineNumber}
                        </div>
                      </div>
                    </div>

                    <div className="flex flex-col gap-3">
                      <h4 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground">Code Evidence</h4>
                      <div className="rounded-lg overflow-hidden border border-border/40 shadow-sm bg-muted/5">
                        <CodeBlock
                          code={detailFinding.code}
                          language="typescript"
                          startLine={detailFinding.lineNumber}
                          highlightLines={[detailFinding.lineNumber + 1]}
                        />
                      </div>
                    </div>
                  </TabsContent>

                  <TabsContent value="fix" className="flex flex-col gap-6 animate-in fade-in duration-300 mt-0 outline-none">
                    {detailFinding.suggestedFix ? (
                      <>
                        <div className="flex flex-col gap-3">
                          <h4 className="text-[11px] font-bold uppercase tracking-widest text-muted-foreground">Recommended Patch</h4>
                          <div className="rounded-lg overflow-hidden border border-border/40 shadow-sm bg-muted/5">
                            <CodeBlock
                              code={detailFinding.suggestedFix}
                              language="typescript"
                              startLine={detailFinding.lineNumber}
                            />
                          </div>
                        </div>
                        <div className="flex gap-3 mt-2">
                          <Link to="/fix" className="flex-1">
                            <Button className="w-full shadow-sm">Apply Fix</Button>
                          </Link>
                          <Button variant="outline" disabled className="flex-1 bg-muted/5">
                            Copy Patch
                          </Button>
                        </div>
                      </>
                    ) : (
                      <div className="flex flex-col items-center justify-center py-16 text-center border rounded-lg border-dashed border-border/60 bg-muted/5">
                        <p className="text-sm text-muted-foreground font-medium">No automated fix available for this finding.</p>
                      </div>
                    )}
                  </TabsContent>

                  <TabsContent value="references" className="flex flex-col gap-4 animate-in fade-in duration-300 mt-0 outline-none">
                    {detailFinding.references && detailFinding.references.length > 0 ? (
                      <ul className="flex flex-col gap-3">
                        {detailFinding.references.map((ref, index) => (
                          <li key={index} className="group flex items-start gap-3 p-4 rounded-lg border border-border/40 bg-muted/5 hover:bg-muted/10 transition-colors shadow-sm">
                            <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-primary/50 shrink-0 group-hover:bg-primary transition-colors" />
                            <a
                              href={ref}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-sm text-primary hover:text-primary/80 font-medium break-all flex-1 leading-relaxed"
                            >
                              {ref}
                            </a>
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <div className="flex flex-col items-center justify-center py-16 text-center border rounded-lg border-dashed border-border/60 bg-muted/5">
                        <p className="text-sm text-muted-foreground font-medium">No external references provided.</p>
                      </div>
                    )}
                  </TabsContent>
                </Tabs>
              </div>

            {/* ML Labeling Section */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pt-6 mt-6 border-t border-border/50 shrink-0">
                <div className="flex flex-col">
                  <span className="text-sm font-semibold">Label for ML Training</span>
                  <span className="text-xs text-muted-foreground">Help improve the false positive classifier.</span>
                </div>
                <div className="flex items-center gap-2">
                  <Button variant="outline" size="sm" disabled={labelingId === detailFinding.id} className={cn(detailFinding.false_positive === false && "border-emerald-500 text-emerald-500 bg-emerald-500/10 hover:bg-emerald-500/20 hover:text-emerald-500")} onClick={() => handleLabelFalsePositive(detailFinding.id, false)}>
                    <ThumbsUp className="h-4 w-4 mr-2" />
                    True Positive
                  </Button>
                  <Button variant="outline" size="sm" disabled={labelingId === detailFinding.id} className={cn(detailFinding.false_positive === true && "border-rose-500 text-rose-500 bg-rose-500/10 hover:bg-rose-500/20 hover:text-rose-500")} onClick={() => handleLabelFalsePositive(detailFinding.id, true)}>
                    <ThumbsDown className="h-4 w-4 mr-2" />
                    False Positive
                  </Button>
                </div>
              </div>

            {/* Status Buttons - Dynamic and clickable */}
              <div className="flex gap-3 pt-4 shrink-0">
                {detailFinding.status === 'accepted' ? (
                   <Button 
                    variant="outline" 
                    className="flex-1 border-status-success text-status-success bg-status-success/10 hover:bg-status-success/20 hover:text-status-success"
                    onClick={() => handleStatusUpdate(detailFinding.id, 'open')}
                    disabled={isUpdatingStatus}
                  >
                    {isUpdatingStatus ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <CheckCircle2 className="h-4 w-4 mr-2" />}
                    Accepted (Click to Re-open)
                  </Button>
                ) : (
                  <Button 
                    variant="outline" 
                    className="flex-1 hover:bg-status-success/10 hover:text-status-success hover:border-status-success/50 transition-colors"
                    onClick={() => handleStatusUpdate(detailFinding.id, 'accepted')}
                    disabled={isUpdatingStatus}
                  >
                    {isUpdatingStatus ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <CheckCircle2 className="h-4 w-4 mr-2" />}
                    Accept Risk
                  </Button>
                )}

                {detailFinding.status === 'ignored' ? (
                   <Button 
                    variant="outline" 
                    className="flex-1 border-muted-foreground text-muted-foreground bg-muted hover:bg-muted/80"
                    onClick={() => handleStatusUpdate(detailFinding.id, 'open')}
                    disabled={isUpdatingStatus}
                  >
                    {isUpdatingStatus ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <XCircle className="h-4 w-4 mr-2" />}
                    Ignored (Click to Re-open)
                  </Button>
                ) : (
                  <Button 
                    variant="outline" 
                    className="flex-1 hover:bg-muted/50 transition-colors"
                    onClick={() => handleStatusUpdate(detailFinding.id, 'ignored')}
                    disabled={isUpdatingStatus}
                  >
                    {isUpdatingStatus ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <XCircle className="h-4 w-4 mr-2" />}
                    Ignore Finding
                  </Button>
                )}
              </div>
            </>
          )}
    </SheetContent>
      </Sheet>

      <Sheet open={isFilterSheetOpen} onOpenChange={setIsFilterSheetOpen}>
        <SheetContent side="right" className="w-full sm:max-w-md p-6">
          <SheetHeader className="pb-4 border-b border-border/50">
            <SheetTitle>Advanced Filters</SheetTitle>
            <SheetDescription>Filter findings by status and tool</SheetDescription>
          </SheetHeader>
          
          <div className="py-6 space-y-8">
            <div className="space-y-4">
              <h3 className="text-sm font-semibold tracking-tight">Status</h3>
              <div className="space-y-3">
                {availableStatuses.map(status => (
                  <div key={status} className="flex items-center space-x-3">
                    <Checkbox
                      id={`status-${status}`}
                      checked={selectedStatuses.has(status)}
                      onCheckedChange={(checked) => {
                        const next = new Set(selectedStatuses);
                        if (checked) next.add(status);
                        else next.delete(status);
                        setSelectedStatuses(next);
                      }}
                    />
                    <label htmlFor={`status-${status}`} className="text-sm font-medium leading-none capitalize">
                      {status}
                    </label>
                  </div>
                ))}
              </div>
            </div>

            <div className="space-y-4">
              <h3 className="text-sm font-semibold tracking-tight">Tool</h3>
              <div className="space-y-3">
                {availableTools.map(tool => (
                  <div key={tool} className="flex items-center space-x-3">
                    <Checkbox
                      id={`tool-${tool}`}
                      checked={selectedTools.has(tool)}
                      onCheckedChange={(checked) => {
                        const next = new Set(selectedTools);
                        if (checked) next.add(tool);
                        else next.delete(tool);
                        setSelectedTools(next);
                      }}
                    />
                    <label htmlFor={`tool-${tool}`} className="text-sm font-medium leading-none capitalize">
                      {tool}
                    </label>
                  </div>
                ))}
              </div>
            </div>

            <div className="pt-4 border-t border-border/50">
              <Button 
                variant="outline" 
                className="w-full"
                onClick={() => {
                  setSelectedStatuses(new Set());
                  setSelectedTools(new Set());
                }}
              >
                Clear All Advanced Filters
              </Button>
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
