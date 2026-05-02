"use client";

import {
  AreaChart, Area, BarChart, Bar, PieChart, Pie, Cell,
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip,
  Legend, ResponsiveContainer,
} from "recharts";
import { format, parseISO } from "date-fns";

import { TopBar } from "@/components/top-bar";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useAnalytics } from "@/lib/api/hooks";

// Severity fill colors (match app palette)
const SEV_COLORS: Record<string, string> = {
  critical: "#dc2626",
  high:     "#ea580c",
  medium:   "#f59e0b",
  low:      "#16a34a",
};

const PERMIT_COLORS: Record<string, string> = {
  active:    "#16a34a",
  expired:   "#f59e0b",
  no_permit: "#dc2626",
  other:     "#ea580c",
};

const PERMIT_LABELS: Record<string, string> = {
  active:    "Active",
  expired:   "Expired",
  no_permit: "No permit",
  other:     "Other issue",
};

function KpiCard({
  label, value, sub,
}: { label: string; value: string | number | null; sub?: string }) {
  return (
    <Card>
      <CardContent className="pt-6">
        <p className="text-xs uppercase tracking-wide text-muted-foreground font-medium">{label}</p>
        {value === null || value === undefined
          ? <p className="text-3xl font-semibold tabular-nums mt-2 text-muted-foreground">—</p>
          : <p className="text-3xl font-semibold tabular-nums mt-2">{value}</p>
        }
        {sub && <p className="text-xs text-muted-foreground mt-1">{sub}</p>}
      </CardContent>
    </Card>
  );
}

function ChartSkeleton() {
  return <Skeleton className="w-full h-[240px] rounded-md" />;
}

const tooltipStyle = {
  backgroundColor: "hsl(var(--popover))",
  border: "1px solid hsl(var(--border))",
  borderRadius: "8px",
  color: "hsl(var(--popover-foreground))",
  fontSize: 12,
  boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1)",
};

