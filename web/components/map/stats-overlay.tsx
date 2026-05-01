"use client";

import { Zap } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useUIStore } from "@/lib/store";
import type { FlagListItem } from "@/lib/api/types";

interface Props {
  flags: FlagListItem[];
}

export function StatsOverlay({ flags }: Props) {
  const setTriggerDialogOpen = useUIStore((s) => s.setTriggerDialogOpen);

  const total = flags.length;
  const critical = flags.filter((f) => f.severity === "critical").length;
  const awaiting = flags.filter((f) => f.status === "pending" || f.status === "assigned").length;

  return (
    <div className="absolute top-4 left-4 z-10 bg-card border shadow-sm rounded-lg p-4 w-56">
      <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">
        Detected changes
      </p>

      <div className="space-y-2.5">
        <div className="flex justify-between items-baseline">
          <span className="text-xs text-muted-foreground uppercase tracking-wide">Total flags</span>
          <span className="text-2xl font-semibold tabular-nums">{total}</span>
        </div>
        <div className="flex justify-between items-baseline">
          <span className="text-xs text-muted-foreground uppercase tracking-wide">Critical</span>
          <span className="text-2xl font-semibold tabular-nums text-red-600 dark:text-red-400">
            {critical}
          </span>
        </div>
        <div className="flex justify-between items-baseline">
          <span className="text-xs text-muted-foreground uppercase tracking-wide">Awaiting</span>
          <span className="text-2xl font-semibold tabular-nums">{awaiting}</span>
        </div>
      </div>

      <div className="mt-4 pt-3 border-t">
        <Button
          size="sm"
          variant="outline"
          className="w-full"
          onClick={() => setTriggerDialogOpen(true)}
        >
          <Zap className="mr-2 h-3.5 w-3.5" />
          Trigger detection
        </Button>
      </div>
    </div>
  );
}
