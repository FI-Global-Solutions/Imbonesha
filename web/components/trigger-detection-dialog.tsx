"use client";

import { useState, useEffect } from "react";
import {
  Satellite, Zap, CheckCircle2, XCircle, Loader2,
  Clock, ChevronRight, AlertTriangle, RefreshCw, History,
} from "lucide-react";
import { toast } from "sonner";
import { format, formatDistanceToNow } from "date-fns";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useUIStore } from "@/lib/store";
import { useAois, useCreateDetectionJob, useDetectionJobs, useDetectionJob } from "@/lib/api/hooks";
import type { DetectionJob } from "@/lib/api/types";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface AoiFeature {
  id: number;
  properties: {
    name: string;
    district: string;
    scene_count: number;
    latest_scenes: { id: number; captured_at: string; label: string }[];
  };
}

// ---------------------------------------------------------------------------
// Job status helpers
// ---------------------------------------------------------------------------

function StatusBadge({ status }: { status: DetectionJob["status"] }) {
  const map = {
    queued:    { label: "Queued",    cls: "bg-muted text-muted-foreground border-border", icon: Clock },
    running:   { label: "Running",   cls: "bg-blue-500/10 text-blue-500 border-blue-500/20", icon: Loader2 },
    completed: { label: "Complete",  cls: "bg-emerald-500/10 text-emerald-500 border-emerald-500/20", icon: CheckCircle2 },
    failed:    { label: "Failed",    cls: "bg-destructive/10 text-destructive border-destructive/20", icon: XCircle },
  } as const;
  const { label, cls, icon: Icon } = map[status];
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold", cls)}>
      <Icon className={cn("h-2.5 w-2.5", status === "running" && "animate-spin")} />
      {label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Live job tracker — shows progress for a single active job
// ---------------------------------------------------------------------------

function LiveJobTracker({ jobId, onDone }: { jobId: number; onDone: () => void }) {
  const { data: job } = useDetectionJob(jobId);

  useEffect(() => {
    if (job?.status === "completed" || job?.status === "failed") {
      if (job.status === "completed") {
        toast.success(`Detection complete — ${job.detection_count} new flag${job.detection_count !== 1 ? "s" : ""} raised`, {
          description: `AOI: ${job.aoi_name}`,
        });
      } else {
        toast.error("Detection job failed", { description: job.error_message || "Unknown error" });
      }
      onDone();
    }
  }, [job?.status]);

  if (!job) return null;

  const steps = [
    { label: "Job queued",          done: true },
    { label: "Downloading scenes",  done: job.status !== "queued" },
    { label: "Running ML inference", done: job.status === "completed" || job.status === "failed" },
    { label: "Creating flags",      done: job.status === "completed" },
  ];

  return (
    <div className="rounded-xl border border-blue-500/20 bg-blue-500/5 p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-7 w-7 rounded-full bg-blue-500/10 flex items-center justify-center">
            <Satellite className="h-3.5 w-3.5 text-blue-500" />
          </div>
          <div>
            <p className="text-sm font-semibold leading-none">{job.aoi_name}</p>
            <p className="text-[10px] text-muted-foreground mt-0.5">Job #{job.id}</p>
          </div>
        </div>
        <StatusBadge status={job.status} />
      </div>

      {/* Step progress */}
      <div className="space-y-1.5">
        {steps.map((step, i) => {
          const isActive = !step.done && steps[i - 1]?.done;
          const isFailed = job.status === "failed" && isActive;
          return (
            <div key={step.label} className="flex items-center gap-2">
              <div className={cn(
                "h-4 w-4 rounded-full flex items-center justify-center shrink-0",
                step.done && !isFailed ? "bg-emerald-500/15" : isActive ? "bg-blue-500/15" : "bg-muted"
              )}>
                {step.done && !isFailed
                  ? <CheckCircle2 className="h-2.5 w-2.5 text-emerald-500" />
                  : isActive && !isFailed
                    ? <Loader2 className="h-2.5 w-2.5 text-blue-500 animate-spin" />
                    : isFailed
                      ? <XCircle className="h-2.5 w-2.5 text-destructive" />
                      : <div className="h-1.5 w-1.5 rounded-full bg-muted-foreground/30" />
                }
              </div>
              <span className={cn(
                "text-xs",
                step.done ? "text-foreground" : "text-muted-foreground"
              )}>
                {step.label}
              </span>
            </div>
          );
        })}
      </div>

      {job.status === "completed" && (
        <div className="flex items-center gap-1.5 rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-3 py-2">
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
          <span className="text-xs font-medium text-emerald-600 dark:text-emerald-400">
            {job.detection_count} flag{job.detection_count !== 1 ? "s" : ""} raised — map updated
          </span>
        </div>
      )}

      {job.status === "failed" && job.error_message && (
        <div className="flex items-start gap-1.5 rounded-lg bg-destructive/10 border border-destructive/20 px-3 py-2">
          <AlertTriangle className="h-3.5 w-3.5 text-destructive shrink-0 mt-0.5" />
          <span className="text-xs text-destructive">{job.error_message}</span>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// AOI card — one per area of interest
// ---------------------------------------------------------------------------

function AoiCard({
  feature,
  launching,
  onTrigger,
}: {
  feature: AoiFeature;
  launching: boolean;
  onTrigger: () => void;
}) {
  const scenes = feature.properties.latest_scenes;
  const canRun = scenes.length >= 2;
  const t1 = scenes[0];
  const t2 = scenes[1];

  return (
    <div className={cn(
      "group relative rounded-xl border bg-card p-4 transition-all duration-150",
      canRun
        ? "hover:border-primary/40 hover:shadow-sm cursor-default"
        : "opacity-60 cursor-not-allowed"
    )}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-3 min-w-0">
          <div className="h-9 w-9 rounded-lg bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
            <Satellite className="h-4 w-4 text-primary" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold truncate">{feature.properties.name}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{feature.properties.district}</p>

            {canRun ? (
              <div className="flex items-center gap-1.5 mt-2">
                <div className="flex items-center gap-1 rounded-md bg-muted px-2 py-0.5">
                  <span className="text-[10px] text-muted-foreground font-medium">T1</span>
                  <span className="text-[10px] font-semibold">{format(new Date(t1.captured_at), "MMM yyyy")}</span>
                </div>
                <ChevronRight className="h-3 w-3 text-muted-foreground" />
                <div className="flex items-center gap-1 rounded-md bg-primary/10 px-2 py-0.5">
                  <span className="text-[10px] text-primary font-medium">T2</span>
                  <span className="text-[10px] font-semibold text-primary">{format(new Date(t2.captured_at), "MMM yyyy")}</span>
                </div>
              </div>
            ) : (
              <p className="text-[10px] text-muted-foreground mt-1.5">
                Needs at least 2 scenes
              </p>
            )}
          </div>
        </div>

        <Button
          size="sm"
          disabled={!canRun || launching}
          onClick={onTrigger}
          className="shrink-0 gap-1.5"
        >
          {launching
            ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
            : <Zap className="h-3.5 w-3.5" />
          }
          {launching ? "Queuing…" : "Run"}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Recent jobs list
// ---------------------------------------------------------------------------

function RecentJobs({ jobs }: { jobs: DetectionJob[] }) {
  const recent = jobs.slice(0, 6);
  if (recent.length === 0) return null;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <History className="h-3.5 w-3.5 text-muted-foreground" />
        <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Recent jobs</span>
      </div>
      <div className="space-y-1.5">
        {recent.map((job) => (
          <div
            key={job.id}
            className="flex items-center justify-between rounded-lg border bg-muted/30 px-3 py-2"
          >
            <div className="flex items-center gap-2.5 min-w-0">
              <div className={cn(
                "h-1.5 w-1.5 rounded-full shrink-0",
                job.status === "completed" ? "bg-emerald-500"
                  : job.status === "failed" ? "bg-destructive"
                  : job.status === "running" ? "bg-blue-500 animate-pulse"
                  : "bg-muted-foreground"
              )} />
              <div className="min-w-0">
                <p className="text-xs font-medium truncate">{job.aoi_name}</p>
                <p className="text-[10px] text-muted-foreground">
                  {job.ran_at
                    ? formatDistanceToNow(new Date(job.ran_at), { addSuffix: true })
                    : formatDistanceToNow(new Date(job.created_at), { addSuffix: true })}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {job.status === "completed" && (
                <span className="text-[10px] text-muted-foreground">
                  {job.detection_count} flag{job.detection_count !== 1 ? "s" : ""}
                </span>
              )}
              <StatusBadge status={job.status} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main dialog
// ---------------------------------------------------------------------------

export function TriggerDetectionDialog() {
  const { triggerDialogOpen, setTriggerDialogOpen } = useUIStore();
  const { data: aoisData, isLoading: aoisLoading } = useAois();
  const { data: allJobs = [] } = useDetectionJobs();
  const createJob = useCreateDetectionJob();

  const [launchingAoi, setLaunchingAoi] = useState<number | null>(null);
  const [activeJobId, setActiveJobId] = useState<number | null>(null);

  // Restore active job on reopen if it's still running
  useEffect(() => {
    if (!triggerDialogOpen) return;
    const inFlight = allJobs.find((j) => j.status === "queued" || j.status === "running");
    // eslint-disable-next-line react-hooks/set-state-in-effect
    if (inFlight && activeJobId === null) setActiveJobId(inFlight.id);
  }, [triggerDialogOpen, allJobs]);

  const features: AoiFeature[] = aoisData?.results?.features ?? aoisData?.features ?? [];
  const recentJobs = allJobs.filter((j) => j.status === "completed" || j.status === "failed");

  const handleTrigger = async (feature: AoiFeature) => {
    const scenes = feature.properties.latest_scenes;
    if (scenes.length < 2) return;
    setLaunchingAoi(feature.id);
    try {
      const job = await createJob.mutateAsync({
        t1_scene_id: scenes[0].id,
        t2_scene_id: scenes[1].id,
      });
      setActiveJobId(job.id);
      toast.info(`Detection queued for "${feature.properties.name}"`, {
        description: "Watch the progress below.",
      });
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { non_field_errors?: string[] } } })
        ?.response?.data?.non_field_errors?.[0] ?? "Failed to start job";
      toast.error(msg);
    } finally {
      setLaunchingAoi(null);
    }
  };

  return (
    <Dialog open={triggerDialogOpen} onOpenChange={setTriggerDialogOpen}>
      <DialogContent className="sm:max-w-[500px] p-0 gap-0 overflow-hidden">
        {/* Header */}
        <DialogHeader className="px-6 pt-6 pb-4 border-b border-border/60">
          <div className="flex items-center gap-3">
            <div className="h-9 w-9 rounded-xl bg-primary/10 flex items-center justify-center">
              <Satellite className="h-4.5 w-4.5 text-primary" />
            </div>
            <div>
              <DialogTitle className="text-base">Run Detection</DialogTitle>
              <DialogDescription className="text-xs mt-0.5">
                Select an AOI to run the ML change detection pipeline
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <ScrollArea className="max-h-[70vh]">
          <div className="px-6 py-5 space-y-5">
            {/* Live job tracker */}
            {activeJobId && (
              <LiveJobTracker
                jobId={activeJobId}
                onDone={() => {
                  // Keep showing result for 4 s then clear
                  setTimeout(() => setActiveJobId(null), 4_000);
                }}
              />
            )}

            {/* AOI list */}
            <div className="space-y-2">
              <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                Areas of interest
              </p>
              {aoisLoading ? (
                <div className="space-y-2">
                  <Skeleton className="h-[76px] w-full rounded-xl" />
                  <Skeleton className="h-[76px] w-full rounded-xl" />
                </div>
              ) : features.length === 0 ? (
                <div className="flex flex-col items-center gap-2 py-8 text-center">
                  <div className="h-10 w-10 rounded-full bg-muted flex items-center justify-center">
                    <RefreshCw className="h-4 w-4 text-muted-foreground" />
                  </div>
                  <p className="text-sm font-medium">No AOIs found</p>
                  <p className="text-xs text-muted-foreground">Seed demo scenes first with<br /><code className="font-mono text-xs bg-muted px-1 rounded">manage.py seed_levir_demo_scenes</code></p>
                </div>
              ) : (
                features.map((f) => (
                  <AoiCard
                    key={f.id}
                    feature={f}
                    launching={launchingAoi === f.id}
                    onTrigger={() => handleTrigger(f)}
                  />
                ))
              )}
            </div>

            {/* Recent jobs */}
            {recentJobs.length > 0 && (
              <>
                <Separator />
                <RecentJobs jobs={recentJobs} />
              </>
            )}
          </div>
        </ScrollArea>
      </DialogContent>
    </Dialog>
  );
}
