"use client";

import { X, ExternalLink, MapPin } from "lucide-react";
import { format } from "date-fns";
import { ReactCompareSlider, ReactCompareSliderImage } from "react-compare-slider";
import { Sheet, SheetContent, SheetHeader } from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useUIStore } from "@/lib/store";
import { useFlag, useFlagImagery } from "@/lib/api/hooks";
import { SEVERITY_BADGE_CLASS, SEVERITY_LABEL, STATUS_BADGE_CLASS } from "@/lib/severity";
import type { FlagDetail, Severity, FlagStatus } from "@/lib/api/types";

const ADMIN_URL = process.env.NEXT_PUBLIC_API_URL?.replace(":8007", ":8007") ?? "http://localhost:8007";

function proxyUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  return `/api/imagery?url=${encodeURIComponent(url)}`;
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
    return <Skeleton className="w-full h-[280px] rounded-md" />;
  }

  const t1 = proxyUrl(data?.t1_url);
  const t2 = proxyUrl(data?.t2_url);

  if (!t1 || !t2) {
    return (
      <div className="w-full h-[280px] rounded-md bg-muted flex items-center justify-center">
        <p className="text-sm text-muted-foreground">Imagery not available</p>
      </div>
    );
  }

  return (
    <div className="rounded-md overflow-hidden border">
      <ReactCompareSlider
        style={{ height: 280 }}
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

function FlagContent({ flag }: { flag: FlagDetail }) {
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
          {flag.status.replace("_", " ")}
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
        <Button
          size="sm"
          variant="outline"
          className="flex-1"
          onClick={() => console.log("Generate report — Phase 2")}
        >
          Generate report
        </Button>
      </div>
    </div>
  );
}

export function FlagDetailSheet() {
  const { drawerOpen, selectedFlagId, closeDrawer } = useUIStore();
  const { data: flag, isLoading } = useFlag(selectedFlagId);

  return (
    <Sheet open={drawerOpen} onOpenChange={(open: boolean) => !open && closeDrawer()}>
      <SheetContent
        side="right"
        className="w-full sm:w-[480px] sm:max-w-[480px] p-0 flex flex-col"
      >
        <SheetHeader className="px-6 py-4 border-b shrink-0 flex-row items-center justify-between space-y-0">
          <h2 className="text-base font-semibold">Flag detail</h2>
          <Button variant="ghost" size="icon" className="h-8 w-8" onClick={closeDrawer}>
            <X className="h-4 w-4" />
          </Button>
        </SheetHeader>

        <ScrollArea className="flex-1">
          <div className="px-6 py-6">
            {isLoading ? (
              <div className="space-y-4">
                <Skeleton className="h-6 w-40" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-3/4" />
                <Skeleton className="h-[280px] w-full rounded-md" />
              </div>
            ) : flag ? (
              <FlagContent flag={flag} />
            ) : (
              <p className="text-sm text-muted-foreground">Flag not found.</p>
            )}
          </div>
        </ScrollArea>
      </SheetContent>
    </Sheet>
  );
}
