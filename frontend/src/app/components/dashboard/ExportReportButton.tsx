import { useState } from "react";
import { Loader2, Download } from "lucide-react";
import { Button } from "../ui/button";
import { downloadAuditReport } from "../../lib/api";
import { toast } from "sonner";

interface ExportReportButtonProps {
  scanId: string;
}

export function ExportReportButton({ scanId }: ExportReportButtonProps) {
  const [isGenerating, setIsGenerating] = useState(false);

  const handleDownload = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    setIsGenerating(true);

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

      toast.success("Report Downloaded", {
        description: `${filename} has been downloaded successfully.`,
      });
    } catch (error) {
      toast.error("Export Failed", {
        description: "Failed to generate the audit report. Please try again.",
      });
    } finally {
      setIsGenerating(false);
    }
  };

  return (
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
  );
}