export default function AnalyticsPage() {
  const { data, isLoading } = useAnalytics();

  const kpis = data?.kpis;
  const flagsOverTime = data?.flags_over_time ?? [];
  const byDistrict = data?.flags_by_district ?? [];
  const permitBreakdown = data?.permit_status_breakdown;
  const throughput = data?.detection_throughput ?? [];

  const permitPie = permitBreakdown
    ? Object.entries(permitBreakdown).map(([k, v]) => ({
        name: PERMIT_LABELS[k] ?? k,
        value: v,
        key: k,
      }))
    : [];

  const totalPermit = permitPie.reduce((acc, p) => acc + p.value, 0);

  return (
    <div className="flex flex-col h-full min-h-0">
      <TopBar breadcrumb="Analytics" />

      <div className="flex-1 min-h-0 overflow-auto">
        <div className="px-6 py-5 space-y-6 max-w-[1400px]">
          {/* Page header */}
          <div>
            <h1 className="text-xl font-semibold text-foreground">Analytics</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              Overview of flag activity and detection performance
            </p>
          </div>

          {/* KPI row */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {isLoading ? (
              [...Array(4)].map((_, i) => (
                <Card key={i}>
                  <CardContent className="pt-6 space-y-2">
                    <Skeleton className="h-3 w-24" />
                    <Skeleton className="h-8 w-16" />
                    <Skeleton className="h-3 w-32" />
                  </CardContent>
                </Card>
              ))
            ) : (
              <>
                <KpiCard
                  label="Total flags"
                  value={kpis?.total_flags ?? null}
                  sub="All time"
                />
                <KpiCard
                  label="Awaiting review"
                  value={kpis?.awaiting_review ?? null}
                  sub="Pending inspector assignment"
                />
                <KpiCard
                  label="Confirmed unauthorized"
                  value={kpis?.confirmed_unauthorized_30d ?? null}
                  sub="Last 30 days"
                />
                <KpiCard
                  label="Avg time to inspection"
                  value={kpis?.avg_time_to_inspection_hours !== null ? `${kpis?.avg_time_to_inspection_hours}h` : null}
                  sub="From flag to verdict"
                />
              </>
            )}
          </div>

          {/* Charts row 1 */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Flags over time — wide */}
            <Card className="lg:col-span-2">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Flags over time</CardTitle>
                <CardDescription>Last 90 days by severity</CardDescription>
              </CardHeader>
              <CardContent>
                {isLoading ? <ChartSkeleton /> : flagsOverTime.length === 0 ? (
                  <div className="h-[240px] flex items-center justify-center">
                    <p className="text-sm text-muted-foreground">No data yet</p>
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height={240}>
                    <AreaChart data={flagsOverTime} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                      <XAxis
                        dataKey="date"
                        tickFormatter={(v) => format(parseISO(v), "MMM d")}
                        tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                        axisLine={false}
                        tickLine={false}
                        interval="preserveStartEnd"
                      />
                      <YAxis
                        tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <RechartsTooltip
                        contentStyle={tooltipStyle}
                        labelFormatter={(v) => format(parseISO(v as string), "d MMM yyyy")}
                      />
                      <Legend
                        iconType="circle"
                        iconSize={8}
                        wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                      />
                      {(["critical", "high", "medium", "low"] as const).map((sev) => (
                        <Area
                          key={sev}
                          type="monotone"
                          dataKey={sev}
                          stackId="1"
                          stroke={SEV_COLORS[sev]}
                          fill={SEV_COLORS[sev]}
                          fillOpacity={0.15}
                          strokeWidth={1.5}
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
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Permit breakdown</CardTitle>
                <CardDescription>By permit status</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col items-center">
                {isLoading ? <ChartSkeleton /> : permitPie.length === 0 ? (
                  <div className="h-[240px] flex items-center justify-center">
                    <p className="text-sm text-muted-foreground">No data yet</p>
                  </div>
                ) : (
                  <>
                    <ResponsiveContainer width="100%" height={200}>
                      <PieChart>
                        <Pie
                          data={permitPie}
                          cx="50%"
                          cy="50%"
                          innerRadius={60}
                          outerRadius={90}
                          paddingAngle={2}
                          dataKey="value"
                        >
                          {permitPie.map((entry) => (
                            <Cell key={entry.key} fill={PERMIT_COLORS[entry.key] ?? "#888"} />
                          ))}
                        </Pie>
                        <RechartsTooltip contentStyle={tooltipStyle} />
                      </PieChart>
                    </ResponsiveContainer>
                    <div className="flex flex-col gap-1.5 w-full mt-1">
                      {permitPie.map((entry) => (
                        <div key={entry.key} className="flex items-center justify-between text-xs">
                          <div className="flex items-center gap-1.5">
                            <span
                              className="inline-block h-2 w-2 rounded-full"
                              style={{ backgroundColor: PERMIT_COLORS[entry.key] ?? "#888" }}
                            />
                            <span className="text-muted-foreground">{entry.name}</span>
                          </div>
                          <span className="font-medium tabular-nums">
                            {entry.value}
                            <span className="text-muted-foreground ml-1 font-normal">
                              ({totalPermit ? Math.round(entry.value / totalPermit * 100) : 0}%)
                            </span>
                          </span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Charts row 2 */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {/* Flags by district horizontal bar */}
            <Card className="lg:col-span-2">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Flags by district</CardTitle>
                <CardDescription>Total flags per administrative district</CardDescription>
              </CardHeader>
              <CardContent>
                {isLoading ? <ChartSkeleton /> : byDistrict.length === 0 ? (
                  <div className="h-[240px] flex items-center justify-center">
                    <p className="text-sm text-muted-foreground">No data yet</p>
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height={240}>
                    <BarChart
                      data={byDistrict}
                      layout="vertical"
                      margin={{ top: 4, right: 16, bottom: 0, left: 60 }}
                    >
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" horizontal={false} />
                      <XAxis
                        type="number"
                        tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        type="category"
                        dataKey="district"
                        tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                        axisLine={false}
                        tickLine={false}
                        width={56}
                      />
                      <RechartsTooltip contentStyle={tooltipStyle} />
                      <Bar
                        dataKey="count"
                        fill="hsl(var(--primary))"
                        fillOpacity={0.85}
                        radius={[0, 3, 3, 0]}
                        maxBarSize={24}
                      />
                    </BarChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>

            {/* Detection throughput line */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium">Detection throughput</CardTitle>
                <CardDescription>Jobs and detections per week</CardDescription>
              </CardHeader>
              <CardContent>
                {isLoading ? <ChartSkeleton /> : throughput.length === 0 ? (
                  <div className="h-[240px] flex items-center justify-center">
                    <p className="text-sm text-muted-foreground">No data yet</p>
                  </div>
                ) : (
                  <ResponsiveContainer width="100%" height={240}>
                    <LineChart data={throughput} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" vertical={false} />
                      <XAxis
                        dataKey="week"
                        tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <RechartsTooltip contentStyle={tooltipStyle} />
                      <Legend
                        iconType="circle"
                        iconSize={8}
                        wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
                      />
                      <Line
                        type="monotone"
                        dataKey="jobs"
                        stroke="hsl(var(--muted-foreground))"
                        strokeWidth={1.5}
                        dot={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="detections"
                        stroke="hsl(var(--primary))"
                        strokeWidth={1.5}
                        dot={false}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
