"use client";

import { useMemo } from "react";
import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip as RechartsTooltip, Legend, ResponsiveContainer,
} from "recharts";
import { format, parseISO } from "date-fns";
import { useTheme } from "next-themes";
import { Flag, Clock, CheckCircle2, AlertTriangle, TrendingUp } from "lucide-react";

import { TopBar } from "@/components/top-bar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAnalytics } from "@/lib/api/hooks";

// ---------------------------------------------------------------------------
// Hard-coded hex colors — Recharts renders SVG, can't resolve CSS vars at
// paint time. We always use explicit hex so dark/light both look correct.
// ---------------------------------------------------------------------------
const SEV: Record<string, string> = {
  critical: "#ef4444",
  high:     "#f97316",
  medium:   "#eab308",
  low:      "#22c55e",
};

const PERMIT_HEX: Record<string, string> = {
  active:    "#22c55e",
  expired:   "#eab308",
  no_permit: "#ef4444",
  other:     "#f97316",
};

const PERMIT_LABELS: Record<string, string> = {
  active:    "Active permit",
  expired:   "Expired permit",
  no_permit: "No permit",
  other:     "Other issue",
};

// ---------------------------------------------------------------------------
// Theme-aware chart colours resolved at render time via CSS getPropertyValue
// ---------------------------------------------------------------------------
function useChartColors() {
  const { resolvedTheme } = useTheme();
  return useMemo(() => {
    if (typeof window === "undefined") {
      return { border: "#e2e8f0", muted: "#94a3b8", primary: "#16a34a", bg: "#ffffff" };
    }
    const style = getComputedStyle(document.documentElement);
    const isDark = resolvedTheme === "dark";
    return {
      border: isDark ? "rgba(255,255,255,0.1)" : "rgba(0,0,0,0.07)",
      muted:  isDark ? "#94a3b8" : "#64748b",
      primary: isDark ? "#4ade80" : "#16a34a",
      bg:     isDark ? "#1e2430" : "#ffffff",
      popover: isDark ? "#1e2430" : "#ffffff",
      popoverFg: isDark ? "#f1f5f9" : "#0f172a",
      popoverBorder: isDark ? "rgba(255,255,255,0.12)" : "rgba(0,0,0,0.1)",
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolvedTheme]);
}

// ---------------------------------------------------------------------------
// KPI card
// ---------------------------------------------------------------------------
interface KpiProps {
  label: string;
  value: string | number | null;
  sub: string;
  icon: React.ElementType;
  accent: string; // tailwind bg class for the icon blob
  iconColor: string; // tailwind text class
}

function KpiCard({ label, value, sub, icon: Icon, accent, iconColor }: KpiProps) {
  return (
    <Card className="relative overflow-hidden">
      <CardContent className="pt-5 pb-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <p className="text-xs uppercase tracking-widest font-semibold text-muted-foreground">
              {label}
            </p>
            {value === null || value === undefined ? (
              <p className="text-4xl font-bold tabular-nums mt-2 text-muted-foreground/50">—</p>
            ) : (
              <p className="text-4xl font-bold tabular-nums mt-2 text-foreground">{value}</p>
            )}
            <p className="text-xs text-muted-foreground mt-1.5 leading-snug">{sub}</p>
          </div>
          <div className={`h-10 w-10 rounded-xl flex items-center justify-center shrink-0 mt-0.5 ${accent}`}>
            <Icon className={`h-5 w-5 ${iconColor}`} />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Shared chart tooltip style (must be plain object — React.CSSProperties)
// ---------------------------------------------------------------------------
function useTooltipStyle() {
  const cc = useChartColors();
  return {
    backgroundColor: cc.popover,
    border: `1px solid ${cc.popoverBorder}`,
    borderRadius: "10px",
    color: cc.popoverFg,
    fontSize: 12,
    boxShadow: "0 8px 24px rgba(0,0,0,0.15)",
    padding: "10px 14px",
  } as React.CSSProperties;
}

function ChartSkeleton({ height = 260 }: { height?: number }) {
  return <Skeleton className="w-full rounded-lg" style={{ height }} />;
}

function EmptyChart({ height = 260 }: { height?: number }) {
  return (
    <div className="flex flex-col items-center justify-center text-muted-foreground/50 gap-2" style={{ height }}>
      <TrendingUp className="h-8 w-8" />
      <p className="text-sm">No data yet</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Status distribution bar
// ---------------------------------------------------------------------------

const STATUS_HEX: Record<string, string> = {
  pending:      "#94a3b8",
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

function StatusDistribution({ data }: { data?: Record<string, number> }) {
  if (!data) return <EmptyChart />;
  const entries = Object.entries(data)
    .filter(([, v]) => v > 0)
    .sort(([, a], [, b]) => b - a);
  const total = entries.reduce((s, [, v]) => s + v, 0);
  if (total === 0) return <EmptyChart />;

  return (
    <div className="space-y-3">
      {entries.map(([status, count]) => {
        const pct = Math.round((count / total) * 100);
        const hex = STATUS_HEX[status] ?? "#888";
        return (
          <div key={status}>
            <div className="flex items-center justify-between text-xs mb-1">
              <div className="flex items-center gap-2">
                <span className="inline-block h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: hex }} />
                <span className="text-muted-foreground">{STATUS_LABELS[status] ?? status}</span>
              </div>
              <span className="font-semibold tabular-nums text-foreground">
                {count}
                <span className="font-normal text-muted-foreground ml-1">({pct}%)</span>
              </span>
            </div>
            <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${pct}%`, backgroundColor: hex, opacity: 0.85 }}
              />
            </div>
          </div>
        );
      })}
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
  const throughput = data?.detection_throughput ?? [];

  const permitPie = useMemo(() => {
    if (!permitBreakdown) return [];
    return Object.entries(permitBreakdown).map(([k, v]) => ({
      name: PERMIT_LABELS[k] ?? k,
      value: v as number,
      key: k,
    }));
  }, [permitBreakdown]);

  const totalPermit = permitPie.reduce((a, p) => a + p.value, 0);

  return (
    <div className="flex flex-col h-full min-h-0">
      <TopBar breadcrumb="Analytics" />

      <div className="flex-1 min-h-0 overflow-auto bg-muted/20">
        <div className="px-6 py-6 space-y-6 max-w-[1400px]">

          {/* Page header */}
          <div>
            <h1 className="text-2xl font-bold text-foreground tracking-tight">Analytics</h1>
            <p className="text-sm text-muted-foreground mt-1">
              Overview of flag activity and detection performance
            </p>
          </div>

          {/* KPI row */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {isLoading ? (
              [...Array(4)].map((_, i) => (
                <Card key={i}>
                  <CardContent className="pt-5 pb-5 space-y-3">
                    <Skeleton className="h-3 w-20" />
                    <Skeleton className="h-9 w-14" />
                    <Skeleton className="h-3 w-28" />
                  </CardContent>
                </Card>
              ))
            ) : (
              <>
                <KpiCard
                  label="Total flags"
                  value={kpis?.total_flags ?? null}
                  sub="All time across all districts"
                  icon={Flag}
                  accent="bg-blue-100 dark:bg-blue-950"
                  iconColor="text-blue-600 dark:text-blue-400"
                />
                <KpiCard
                  label="Awaiting review"
                  value={kpis?.awaiting_review ?? null}
                  sub="Pending inspector assignment"
                  icon={Clock}
                  accent="bg-amber-100 dark:bg-amber-950"
                  iconColor="text-amber-600 dark:text-amber-400"
                />
                <KpiCard
                  label="Confirmed unauthorized"
                  value={kpis?.confirmed_unauthorized_30d ?? null}
                  sub="Inspector verified · last 30 days"
                  icon={CheckCircle2}
                  accent="bg-green-100 dark:bg-green-950"
                  iconColor="text-green-600 dark:text-green-400"
                />
                <KpiCard
                  label="Avg to inspection"
                  value={kpis?.avg_time_to_inspection_hours != null
                    ? `${kpis.avg_time_to_inspection_hours}h`
                    : null}
                  sub="From flag raised to verdict"
                  icon={AlertTriangle}
                  accent="bg-red-100 dark:bg-red-950"
                  iconColor="text-red-600 dark:text-red-400"
                />
              </>
            )}
          </div>

          {/* Charts row 1 */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

            {/* Flags over time — spans 2 cols */}
            <Card className="lg:col-span-2">
              <CardHeader className="border-b pb-4">
                <CardTitle>Flags over time</CardTitle>
                <CardDescription>Last 90 days — stacked by severity</CardDescription>
              </CardHeader>
              <CardContent className="pt-4">
                {isLoading ? <ChartSkeleton /> : flagsOverTime.length === 0 ? <EmptyChart /> : (
                  <ResponsiveContainer width="100%" height={260}>
                    <AreaChart data={flagsOverTime} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                      <defs>
                        {(["critical", "high", "medium", "low"] as const).map((sev) => (
                          <linearGradient key={sev} id={`grad-${sev}`} x1="0" y1="0" x2="0" y2="1">
                            <stop offset="0%" stopColor={SEV[sev]} stopOpacity={0.4} />
                            <stop offset="100%" stopColor={SEV[sev]} stopOpacity={0.02} />
                          </linearGradient>
                        ))}
                      </defs>
                      <CartesianGrid stroke={cc.border} vertical={false} />
                      <XAxis
                        dataKey="date"
                        tickFormatter={(v) => format(parseISO(v), "MMM d")}
                        tick={{ fontSize: 11, fill: cc.muted }}
                        axisLine={false} tickLine={false}
                        interval="preserveStartEnd"
                      />
                      <YAxis
                        tick={{ fontSize: 11, fill: cc.muted }}
                        axisLine={false} tickLine={false}
                      />
                      <RechartsTooltip
                        contentStyle={tooltipStyle}
                        labelFormatter={(v) => format(parseISO(v as string), "d MMM yyyy")}
                      />
                      <Legend
                        iconType="circle" iconSize={8}
                        wrapperStyle={{ fontSize: 11, paddingTop: 12, color: cc.muted }}
                      />
                      {(["critical", "high", "medium", "low"] as const).map((sev) => (
                        <Area
                          key={sev}
                          type="monotone"
                          dataKey={sev}
                          stackId="1"
                          stroke={SEV[sev]}
                          fill={`url(#grad-${sev})`}
                          strokeWidth={2}
                          dot={false}
                        />
                      ))}
                    </AreaChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            {/* Permit breakdown donut */}
            <Card>
              <CardHeader className="border-b pb-4">
                <CardTitle>Permit breakdown</CardTitle>
                <CardDescription>Share by permit status</CardDescription>
              </CardHeader>
              <CardContent className="pt-4 flex flex-col items-center">
                {isLoading ? <ChartSkeleton /> : permitPie.length === 0 ? <EmptyChart /> : (
                  <>
                    <div className="relative">
                      <ResponsiveContainer width={220} height={200}>
                        <PieChart>
                          <Pie
                            data={permitPie}
                            cx="50%" cy="50%"
                            innerRadius={66} outerRadius={94}
                            paddingAngle={3}
                            dataKey="value"
                            strokeWidth={0}
                          >
                            {permitPie.map((entry) => (
                              <Cell key={entry.key} fill={PERMIT_HEX[entry.key] ?? "#888"} />
                            ))}
                          </Pie>
                          <RechartsTooltip contentStyle={tooltipStyle} />
                        </PieChart>
                      </ResponsiveContainer>
                      {/* Centre label */}
                      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
                        <span className="text-2xl font-bold tabular-nums text-foreground">{totalPermit}</span>
                        <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">total</span>
                      </div>
                    </div>

                    <div className="w-full space-y-2 mt-3 px-1">
                      {permitPie.map((entry) => {
                        const pct = totalPermit ? Math.round(entry.value / totalPermit * 100) : 0;
                        return (
                          <div key={entry.key}>
                            <div className="flex items-center justify-between text-xs mb-1">
                              <div className="flex items-center gap-2">
                                <span
                                  className="inline-block h-2 w-2 rounded-full shrink-0"
                                  style={{ backgroundColor: PERMIT_HEX[entry.key] ?? "#888" }}
                                />
                                <span className="text-muted-foreground">{entry.name}</span>
                              </div>
                              <span className="font-semibold tabular-nums text-foreground">
                                {entry.value}
                                <span className="font-normal text-muted-foreground ml-1">({pct}%)</span>
                              </span>
                            </div>
                            <div className="h-1 w-full rounded-full bg-muted overflow-hidden">
                              <div
                                className="h-full rounded-full transition-all"
                                style={{
                                  width: `${pct}%`,
                                  backgroundColor: PERMIT_HEX[entry.key] ?? "#888",
                                  opacity: 0.85,
                                }}
                              />
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Charts row 2 */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">

            {/* Flags by district */}
            <Card className="lg:col-span-2">
              <CardHeader className="border-b pb-4">
                <CardTitle>Flags by district</CardTitle>
                <CardDescription>Total enforcement flags per administrative district</CardDescription>
              </CardHeader>
              <CardContent className="pt-4">
                {isLoading ? <ChartSkeleton /> : byDistrict.length === 0 ? <EmptyChart /> : (
                  <ResponsiveContainer width="100%" height={Math.max(180, byDistrict.length * 38)}>
                    <BarChart
                      data={byDistrict}
                      layout="vertical"
                      margin={{ top: 4, right: 24, bottom: 0, left: 64 }}
                    >
                      <CartesianGrid stroke={cc.border} horizontal={false} />
                      <XAxis
                        type="number"
                        tick={{ fontSize: 11, fill: cc.muted }}
                        axisLine={false} tickLine={false}
                      />
                      <YAxis
                        type="category"
                        dataKey="district"
                        tick={{ fontSize: 12, fill: cc.muted, fontWeight: 500 }}
                        axisLine={false} tickLine={false}
                        width={60}
                      />
                      <RechartsTooltip contentStyle={tooltipStyle} />
                      <Bar
                        dataKey="count"
                        fill={cc.primary}
                        fillOpacity={0.9}
                        radius={[0, 4, 4, 0]}
                        maxBarSize={28}
                        label={{
                          position: "right",
                          fontSize: 11,
                          fill: cc.muted,
                          formatter: (v: unknown) => String(v),
                        }}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            {/* Detection throughput */}
            <Card>
              <CardHeader className="border-b pb-4">
                <CardTitle>Detection throughput</CardTitle>
                <CardDescription>Jobs run and detections found per week</CardDescription>
              </CardHeader>
              <CardContent className="pt-4">
                {isLoading ? <ChartSkeleton /> : throughput.length === 0 ? <EmptyChart /> : (
                  <ResponsiveContainer width="100%" height={260}>
                    <LineChart data={throughput} margin={{ top: 4, right: 8, bottom: 0, left: -16 }}>
                      <CartesianGrid stroke={cc.border} vertical={false} />
                      <XAxis
                        dataKey="week"
                        tick={{ fontSize: 10, fill: cc.muted }}
                        axisLine={false} tickLine={false}
                      />
                      <YAxis
                        tick={{ fontSize: 11, fill: cc.muted }}
                        axisLine={false} tickLine={false}
                      />
                      <RechartsTooltip contentStyle={tooltipStyle} />
                      <Legend
                        iconType="circle" iconSize={8}
                        wrapperStyle={{ fontSize: 11, paddingTop: 12, color: cc.muted }}
                      />
                      <Line
                        type="monotone" dataKey="jobs"
                        stroke={cc.muted}
                        strokeWidth={2} dot={false}
                        strokeDasharray="4 4"
                      />
                      <Line
                        type="monotone" dataKey="detections"
                        stroke={cc.primary}
                        strokeWidth={2.5} dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Status distribution */}
          <Card>
            <CardHeader className="border-b pb-4">
              <CardTitle>Flag status distribution</CardTitle>
              <CardDescription>Count of flags in each lifecycle state</CardDescription>
            </CardHeader>
            <CardContent className="pt-4">
              {isLoading ? <ChartSkeleton /> : <StatusDistribution data={data?.status_breakdown} />}
            </CardContent>
          </Card>

          {/* Bottom padding */}
          <div className="h-4" />
        </div>
      </div>
    </div>
  );
}
