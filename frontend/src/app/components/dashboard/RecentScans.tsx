import { Trash2 } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "../ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "../ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import { StatusPill } from "../status-pill";
import { ExportReportButton } from "./ExportReportButton";
import type { UiJob } from "../../hooks/useRecentJobs";
import { cn } from "../ui/utils";

interface RecentScansProps {
  recentJobs: UiJob[];
  onClearRecents: () => void;
}

export function RecentScans({ recentJobs, onClearRecents }: RecentScansProps) {
  const navigate = useNavigate();

  const formatTimestamp = (timestamp: string) => {
    let formattedStr = timestamp;
    if (timestamp && !timestamp.endsWith("Z") && !timestamp.includes("+")) {
      formattedStr = timestamp.replace(" ", "T") + "Z";
    }
    const date = new Date(formattedStr);
    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    }).format(date);
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <div>
          <CardTitle>Recent Scans</CardTitle>
          <CardDescription>Your latest vulnerability scan jobs</CardDescription>
        </div>
        {recentJobs.length > 0 && (
          <Button variant="outline" size="sm" onClick={onClearRecents}>
            <Trash2 className="h-4 w-4 mr-2" />
            Clear
          </Button>
        )}
      </CardHeader>

      <CardContent>
        {recentJobs.length === 0 ? (
          <div className="text-sm text-muted-foreground">
            No scans yet. Upload a ZIP above to start your first scan.
          </div>
        ) : (
          <>
            <div className="hidden md:block">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Job ID</TableHead>
                    <TableHead>Repository</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Timestamp</TableHead>
                    <TableHead>Duration</TableHead>
                    <TableHead className="text-right">Findings</TableHead>
                    <TableHead></TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {recentJobs.map((job) => (
                    <TableRow 
                      key={job.id} 
                      className={cn(
                        job.status === "completed" ? "cursor-pointer hover:bg-muted/50" : "opacity-65 cursor-not-allowed"
                      )}
                      onClick={() => {
                        if (job.status === "completed") {
                          navigate(`/findings?job_id=${job.id}`);
                        }
                      }}
                    >
                      <TableCell className="font-mono text-xs">{job.id}</TableCell>
                      <TableCell className="font-medium">{job.repoName}</TableCell>
                      <TableCell><StatusPill status={job.status} /></TableCell>
                      <TableCell className="text-muted-foreground text-sm">{formatTimestamp(job.timestamp)}</TableCell>
                      <TableCell className="text-muted-foreground text-sm">{job.duration || "-"}</TableCell>
                      <TableCell className="text-right">
                        {job.status === "completed" && <span className="font-medium">{job.findingsCount}</span>}
                      </TableCell>
                      <TableCell className="text-right flex justify-end gap-2" onClick={(e) => e.stopPropagation()}>
                        {job.status === "completed" && <ExportReportButton scanId={job.id} />}
                        {job.status === "completed" ? (
                          <Link to={`/findings?job_id=${job.id}`}>
                            <Button variant="ghost" size="sm">View</Button>
                          </Link>
                        ) : (
                          <Button variant="ghost" size="sm" disabled>View</Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>

            <div className="md:hidden space-y-3">
              {recentJobs.map((job) => {
                const cardContent = (
                  <Card className={cn(
                    "transition-colors",
                    job.status === "completed" ? "hover:bg-muted/50 cursor-pointer" : "opacity-65 cursor-not-allowed"
                  )}>
                    <CardContent className="p-4">
                      <div className="flex items-start justify-between mb-2">
                        <div className="flex-1 min-w-0">
                          <div className="font-medium truncate">{job.repoName}</div>
                          <div className="text-xs text-muted-foreground font-mono mt-1">{job.id}</div>
                        </div>
                        <StatusPill status={job.status} />
                      </div>
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span>{formatTimestamp(job.timestamp)}</span>
                        <div className="flex items-center gap-3" onClick={(e) => e.stopPropagation()}>
                          {job.status === "completed" && <ExportReportButton scanId={job.id} />}
                          {job.status === "completed" && <span className="font-medium text-foreground">{job.findingsCount} findings</span>}
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );

                return job.status === "completed" ? (
                  <Link key={job.id} to={`/findings?job_id=${job.id}`} className="block">
                    {cardContent}
                  </Link>
                ) : (
                  <div key={job.id} className="block">
                    {cardContent}
                  </div>
                );
              })}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}