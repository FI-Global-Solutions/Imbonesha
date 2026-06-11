"use client";

import { useMemo } from "react";
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  XAxis, YAxis, CartesianGrid,
  Tooltip as RechartsTooltip, ResponsiveContainer, Legend,
} from "recharts";
import { format, parseISO } from "date-fns";
import { useTheme } from "next-themes";
import { Flag, Clock, CheckCircle2, AlertTriangle, TrendingUp } from "lucide-react";

import { TopBar } from "@/components/top-bar";
import { Skeleton } from "@/components/ui/skeleton";
import { useAnalytics } from "@/lib/api/hooks";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------
const SEV_HEX: Record<string, string> = {
  critical: "#ef4444",
  high:     "#f97316",
  medium:   "#eab308",
  low:      "#22c55e",
};

const PERMIT_HEX: Record<string, string> = {
  authorized:     "#22c55e",
  expired:        "#eab308",
  no_permit:      "#ef4444",
  wrong_category: "#f59e0b",
  zone_violation: "#dc2626",
  no_parcel:      "#94a3b8",
};

const PERMIT_LABELS: Record<string, string> = {
  authorized:     "Authorized",
  expired:        "Expired permit",
  no_permit:      "No permit",
  wrong_category: "Wrong category",
  zone_violation: "Zone violation",
  no_parcel:      "Unregistered land",
};

const STATUS_HEX: Record<string, string> = {
  pending:      "#6366f1",
  assigned:     "#3b82f6",
  in_review:    "#8b5cf6",
  confirmed:    "#ef4444",
  dismissed:    "#64748b",
  monitoring:   "#f59e0b",
  inaccessible: "#94a3b8",
  data_error:   "#94a3b8",
  closed:       "#22c55e",
};

const STATUS_LABELS: Record<string, string> = {
  pending:      "Pending",
  assigned:     "Assigned",
  in_review:    "In Review",
  confirmed:    "Confirmed",
  dismissed:    "Dismissed",
  monitoring:   "Monitoring",
  inaccessible: "Inaccessible",
  data_error:   "Data Error",
  closed:       "Closed",
};

// ---------------------------------------------------------------------------
// Theme-aware chart colours
// ---------------------------------------------------------------------------
function useChartColors() {
  const { resolvedTheme } = useTheme();
  return useMemo(() => {
    const isDark = resolvedTheme === "dark";
    return {
      border:      isDark ? "rgba(255,255,255,0.06)" : "rgba(0,0,0,0.06)",
      muted:       isDark ? "#64748b" : "#94a3b8",
      primary:     isDark ? "#4ade80" : "#16a34a",
      popover:     isDark ? "#1a1f2e" : "#ffffff",
      popoverFg:   isDark ? "#f1f5f9" : "#0f172a",
      popoverBorder: isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.08)",
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedTheme]);
}

function useTooltipStyle() {
  const cc = useChartColors();
  return {
    backgroundColor: cc.popover,
    border: `1px solid ${cc.popoverBorder}`,
    borderRadius: "12px",
    color: cc.popoverFg,
    fontSize: 12,
    boxShadow: "0 12px 32px rgba(0,0,0,0.2)",
    padding: "10px 14px",
  } as React.CSSProperties;
}

// ---------------------------------------------------------------------------
// Small reusable pieces
// ---------------------------------------------------------------------------
function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-muted-foreground/50 mb-4">
      {children}
    </p>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center h-40 text-muted-foreground/30 gap-2">
      <TrendingUp className="h-7 w-7" />
      <p className="text-xs">No data yet</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// KPI Card
// ---------------------------------------------------------------------------
interface KpiProps {
  label: string;
  value: string | number | null;
  sub: string;
  icon: React.ElementType;
  color: string;
}

