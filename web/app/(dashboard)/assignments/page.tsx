"use client";

import { useMemo } from "react";
import Link from "next/link";
import { formatDistanceToNow } from "date-fns";
import { ClipboardList, ArrowRight, CheckCircle2, XCircle, Clock, MapPin } from "lucide-react";
import { TopBar } from "@/components/top-bar";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useFlags } from "@/lib/api/hooks";
import { SEVERITY_BADGE_CLASS, SEVERITY_LABEL, STATUS_BADGE_CLASS, STATUS_LABEL } from "@/lib/severity";
import type { FlagListItem, Severity, FlagStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const VERDICT_ICON: Record<string, React.ElementType> = {
  confirmed: CheckCircle2,
  dismissed: XCircle,
  monitoring: Clock,
  inaccessible: MapPin,
  data_error: XCircle,
};

const VERDICT_COLOR: Record<string, string> = {
  confirmed:    "text-red-500",
  dismissed:    "text-slate-400",
  monitoring:   "text-amber-500",
  inaccessible: "text-slate-400",
  data_error:   "text-slate-400",
};

function AssignmentCard({ flag, completed }: { flag: FlagListItem; completed: boolean }) {
  const sev = flag.severity as Severity;
  const status = flag.status as FlagStatus;

  return (
    <div className={cn(
      "group relative rounded-xl border bg-card p-4 transition-all duration-150",
      !completed && "hover:border-primary/40 hover:shadow-sm"
    )}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0 flex-1">
          <div className="flex flex-col gap-1.5 shrink-0 mt-0.5">
            <Badge variant="outline" className={cn("text-[10px] px-1.5 py-0", SEVERITY_BADGE_CLASS[sev])}>
              {SEVERITY_LABEL[sev]}
            </Badge>
            <Badge variant="outline" className={cn("text-[10px] px-1.5 py-0", STATUS_BADGE_CLASS[status])}>
              {STATUS_LABEL[status]}
            </Badge>
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold truncate">
              {flag.parcel_upi ?? <span className="text-muted-foreground italic">Unmatched parcel</span>}
            </p>
            {flag.owner_name && (
              <p className="text-xs text-muted-foreground truncate">{flag.owner_name}</p>
            )}
            <p className="text-xs text-muted-foreground mt-1">
              {flag.district || "—"}
              {" · "}
              {flag.permit_status === "no_permit" ? "No permit" :
               flag.permit_status === "expired" ? "Expired permit" :
               flag.permit_status === "authorized" ? "Active permit" : "—"}
            </p>
            <p className="text-[10px] text-muted-foreground mt-1.5">
              Flagged {formatDistanceToNow(new Date(flag.created_at), { addSuffix: true })}
              {flag.assigned_at && ` · Assigned ${formatDistanceToNow(new Date(flag.assigned_at), { addSuffix: true })}`}
            </p>
          </div>
        </div>

        {!completed ? (
          <Link
            href={`/assignments/${flag.id}/inspect`}
            className="shrink-0 inline-flex items-center gap-1.5 h-8 px-3 rounded-lg bg-primary text-primary-foreground text-xs font-semibold hover:bg-primary/90 transition-colors"
          >
            Inspect
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        ) : (
          <div className="shrink-0 flex flex-col items-end gap-1">
            <span className={cn("text-[10px] font-semibold uppercase tracking-wide", VERDICT_COLOR[status] ?? "text-slate-400")}>
              {STATUS_LABEL[status]}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

function CardSkeleton() {
  return (
    <div className="rounded-xl border bg-card p-4 space-y-2">
      <div className="flex gap-3">
        <div className="space-y-1.5 shrink-0">
          <Skeleton className="h-5 w-14" />
          <Skeleton className="h-5 w-16" />
        </div>
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-3 w-28" />
          <Skeleton className="h-3 w-20" />
        </div>
        <Skeleton className="h-8 w-20 shrink-0" />
      </div>
    </div>
  );
}

export default function AssignmentsPage() {
  const { data, isLoading } = useFlags({ limit: 500 });
  const flags = data?.results ?? [];

  const pending = useMemo(() =>
    flags
      .filter((f) => f.status === "assigned")
      .sort((a, b) => {
        const sevOrder = { critical: 0, high: 1, medium: 2, low: 3 };
        const diff = (sevOrder[a.severity as Severity] ?? 4) - (sevOrder[b.severity as Severity] ?? 4);
        if (diff !== 0) return diff;
        return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      }),
    [flags]
  );

  const completed = useMemo(() =>
    flags.filter((f) => ["confirmed", "dismissed", "monitoring", "inaccessible", "data_error"].includes(f.status)),
    [flags]
  );

  const header = (
    <div className="flex items-center gap-2">
      <ClipboardList className="h-4 w-4 text-muted-foreground" />
      <span className="text-xl font-semibold">My Assignments</span>
      {pending.length > 0 && (
        <span className="ml-1 text-xs font-bold tabular-nums rounded-full px-2 py-0.5 bg-primary/10 text-primary">
          {pending.length}
        </span>
      )}
    </div>
  );

  return (
    <div className="flex flex-col h-full min-h-0">
      <TopBar breadcrumb="My Assignments" />
      <div className="flex-1 min-h-0 overflow-auto">
        <div className="px-6 py-5 max-w-2xl space-y-8">
          {header}

          {/* Pending tab */}
          <section className="space-y-3">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              Pending — needs site visit
            </p>
            {isLoading ? (
              <div className="space-y-3">
                <CardSkeleton /><CardSkeleton /><CardSkeleton />
              </div>
            ) : pending.length === 0 ? (
              <div className="rounded-xl border border-dashed bg-muted/20 py-10 text-center">
                <ClipboardList className="h-8 w-8 text-muted-foreground/40 mx-auto mb-2" />
                <p className="text-sm font-medium text-muted-foreground">No pending assignments</p>
                <p className="text-xs text-muted-foreground mt-1">You're all caught up.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {pending.map((f) => <AssignmentCard key={f.id} flag={f} completed={false} />)}
              </div>
            )}
          </section>

          {/* Completed tab */}
          {completed.length > 0 && (
            <section className="space-y-3">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                Completed — {completed.length} inspection{completed.length !== 1 ? "s" : ""}
              </p>
              <div className="space-y-3">
                {completed.map((f) => <AssignmentCard key={f.id} flag={f} completed={true} />)}
              </div>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
