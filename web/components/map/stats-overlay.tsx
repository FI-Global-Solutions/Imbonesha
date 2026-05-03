"use client";

import type { FlagListItem } from "@/lib/api/types";

interface Props {
  flags: FlagListItem[];
}

export function StatsOverlay({ flags }: Props) {
  const total = flags.length;
  const critical = flags.filter((f) => f.severity === "critical").length;
  const awaiting = flags.filter((f) => f.status === "pending" || f.status === "assigned").length;

  return (
    <div className="absolute top-4 left-4 z-10 bg-card/95 backdrop-blur-sm border shadow-sm rounded-xl p-4 w-52">
      <p className="text-[10px] font-semibold text-muted-foreground uppercase tracking-widest mb-3">
        Live overview
      </p>
      <div className="space-y-2.5">
        <div className="flex justify-between items-baseline">
          <span className="text-xs text-muted-foreground">Total flags</span>
          <span className="text-2xl font-bold tabular-nums">{total}</span>
        </div>
        <div className="flex justify-between items-baseline">
          <span className="text-xs text-muted-foreground">Critical</span>
          <span className="text-2xl font-bold tabular-nums text-red-500">{critical}</span>
        </div>
        <div className="flex justify-between items-baseline">
          <span className="text-xs text-muted-foreground">Awaiting review</span>
          <span className="text-2xl font-bold tabular-nums text-amber-500">{awaiting}</span>
        </div>
      </div>
    </div>
  );
}
