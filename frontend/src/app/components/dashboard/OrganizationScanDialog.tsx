import { useState } from "react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";

interface OrganizationScanDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onScan: (url: string) => void;
  isLoading: boolean;
}

export function OrganizationScanDialog({ isOpen, onClose, onScan, isLoading }: OrganizationScanDialogProps) {
  const [orgUrl, setOrgUrl] = useState("");

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-lg bg-background border border-border p-4 shadow-lg">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-lg font-semibold">Scan Organization</div>
            <div className="text-sm text-muted-foreground">
              Fetch and execute vulnerability tests across all repositories
            </div>
          </div>
          <Button variant="ghost" onClick={onClose} disabled={isLoading}>
            Close
          </Button>
        </div>

        <div className="mt-4 space-y-2">
          <Input
            placeholder="https://github.com/your-org"
            value={orgUrl}
            onChange={(e) => setOrgUrl(e.target.value)}
            disabled={isLoading}
          />
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button
            onClick={() => onScan(orgUrl)}
            disabled={isLoading || !orgUrl.trim()}
          >
            {isLoading ? "Initializing..." : "Run Batch Scan"}
          </Button>
        </div>
      </div>
    </div>
  );
}