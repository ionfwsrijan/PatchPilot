import { useState } from "react";
import { Loader2, Download, CheckCircle, AlertTriangle } from "lucide-react";
import { Button } from "../ui/button";
import { downloadAuditReport } from "../../lib/api";

interface ExportReportButtonProps {
  scanId: string;
}

export function ExportReportButton({ scanId }: ExportReportButtonProps) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [status, setStatus] = useState<"idle" | "success" | "error">("idle");

  const handleDownload = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

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
        size="sm"
        onClick={handleDownload}
        disabled={isGenerating}
        className="flex items-center gap-2 text-xs h-8"
      >
        {isGenerating ? (
          <Loader2 className="w-3 h-3 animate-spin" />
        ) : (
          <Download className="w-3 h-3" />
        )}
        {isGenerating ? "Generating..." : "PDF"}
      </Button>

      {status === "success" && (
        <div className="absolute bottom-full right-0 mb-2 z-50 flex items-center gap-2 p-2 bg-slate-900 border border-emerald-800 text-slate-200 shadow-xl rounded min-w-[200px] animate-in fade-in slide-in-from-bottom-2">
          <CheckCircle className="w-4 h-4 text-emerald-500 shrink-0" />
          <div className="flex flex-col">
            <span className="text-xs font-semibold text-slate-200">Report Downloaded</span>
          </div>
        </div>
      )}

      {status === "error" && (
        <div className="absolute bottom-full right-0 mb-2 z-50 flex items-center gap-2 p-2 bg-slate-900 border border-rose-800 text-slate-200 shadow-xl rounded min-w-[200px] animate-in fade-in slide-in-from-bottom-2">
          <AlertTriangle className="w-4 h-4 text-rose-500 shrink-0" />
          <div className="flex flex-col">
            <span className="text-xs font-semibold text-slate-200">Export Failed</span>
          </div>
        </div>
      )}
    </div>
  );
}