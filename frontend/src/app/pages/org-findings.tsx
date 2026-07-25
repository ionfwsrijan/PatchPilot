import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, Building2, ShieldAlert, CheckCircle, XCircle, Filter, Download, Loader2, ChevronLeft, ChevronRight, Network } from "lucide-react";
import { getOrgSummary, getOrgFindings, downloadOrgAuditReport } from "../lib/api";
import { saveBlob } from "../lib/download";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../components/ui/table";
import { BlastRadiusGraph } from "../components/blast-radius-graph";

const getSeverityColor = (sev: string) => {
  switch (sev?.toLowerCase()) {
    case "critical": return "bg-rose-500/10 text-rose-500 border-rose-500/20";
    case "high": return "bg-orange-500/10 text-orange-500 border-orange-500/20";
    case "medium": return "bg-amber-500/10 text-amber-500 border-amber-500/20";
    case "low": return "bg-blue-500/10 text-blue-500 border-blue-500/20";
    default: return "bg-slate-500/10 text-slate-500 border-slate-500/20";
  }
};

export function OrgFindings() {
  const { orgJobId } = useParams<{ orgJobId: string }>();
  const navigate = useNavigate();

  const [summary, setSummary] = useState<any>(null);
  const [findings, setFindings] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [exporting, setExporting] = useState(false);
  const [repoFilter, setRepoFilter] = useState<string>("ALL");
  const [currentPage, setCurrentPage] = useState(1);
  const [showGraph, setShowGraph] = useState(false);
  const itemsPerPage = 50;

  useEffect(() => {
    setCurrentPage(1);
  }, [repoFilter]);

  useEffect(() => {
    if (!orgJobId) return;
    
    async function fetchData() {
      try {
        const [sumData, findData] = await Promise.all([
          getOrgSummary(orgJobId!),
          getOrgFindings(orgJobId!)
        ]);
        setSummary(sumData);
        setFindings(findData);
      } catch (err) {
        console.error("Failed to load org data", err);
      } finally {
        setLoading(false);
      }
    }
    
    fetchData();
  }, [orgJobId]);

  const handleExportPDF = async () => {
    if (!orgJobId) return;
    try {
      setExporting(true);
      const { blob, filename } = await downloadOrgAuditReport(orgJobId);
      saveBlob(blob, filename);
    } catch (err) {
      console.error("Failed to export PDF", err);
      alert("Failed to generate PDF. Please try again.");
    } finally {
      setExporting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-[50vh] items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
      </div>
    );
  }

  if (!summary) {
    return (
      <div className="container mx-auto p-8 text-center text-muted-foreground">
        Failed to load organization data.
      </div>
    );
  }

  const uniqueRepos = Array.from(new Set(findings.map(f => f.repo_name)));
  const filteredFindings = repoFilter === "ALL" 
    ? findings 
    : findings.filter(f => f.repo_name === repoFilter);
  const totalPages = Math.ceil(filteredFindings.length / itemsPerPage);
  const paginatedFindings = filteredFindings.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  return (
    <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8 max-w-7xl pb-20 md:pb-8 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-8">
        <div className="flex items-center gap-4">
          <Button variant="ghost" size="icon" onClick={() => navigate("/dashboard")} className="cursor-pointer">
            <ArrowLeft className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Building2 className="h-6 w-6 text-primary" />
              Organization Security Posture
            </h1>
            <p className="text-muted-foreground text-sm">
              Aggregate vulnerability data across {summary.total_repositories} repositories.
            </p>
          </div>
        </div>
        
        <div className="flex items-center gap-3">
          <Button 
            variant="outline"
            onClick={() => setShowGraph(!showGraph)}
            className="shadow-sm transition-all cursor-pointer border-slate-700 bg-slate-900 text-slate-100 hover:bg-slate-800"
          >
            <Network className="mr-2 h-4 w-4" />
            {showGraph ? "Hide Blast Radius" : "Visualize Blast Radius"}
          </Button>

          <Button 
            onClick={handleExportPDF} 
            disabled={exporting}
            className="shadow-sm transition-all cursor-pointer"
          >
            {exporting ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <Download className="mr-2 h-4 w-4" />
                Export Report
              </>
            )}
          </Button>
        </div>
      </div>

      {showGraph && (
        <div className="mb-8 w-full animate-in fade-in slide-in-from-top-4 duration-500">
          <BlastRadiusGraph orgJobId={orgJobId!} />
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <Card className="bg-muted/30 border-border/50">
          <CardContent className="p-6 flex items-center gap-4">
            <div className="p-3 bg-primary/10 rounded-lg border border-primary/20"><Building2 className="h-6 w-6 text-primary" /></div>
            <div>
              <p className="text-sm text-muted-foreground font-medium">Total Repos</p>
              <h3 className="text-2xl font-bold">{summary.total_repositories}</h3>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-muted/30 border-border/50">
          <CardContent className="p-6 flex items-center gap-4">
            <div className="p-3 bg-emerald-500/10 rounded-lg border border-emerald-500/20"><CheckCircle className="h-6 w-6 text-emerald-500" /></div>
            <div>
              <p className="text-sm text-muted-foreground font-medium">Scanned</p>
              <h3 className="text-2xl font-bold">{summary.completed_repositories}</h3>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-muted/30 border-border/50">
          <CardContent className="p-6 flex items-center gap-4">
            <div className="p-3 bg-rose-500/10 rounded-lg border border-rose-500/20"><XCircle className="h-6 w-6 text-rose-500" /></div>
            <div>
              <p className="text-sm text-muted-foreground font-medium">Failed</p>
              <h3 className="text-2xl font-bold">{summary.failed_repositories}</h3>
            </div>
          </CardContent>
        </Card>
        <Card className="bg-muted/30 border-border/50">
          <CardContent className="p-6 flex items-center gap-4">
            <div className="p-3 bg-amber-500/10 rounded-lg border border-amber-500/20"><ShieldAlert className="h-6 w-6 text-amber-500" /></div>
            <div>
              <p className="text-sm text-muted-foreground font-medium">Total Findings</p>
              <h3 className="text-2xl font-bold">{findings.length}</h3>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
        <Card className="md:col-span-2 shadow-sm">
          <CardHeader>
            <CardTitle className="text-lg">Top Vulnerable Repositories</CardTitle>
            <CardDescription>Highest concentration of security findings</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {summary.top_vulnerable_repositories.map((repo: any, index: number) => (
                <div key={index} className="flex items-center justify-between p-3 bg-muted/30 rounded-lg border border-border/50 transition-colors hover:bg-muted/50">
                  <span className="font-medium">{repo.repo_name}</span>
                  <span className="text-sm font-mono font-bold bg-destructive/10 text-destructive border border-destructive/20 px-2.5 py-1 rounded-md">
                    {repo.count} issues
                  </span>
                </div>
              ))}
              {summary.top_vulnerable_repositories.length === 0 && (
                <div className="text-sm text-muted-foreground text-center py-8 border rounded-lg bg-muted/10">No vulnerabilities found across the organization.</div>
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="shadow-sm">
          <CardHeader>
            <CardTitle className="text-lg">Severity Breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {Object.entries(summary.severity_distribution).map(([sev, count]) => (
                <div key={sev} className="flex items-center justify-between p-2 rounded-md hover:bg-muted/50 transition-colors">
                  <span className="text-sm font-medium uppercase text-muted-foreground">{sev}</span>
                  <span className="text-sm font-bold bg-background px-3 py-1 rounded-md border shadow-sm">{String(count)}</span>
                </div>
              ))}
              {Object.keys(summary.severity_distribution).length === 0 && (
                <div className="text-sm text-muted-foreground text-center py-4">No data available.</div>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Global Findings Table */}
      <Card className="shadow-sm">
        <CardHeader className="flex flex-row items-center justify-between border-b bg-muted/10 pb-4">
          <div>
            <CardTitle>Global Findings Ledger</CardTitle>
            <CardDescription>All vulnerabilities detected across the batch scan</CardDescription>
          </div>
          <div className="flex items-center gap-2 bg-background border rounded-md p-1 shadow-sm">
            <div className="pl-2 pr-1 text-muted-foreground">
              <Filter className="w-4 h-4" />
            </div>
            <select 
              className="bg-transparent text-sm text-foreground py-1.5 pr-8 pl-2 outline-none cursor-pointer font-medium appearance-none"
              value={repoFilter}
              onChange={(e) => setRepoFilter(e.target.value)}
              style={{ backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%236b7280' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`, backgroundPosition: 'right 0.25rem center', backgroundRepeat: 'no-repeat', backgroundSize: '1.5em 1.5em' }}
            >
              <option value="ALL">All Repositories</option>
              {uniqueRepos.map(repo => (
                <option key={repo} value={repo}>{repo}</option>
              ))}
            </select>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          <div className="max-h-[600px] overflow-y-auto">
            <Table>
              <TableHeader className="sticky top-0 bg-card z-10 shadow-sm border-b">
                <TableRow>
                  <TableHead className="w-[200px]">Repository</TableHead>
                  <TableHead className="w-[120px]">Severity</TableHead>
                  <TableHead>Vulnerability</TableHead>
                  <TableHead>File</TableHead>
                  <TableHead className="text-right">CWE</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {paginatedFindings.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5} className="text-center py-12 text-muted-foreground bg-muted/5">
                      <div className="flex flex-col items-center gap-2">
                        <CheckCircle className="h-8 w-8 text-muted-foreground/50" />
                        <p>No findings match the current filter.</p>
                      </div>
                    </TableCell>
                  </TableRow>
                ) : (
                  paginatedFindings.map((finding) => (
                    <TableRow key={finding.id} className="hover:bg-muted/50 transition-colors cursor-default">
                      <TableCell className="font-medium text-primary">{finding.repo_name}</TableCell>
                      <TableCell>
                        <span className={`text-[10px] font-bold px-2 py-1 rounded border uppercase tracking-wider ${getSeverityColor(finding.severity)}`}>
                          {finding.severity || "INFO"}
                        </span>
                      </TableCell>
                      <TableCell className="max-w-[300px] truncate font-medium" title={finding.title}>
                        {finding.title}
                      </TableCell>
                      <TableCell className="text-muted-foreground text-sm truncate max-w-[200px]" title={finding.file_path}>
                        {finding.file_path ? `${finding.file_path}:${finding.line_number || '*'}` : '-'}
                      </TableCell>
                      <TableCell className="text-right font-mono text-xs text-muted-foreground">
                        {finding.cwe || '-'}
                      </TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
          </div>
          
          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between px-4 py-3 border-t bg-muted/10">
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
                <span className="text-sm font-medium px-2">Page {currentPage} of {totalPages}</span>
                <Button 
                  variant="outline" 
                  size="sm" 
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                >
                  Next <ChevronRight className="h-4 w-4 ml-1" />
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
