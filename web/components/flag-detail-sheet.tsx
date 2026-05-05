"use client";

import { useState } from "react";
import { X, ExternalLink, MapPin, UserCheck, UserX, CheckCircle2, Eye, RefreshCw } from "lucide-react";
import { format, formatDistanceToNow } from "date-fns";
import { toast } from "sonner";
import { ReactCompareSlider, ReactCompareSliderImage } from "react-compare-slider";
import { Sheet, SheetContent, SheetHeader } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useUIStore } from "@/lib/store";
import { useFlag, useFlagImagery, useMe, useAssignFlag, useUnassignFlag } from "@/lib/api/hooks";
import { AssignInspectorDialog } from "@/components/assign-inspector-dialog";
import { SEVERITY_BADGE_CLASS, SEVERITY_LABEL, STATUS_BADGE_CLASS, STATUS_LABEL } from "@/lib/severity";
import type { FlagDetail, Severity, FlagStatus, AuditLog } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const ADMIN_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8007";

// Stream URLs come from the API as absolute URLs pointing to /api/v1/flags/{id}/stream/?t=t1|t2
// Append the JWT so the plain <img> tag can authenticate without an Authorization header.
function authedImageUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  if (typeof document === "undefined") return url;
  const token = document.cookie.match(/(?:^|; )access_token=([^;]*)/)?.[1];
  if (!token) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}token=${encodeURIComponent(decodeURIComponent(token))}`;
}

function PermitBlock({ flag }: { flag: FlagDetail }) {
  const p = flag.parcel?.active_permit;
  const permitStatus = flag.permit_status;

  if (p) {
    return (
      <div className="rounded-md border border-green-200 bg-green-50 dark:border-green-900 dark:bg-green-950 p-4 space-y-1">
        <p className="text-sm font-semibold text-green-700 dark:text-green-400">Active permit</p>
        <p className="text-xs text-muted-foreground font-mono">{p.permit_no}</p>
        <p className="text-xs text-muted-foreground">{p.get_category_display}</p>
        {p.expiry_date && (
          <p className="text-xs text-muted-foreground">
            Expires {format(new Date(p.expiry_date), "d MMM yyyy")}
          </p>
        )}
      </div>
    );
  }

  if (permitStatus === "expired") {
    return (
      <div className="rounded-md border border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950 p-4">
        <p className="text-sm font-semibold text-amber-700 dark:text-amber-400">Expired permit</p>
        <p className="text-xs text-muted-foreground mt-0.5">Permit exists but has lapsed</p>
      </div>
    );
  }

  if (permitStatus === "other") {
    return (
      <div className="rounded-md border border-amber-200 bg-amber-50 dark:border-amber-900 dark:bg-amber-950 p-4">
        <p className="text-sm font-semibold text-amber-700 dark:text-amber-400">Permit issue</p>
        <p className="text-xs text-muted-foreground mt-0.5">Permit present but not active</p>
      </div>
    );
  }

  return (
    <div className="rounded-md border border-red-200 bg-red-50 dark:border-red-900 dark:bg-red-950 p-4">
      <p className="text-sm font-semibold text-red-700 dark:text-red-400">No permit</p>
      <p className="text-xs text-muted-foreground mt-0.5">No construction permit found for this parcel</p>
    </div>
  );
}

function ImageComparison({ flagId }: { flagId: number }) {
  const { data, isLoading } = useFlagImagery(flagId);

  if (isLoading) {
    return <Skeleton className="w-full h-70 rounded-md" />;
  }

  const t1 = authedImageUrl(data?.t1_url);
  const t2 = authedImageUrl(data?.t2_url);

  if (!t1 || !t2) {
    return (
      <div className="w-full h-70 rounded-md bg-muted flex items-center justify-center">
        <p className="text-sm text-muted-foreground">Imagery not available</p>
      </div>
    );
  }

  return (
    <div className="rounded-md overflow-hidden border">
      <ReactCompareSlider
        style={{ height: 280 }}  /* 280px = h-70 in Tailwind */
        itemOne={
          <ReactCompareSliderImage
            src={t1}
            alt="Before (T1)"
            style={{ objectFit: "cover" }}
          />
        }
        itemTwo={
          <ReactCompareSliderImage
            src={t2}
            alt="After (T2)"
            style={{ objectFit: "cover" }}
          />
        }
      />
      <div className="flex justify-between px-3 py-1.5 bg-muted/50 text-xs text-muted-foreground">
        <span>Before · {data?.t1_captured_at ? format(new Date(data.t1_captured_at), "MMM yyyy") : "T1"}</span>
        <span>After · {data?.t2_captured_at ? format(new Date(data.t2_captured_at), "MMM yyyy") : "T2"}</span>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Audit timeline event icons + colors
// ---------------------------------------------------------------------------

const EVENT_META: Record<string, { icon: React.ElementType; color: string }> = {
  created:              { icon: CheckCircle2,  color: "text-emerald-500" },
  assigned:             { icon: UserCheck,     color: "text-blue-500" },
  unassigned:           { icon: UserX,         color: "text-slate-400" },
  inspection_submitted: { icon: Eye,           color: "text-amber-500" },
  status_changed:       { icon: RefreshCw,     color: "text-violet-500" },
  updated:              { icon: RefreshCw,     color: "text-slate-400" },
};

function AuditTimeline({ logs }: { logs: AuditLog[] }) {
  if (logs.length === 0) return null;
  return (
    <div className="space-y-3">
      {logs.map((log, i) => {
        const meta = EVENT_META[log.event] ?? { icon: RefreshCw, color: "text-slate-400" };
        const Icon = meta.icon;
        return (
          <div key={log.id} className="flex gap-3">
            <div className="flex flex-col items-center">
              <div className={cn("h-6 w-6 rounded-full bg-muted flex items-center justify-center shrink-0", meta.color)}>
                <Icon className="h-3 w-3" />
              </div>
              {i < logs.length - 1 && <div className="w-px flex-1 bg-border mt-1" />}
            </div>
            <div className="pb-4 min-w-0">
              <p className="text-xs font-medium leading-none capitalize">
                {log.event.replace(/_/g, " ")}
              </p>
              {log.message && (
                <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{log.message}</p>
              )}
              <p className="text-[10px] text-muted-foreground mt-1">
                {log.actor_name ?? "System"} · {formatDistanceToNow(new Date(log.timestamp), { addSuffix: true })}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Assignment block
// ---------------------------------------------------------------------------

function AssignmentBlock({ flag, canAssign }: { flag: FlagDetail; canAssign: boolean }) {
  const [dialogOpen, setDialogOpen] = useState(false);
  const unassign = useUnassignFlag();

  if (flag.assigned_to) {
    return (
      <div className="rounded-md border border-blue-200 bg-blue-50 dark:border-blue-900 dark:bg-blue-950 p-3 space-y-1">
        <div className="flex items-center justify-between">
          <p className="text-xs font-semibold text-blue-700 dark:text-blue-400">Assigned inspector</p>
          {canAssign && (
            <button
              type="button"
              className="text-[10px] text-blue-500 hover:text-blue-700 dark:hover:text-blue-300 transition-colors"
              onClick={async () => {
                try {
                  await unassign.mutateAsync(flag.id);
                  toast.success("Flag unassigned");
                } catch {
                  toast.error("Failed to unassign");
                }
              }}
              disabled={unassign.isPending}
            >
              {unassign.isPending ? "Unassigning…" : "Unassign"}
            </button>
          )}
        </div>
        <p className="text-sm font-medium">{flag.assigned_to.full_name}</p>
        <p className="text-xs text-muted-foreground">{flag.assigned_to.email}</p>
        {flag.assigned_at && (
          <p className="text-[10px] text-muted-foreground">
            Assigned {formatDistanceToNow(new Date(flag.assigned_at), { addSuffix: true })}
            {flag.assigned_by_email ? ` by ${flag.assigned_by_email}` : ""}
          </p>
        )}
      </div>
    );
  }

  if (!canAssign) return null;

  return (
    <>
      <Button
        variant="outline"
        size="sm"
        className="w-full gap-1.5 h-9"
        onClick={() => setDialogOpen(true)}
      >
        <UserCheck className="h-3.5 w-3.5" />
        Assign inspector
      </Button>
      <AssignInspectorDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        flagIds={[flag.id]}
      />
    </>
  );
}

function FlagContent({ flag, canAssign }: { flag: FlagDetail; canAssign: boolean }) {
  const sev = flag.severity as Severity;
  const status = flag.status as FlagStatus;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <Badge variant="outline" className={SEVERITY_BADGE_CLASS[sev]}>
          {SEVERITY_LABEL[sev]}
        </Badge>
        <Badge variant="outline" className={STATUS_BADGE_CLASS[status]}>
          {STATUS_LABEL[status] ?? status}
        </Badge>
        <span className="text-xs text-muted-foreground ml-auto">Flag #{flag.id}</span>
      </div>

      <Separator />

      {/* Parcel info */}
      <section className="space-y-3">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Parcel</h3>
        {flag.parcel_upi ? (
          <div className="space-y-1.5">
            <p className="font-mono text-sm font-medium">{flag.parcel_upi}</p>
            {flag.owner_name && (
              <p className="text-sm">{flag.owner_name}</p>
            )}
            <div className="flex items-center gap-1 text-xs text-muted-foreground">
              <MapPin className="h-3 w-3" />
              {[flag.parcel?.district, flag.parcel?.sector, flag.parcel?.cell]
                .filter(Boolean)
                .join(" · ")}
            </div>
            {flag.parcel?.zone_type && (
              <p className="text-xs text-muted-foreground">
                Zone: <span className="capitalize">{flag.parcel.zone_type.replace(/_/g, " ")}</span>
              </p>
            )}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">No parcel matched (footprint outside registry)</p>
        )}
      </section>

      <Separator />

      {/* Permit status */}
      <section className="space-y-3">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Permit status</h3>
        <PermitBlock flag={flag} />
      </section>

      <Separator />

      {/* Image comparison */}
      <section className="space-y-3">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Satellite imagery</h3>
        <ImageComparison flagId={flag.id} />
      </section>

      <Separator />

      {/* Detection details */}
      <section className="space-y-3">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Detection</h3>
        <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <div>
            <p className="text-xs text-muted-foreground">Confidence</p>
            <p className="font-medium">{Math.round((flag.detection?.confidence ?? 0) * 100)}%</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Footprint</p>
            <p className="font-medium">{Math.round(flag.detection?.area_sqm ?? 0)} m²</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Change type</p>
            <p className="font-medium capitalize">{flag.detection?.change_type?.replace(/_/g, " ")}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground">Flagged</p>
            <p className="font-medium">{format(new Date(flag.created_at), "d MMM yyyy")}</p>
          </div>
        </div>
      </section>

      <Separator />

      {/* Assignment */}
      {(canAssign || flag.assigned_to) && (
        <section className="space-y-3">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Assignment</h3>
          <AssignmentBlock flag={flag} canAssign={canAssign} />
        </section>
      )}

      {(canAssign || flag.assigned_to) && <Separator />}

      {/* Inspections */}
      {flag.inspections.length > 0 && (
        <>
          <section className="space-y-3">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Inspections</h3>
            <div className="space-y-2">
              {flag.inspections.map((ins) => (
                <div key={ins.id} className="rounded-md border bg-muted/30 p-3 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold capitalize">{ins.verdict.replace(/_/g, " ")}</span>
                    <span className="text-[10px] text-muted-foreground">{ins.inspector_name}</span>
                  </div>
                  {ins.notes && <p className="text-xs text-muted-foreground italic">"{ins.notes}"</p>}
                  <div className="flex gap-3 text-[10px] text-muted-foreground">
                    {ins.construction_stage && <span>Stage: {ins.construction_stage}</span>}
                    {ins.estimated_floors != null && <span>{ins.estimated_floors} floor{ins.estimated_floors !== 1 ? "s" : ""}</span>}
                    {ins.visited_at && <span>Visited {format(new Date(ins.visited_at), "d MMM yyyy")}</span>}
                  </div>
                </div>
              ))}
            </div>
          </section>
          <Separator />
        </>
      )}

      {/* Actions */}
      <div className="flex gap-2">
        <a
          href={`${ADMIN_URL}/admin/flags/flag/${flag.id}/change/`}
          target="_blank"
          rel="noopener noreferrer"
          className="flex-1 inline-flex h-7 items-center justify-center gap-1 rounded-[min(var(--radius-md),12px)] border border-border bg-background px-2.5 text-[0.8rem] font-medium text-foreground hover:bg-muted transition-colors"
        >
          <ExternalLink className="h-3.5 w-3.5" />
          Open in admin
        </a>
      </div>

      <Separator />

      {/* Audit timeline */}
      {flag.audit_logs.length > 0 && (
        <section className="space-y-3">
          <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Activity</h3>
          <AuditTimeline logs={flag.audit_logs} />
        </section>
      )}
    </div>
  );
}

export function FlagDetailSheet() {
  const { drawerOpen, selectedFlagId, closeDrawer } = useUIStore();
  const { data: flag, isLoading } = useFlag(selectedFlagId);
  const { data: me } = useMe();
  const canAssign = me?.role === "admin" || me?.role === "district_admin";

  return (
    <Sheet open={drawerOpen} onOpenChange={(open: boolean) => !open && closeDrawer()}>
      <SheetContent
        side="right"
        showCloseButton={false}
        className="w-full sm:w-120 sm:max-w-120 p-0 flex flex-col"
      >
        <SheetHeader className="px-6 py-4 border-b shrink-0 flex-row items-center justify-between space-y-0">
          <h2 className="text-base font-semibold">Flag detail</h2>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={closeDrawer}>
            <X className="h-4 w-4" />
          </Button>
        </SheetHeader>

        <ScrollArea className="flex-1 min-h-0">
          <div className="px-6 py-6">
            {isLoading ? (
              <div className="space-y-4">
                <Skeleton className="h-6 w-40" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-70 w-full rounded-md" />
              </div>
            ) : flag ? (
              <FlagContent flag={flag} canAssign={canAssign} />
            ) : (
              <p className="text-sm text-muted-foreground">Flag not found.</p>
            )}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
