"use client";

import type { FlagListItem } from "@/lib/api/types";

interface Props {
  flags: FlagListItem[];
  totalCount: number;
  verifiedCount: number;
  showVerified: boolean;
  onToggleVerified: () => void;
}

function StatCard({ label, value, color }: { label: string; value: number; color?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-white/40">{label}</span>
      <span className={`text-3xl font-black tabular-nums leading-none tracking-tight ${color ?? "text-white"}`}>
        {value}
      </span>
    </div>
  );
}

export function StatsOverlay({ flags, totalCount, verifiedCount, showVerified, onToggleVerified }: Props) {
  const total = totalCount;
  const critical = flags.filter((f) => f.severity === "critical").length;
  const high = flags.filter((f) => f.severity === "high").length;
  const awaiting = flags.filter((f) => f.status === "pending" || f.status === "assigned").length;

  return (
    <div className="absolute top-4 left-4 z-10 rounded-2xl overflow-hidden" style={{
      background: "rgba(10, 12, 18, 0.72)",
      backdropFilter: "blur(20px) saturate(180%)",
      WebkitBackdropFilter: "blur(20px) saturate(180%)",
      border: "1px solid rgba(255,255,255,0.08)",
      boxShadow: "0 8px 32px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.06)",
      width: 200,
    }}>
      {/* Header */}
      <div className="px-4 pt-3.5 pb-2.5 border-b border-white/6">
        <div className="flex items-center gap-2">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-white/40">
            Live Overview
          </p>
        </div>
      </div>

      {/* Stats */}
      <div className="px-4 py-3.5 space-y-3">
        <StatCard label="Total flags" value={total} />

        <div className="h-px bg-white/6" />

        <div className="grid grid-cols-2 gap-3">
          <StatCard label="Critical" value={critical} color="text-red-400" />
          <StatCard label="High" value={high} color="text-orange-400" />
        </div>

        <div className="h-px bg-white/6" />

        <StatCard label="Awaiting review" value={awaiting} color="text-amber-400" />

        {verifiedCount > 0 && (
          <>
            <div className="h-px bg-white/6" />
            <button
              type="button"
              onClick={onToggleVerified}
              className={`w-full text-left flex items-center justify-between gap-2 rounded-lg px-2.5 py-2 transition-colors ${
                showVerified
                  ? "bg-emerald-500/20 text-emerald-300"
                  : "bg-white/5 text-white/50 hover:bg-white/10 hover:text-white/70"
              }`}
            >
              <span className="text-[10px] font-semibold uppercase tracking-widest leading-tight">
                {showVerified ? "Hide verified" : "Show verified"}
              </span>
              <span className={`text-sm font-black tabular-nums ${showVerified ? "text-emerald-300" : "text-white/40"}`}>
                {verifiedCount}
              </span>
            </button>
          </>
        )}
      </div>

      {/* Footer bar — severity proportion (derived from loaded flags) */}
      {flags.length > 0 && (
        <div className="px-4 pb-3.5">
          <div className="flex h-1 rounded-full overflow-hidden gap-px">
            <div className="bg-red-500/80 transition-all" style={{ width: `${(critical / flags.length) * 100}%` }} />
            <div className="bg-orange-500/80 transition-all" style={{ width: `${(high / flags.length) * 100}%` }} />
            <div className="bg-amber-500/80 transition-all" style={{ width: `${(flags.filter(f => f.severity === "medium").length / flags.length) * 100}%` }} />
            <div className="bg-slate-500/60 flex-1" />
          </div>
          <p className="text-[9px] text-white/25 mt-1.5 font-medium tracking-wide">Severity distribution</p>
        </div>
      )}
    </div>
  );
}