function KpiCard({ label, value, sub, icon: Icon, color }: KpiProps) {
  return (
    <div className="rounded-2xl border border-border/50 bg-card p-5 flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-muted-foreground/50">{label}</p>
        <div className="h-7 w-7 rounded-lg flex items-center justify-center" style={{ background: `${color}18` }}>
          <Icon className="h-3.5 w-3.5" style={{ color }} />
        </div>
      </div>
      <div>
        {value === null || value === undefined
          ? <p className="text-4xl font-black tabular-nums tracking-tight text-muted-foreground/30">—</p>
          : <p className="text-4xl font-black tabular-nums tracking-tight text-foreground">{value}</p>
        }
        <p className="text-[11px] text-muted-foreground/60 mt-1.5 leading-snug">{sub}</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Horizontal bar (for districts / status)
// ---------------------------------------------------------------------------
function HBar({ label, value, total, color }: { label: string; value: number; total: number; color: string }) {
  const pct = total > 0 ? Math.round((value / total) * 100) : 0;
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-2 min-w-0">
          <span className="h-1.5 w-1.5 rounded-full shrink-0" style={{ background: color }} />
          <span className="text-muted-foreground truncate">{label}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-3">
          <span className="font-semibold tabular-nums text-foreground">{value}</span>
          <span className="text-muted-foreground/50 w-8 text-right">{pct}%</span>
        </div>
      </div>
      <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${pct}%`, background: color, opacity: 0.8 }}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function AnalyticsPage() {
  const { data, isLoading } = useAnalytics();
  const cc = useChartColors();
  const tooltipStyle = useTooltipStyle();

  const kpis = data?.kpis;
  const flagsOverTime = data?.flags_over_time ?? [];
  const byDistrict = data?.flags_by_district ?? [];
  const permitBreakdown = data?.permit_status_breakdown;
  const statusBreakdown = data?.status_breakdown;

  const permitPie = useMemo(() => {
    if (!permitBreakdown) return [];
    return Object.entries(permitBreakdown)
      .map(([k, v]) => ({ name: PERMIT_LABELS[k] ?? k, value: v as number, key: k }))
      .filter((e) => e.value > 0);
  }, [permitBreakdown]);

  const statusEntries = useMemo(() => {
    if (!statusBreakdown) return [];
    return Object.entries(statusBreakdown)
      .filter(([, v]) => (v as number) > 0)
      .sort(([, a], [, b]) => (b as number) - (a as number))
      .map(([k, v]) => ({ key: k, label: STATUS_LABELS[k] ?? k, value: v as number }));
  }, [statusBreakdown]);

  const totalPermit = permitPie.reduce((s, e) => s + e.value, 0);
  const totalStatus = statusEntries.reduce((s, e) => s + e.value, 0);
  const districtTotal = byDistrict.reduce((s: number, d: { count: number }) => s + d.count, 0);

  // Severity breakdown from kpis — derive from permit+status since backend gives us totals
  const sevData = useMemo(() => {
    if (!data) return [];
    // Use permit pie data to build a severity-style bar for visual interest
    return permitPie.map((e) => ({ name: e.name, value: e.value, color: PERMIT_HEX[e.key] ?? "#888" }));
  }, [data, permitPie]);

  return (
    <div className="flex flex-col h-full min-h-0">
      <TopBar breadcrumb="Analytics" />

      <div className="flex-1 min-h-0 overflow-auto">
        <div className="px-6 py-6 space-y-8 max-w-[1400px]">

          {/* Header */}
          <div>
            <h1 className="text-2xl font-black tracking-tight text-foreground">Analytics</h1>
            <p className="text-[13px] text-muted-foreground mt-1">
              Real-time flag activity and enforcement performance
            </p>
          </div>

          {/* KPI row */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {isLoading ? (
              [...Array(4)].map((_, i) => (
                <div key={i} className="rounded-2xl border border-border/50 bg-card p-5 space-y-3">
                  <Skeleton className="h-3 w-24" />
                  <Skeleton className="h-10 w-16" />
                  <Skeleton className="h-3 w-32" />
                </div>
              ))
            ) : (
              <>
                <KpiCard label="Total flags" value={kpis?.total_flags ?? null}
                  sub="All time across all districts" icon={Flag} color="#6366f1" />
                <KpiCard label="Awaiting review" value={kpis?.awaiting_review ?? null}
                  sub="Pending inspector assignment" icon={Clock} color="#f59e0b" />
                <KpiCard label="Confirmed unauthorized" value={kpis?.confirmed_unauthorized_30d ?? null}
                  sub="Inspector verified · last 30 days" icon={CheckCircle2} color="#22c55e" />
                <KpiCard
                  label="Avg to inspection"
                  value={kpis?.avg_time_to_inspection_hours != null ? `${kpis.avg_time_to_inspection_hours}h` : null}
                  sub="From flag raised to verdict" icon={AlertTriangle} color="#ef4444" />
              </>
            )}
          </div>

          {/* Flags over time — full width */}
          <div className="rounded-2xl border border-border/50 bg-card p-6">
            <SectionLabel>Flags over time · last 90 days</SectionLabel>
            {isLoading ? <Skeleton className="h-56 w-full rounded-xl" /> :
             flagsOverTime.length === 0 ? <EmptyState /> : (
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={flagsOverTime} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
                  <defs>
                    {(["critical","high","medium","low"] as const).map((s) => (
                      <linearGradient key={s} id={`g-${s}`} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor={SEV_HEX[s]} stopOpacity={0.35} />
                        <stop offset="100%" stopColor={SEV_HEX[s]} stopOpacity={0} />
                      </linearGradient>
                    ))}
                  </defs>
                  <CartesianGrid stroke={cc.border} vertical={false} />
                  <XAxis dataKey="date"
                    tickFormatter={(v) => format(parseISO(v), "MMM d")}
                    tick={{ fontSize: 11, fill: cc.muted }} axisLine={false} tickLine={false}
                    interval="preserveStartEnd"
                  />
                  <YAxis tick={{ fontSize: 11, fill: cc.muted }} axisLine={false} tickLine={false} />
                  <RechartsTooltip contentStyle={tooltipStyle}
                    labelFormatter={(v) => format(parseISO(v as string), "d MMM yyyy")} />
                  <Legend iconType="circle" iconSize={7}
                    wrapperStyle={{ fontSize: 11, paddingTop: 12, color: cc.muted }} />
                  {(["critical","high","medium","low"] as const).map((s) => (
                    <Area key={s} type="monotone" dataKey={s} stackId="1"
                      stroke={SEV_HEX[s]} fill={`url(#g-${s})`} strokeWidth={1.5} dot={false} />
                  ))}
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Row 1 — Districts + Permit donut */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

            {/* Districts bar chart */}
            <div className="lg:col-span-2 rounded-2xl border border-border/50 bg-card p-6">
              <SectionLabel>Flags by district</SectionLabel>
              {isLoading ? <Skeleton className="h-52 w-full rounded-xl" /> :
               byDistrict.length === 0 ? <EmptyState /> : (
                <ResponsiveContainer width="100%" height={Math.max(160, byDistrict.length * 44)}>
                  <BarChart
                    data={byDistrict}
                    layout="vertical"
                    margin={{ top: 0, right: 48, bottom: 0, left: 4 }}
                  >
                    <CartesianGrid stroke={cc.border} horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 11, fill: cc.muted }} axisLine={false} tickLine={false} />
                    <YAxis
                      type="category" dataKey="district" width={72}
                      tick={{ fontSize: 12, fill: cc.muted, fontWeight: 500 }}
                      axisLine={false} tickLine={false}
                    />
                    <RechartsTooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
                    <Bar dataKey="count" radius={[0, 6, 6, 0]} maxBarSize={24} fill={cc.primary} fillOpacity={0.9}
                      label={{ position: "right", fontSize: 11, fill: cc.muted, formatter: (v: unknown) => String(v) }}
                    />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>

            {/* Permit donut */}
            <div className="rounded-2xl border border-border/50 bg-card p-6 flex flex-col">
              <SectionLabel>Permit status</SectionLabel>
              {isLoading ? <Skeleton className="h-52 w-full rounded-xl" /> :
               permitPie.length === 0 ? <EmptyState /> : (
                <>
                  <div className="relative flex items-center justify-center mb-4">
                    <ResponsiveContainer width={180} height={180}>
                      <PieChart>
                        <Pie data={permitPie} cx="50%" cy="50%"
                          innerRadius={54} outerRadius={82}
                          paddingAngle={3} dataKey="value" strokeWidth={0}
                        >
                          {permitPie.map((e) => (
                            <Cell key={e.key} fill={PERMIT_HEX[e.key] ?? "#888"} />
                          ))}
                        </Pie>
                        <RechartsTooltip contentStyle={tooltipStyle} />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                      <span className="text-2xl font-black tabular-nums">{totalPermit}</span>
                      <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground/40 mt-0.5">total</span>
                    </div>
                  </div>
                  <div className="space-y-2.5 flex-1">
                    {permitPie.map((e) => (
                      <HBar key={e.key} label={e.name} value={e.value} total={totalPermit} color={PERMIT_HEX[e.key] ?? "#888"} />
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>

          {/* Row 2 — Status distribution + Severity bars */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

            {/* Status distribution */}
            <div className="rounded-2xl border border-border/50 bg-card p-6">
              <SectionLabel>Flag lifecycle</SectionLabel>
              {isLoading ? <Skeleton className="h-48 w-full rounded-xl" /> :
               statusEntries.length === 0 ? <EmptyState /> : (
                <div className="space-y-3">
                  {statusEntries.map((e) => (
                    <HBar key={e.key} label={e.label} value={e.value} total={totalStatus} color={STATUS_HEX[e.key] ?? "#888"} />
                  ))}
                </div>
              )}
            </div>

            {/* Permit breakdown as horizontal bars (more readable than donut alone) */}
            <div className="rounded-2xl border border-border/50 bg-card p-6">
              <SectionLabel>Permit breakdown detail</SectionLabel>
              {isLoading ? <Skeleton className="h-48 w-full rounded-xl" /> :
               sevData.length === 0 ? <EmptyState /> : (
                <ResponsiveContainer width="100%" height={Math.max(160, sevData.length * 52)}>
                  <BarChart data={sevData} layout="vertical" margin={{ top: 0, right: 48, bottom: 0, left: 4 }}>
                    <CartesianGrid stroke={cc.border} horizontal={false} />
                    <XAxis type="number" tick={{ fontSize: 11, fill: cc.muted }} axisLine={false} tickLine={false} />
                    <YAxis type="category" dataKey="name" width={96}
                      tick={{ fontSize: 11, fill: cc.muted }} axisLine={false} tickLine={false} />
                    <RechartsTooltip contentStyle={tooltipStyle} cursor={{ fill: "rgba(255,255,255,0.03)" }} />
                    <Bar dataKey="value" radius={[0, 6, 6, 0]} maxBarSize={22}
                      label={{ position: "right", fontSize: 11, fill: cc.muted, formatter: (v: unknown) => String(v) }}
                    >
                      {sevData.map((e, i) => <Cell key={i} fill={e.color} fillOpacity={0.85} />)}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {/* District breakdown — detailed horizontal bars */}
          <div className="rounded-2xl border border-border/50 bg-card p-6">
            <SectionLabel>District breakdown</SectionLabel>
            {isLoading ? <Skeleton className="h-32 w-full rounded-xl" /> :
             byDistrict.length === 0 ? <EmptyState /> : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {(byDistrict as { district: string; count: number }[]).map((d, i) => {
                  const colors = [cc.primary, "#6366f1", "#f59e0b", "#ef4444", "#8b5cf6", "#3b82f6"];
                  return (
                    <HBar key={d.district} label={d.district} value={d.count} total={districtTotal}
                      color={colors[i % colors.length]} />
                  );
                })}
              </div>
            )}
          </div>

          <div className="h-4" />
        </div>
      </div>
    </div>
  );
}
