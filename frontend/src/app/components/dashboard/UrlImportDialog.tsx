import { useState } from "react";
import { Button } from "../ui/button";
import { Input } from "../ui/input";

interface UrlImportDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onImport: (url: string, ref: string) => void;
  isLoading: boolean;
}

export function UrlImportDialog({ isOpen, onClose, onImport, isLoading }: UrlImportDialogProps) {
  const [repoUrl, setRepoUrl] = useState("");
  const [repoRef, setRepoRef] = useState("main");

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg rounded-lg bg-background border border-border p-4 shadow-lg">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="text-lg font-semibold">Import from URL</div>
            <div className="text-sm text-muted-foreground">
              GitHub repos supported (example: https://github.com/owner/repo)
            </div>
          </div>
          <Button variant="ghost" onClick={onClose} disabled={isLoading}>
            Close
          </Button>
        </div>

        <div className="mt-4 space-y-2">
          <Input
            placeholder="https://github.com/owner/repo"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            disabled={isLoading}
          />
          <Input
            placeholder="Branch/ref (default: main)"
            value={repoRef}
            onChange={(e) => setRepoRef(e.target.value)}
            disabled={isLoading}
          />
        </div>

        <div className="mt-4 flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={isLoading}>
            Cancel
          </Button>
          <Button
            onClick={() => onImport(repoUrl, repoRef)}
            disabled={isLoading || !repoUrl.trim()}
          >
            {isLoading ? "Importing..." : "Import & Scan"}
          </Button>
        </div>
      </div>
    </div>
  );
}