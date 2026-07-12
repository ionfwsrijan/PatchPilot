import React from "react";
import { Tooltip, TooltipTrigger, TooltipContent } from "./ui/tooltip";

export function FixConfidence({ confidence }: { confidence: number | null | undefined }) {
  const isMissing = confidence === null || confidence === undefined;
  const pct = isMissing ? 0 : Math.round(confidence * 100);

  let barColor = "bg-rose-500";
  let textColor = "text-rose-600";
  if (!isMissing) {
    if (pct >= 70) {
      barColor = "bg-status-success";
      textColor = "text-status-success";
    } else if (pct >= 40) {
      barColor = "bg-amber-400";
      textColor = "text-amber-600";
    }
  } else {
    barColor = "bg-muted/60";
    textColor = "text-muted-foreground";
  }

  const tooltipText = isMissing
    ? "No confidence score available for this fix"
    : `Model predicts ${pct}% chance this fix passes verification`;

  return (
    <Tooltip>
      <TooltipTrigger>
        <div className="flex items-center gap-2">
          <div className="w-28 h-2 bg-border rounded overflow-hidden">
            <div className={`${barColor} h-2`} style={{ width: `${Math.max(pct, 10)}%` }} />
          </div>
          <div className={`text-xs font-mono ${textColor}`}>
            {isMissing ? "N/A" : `${pct}%`}
          </div>
        </div>
      </TooltipTrigger>
      <TooltipContent sideOffset={6}>{tooltipText}</TooltipContent>
    </Tooltip>
  );
}

export default FixConfidence;
