"use client";

import { useState } from "react";
import { Zap, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { format } from "date-fns";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useUIStore } from "@/lib/store";
import { useAois, useCreateDetectionJob } from "@/lib/api/hooks";

interface AoiFeature {
  id: number;
  properties: {
    name: string;
    district: string;
    scene_count: number;
    latest_scenes: { id: number; captured_at: string; label: string }[];
  };
}

export function TriggerDetectionDialog() {
  const { triggerDialogOpen, setTriggerDialogOpen } = useUIStore();
  const { data: aoisData, isLoading: aoisLoading } = useAois();
  const createJob = useCreateDetectionJob();
  const [launching, setLaunching] = useState<number | null>(null);

  const features: AoiFeature[] = aoisData?.results?.features ?? [];

  const handleTrigger = async (feature: AoiFeature) => {
    const scenes = feature.properties.latest_scenes;
    if (scenes.length < 2) return;

    const t1 = scenes[0];
    const t2 = scenes[1];

    setLaunching(feature.id);
    try {
      await createJob.mutateAsync({ t1_scene_id: t1.id, t2_scene_id: t2.id });
      toast.success(`Detection job queued for "${feature.properties.name}"`, {
        description: "New flags will appear on the map when the job completes.",
      });
      setTriggerDialogOpen(false);
    } catch {
      toast.error("Failed to trigger detection job");
    } finally {
      setLaunching(null);
    }
  };

  return (
    <Dialog open={triggerDialogOpen} onOpenChange={setTriggerDialogOpen}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle>Trigger detection</DialogTitle>
          <DialogDescription>
            Run the change detection pipeline against the latest scene pair for an AOI.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-2 py-2">
          {aoisLoading ? (
            <>
              <Skeleton className="h-14 w-full rounded-md" />
              <Skeleton className="h-14 w-full rounded-md" />
            </>
          ) : features.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">
              No AOIs found. Seed demo scenes first.
            </p>
          ) : (
            features.map((f) => {
              const scenes = f.properties.latest_scenes;
              const canRun = scenes.length >= 2;
              const t1Label = canRun ? format(new Date(scenes[0].captured_at), "MMM yyyy") : null;
              const t2Label = canRun ? format(new Date(scenes[1].captured_at), "MMM yyyy") : null;

              return (
                <div
                  key={f.id}
                  className="flex items-center justify-between rounded-md border px-4 py-3"
                >
                  <div>
                    <p className="text-sm font-medium">{f.properties.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {canRun
                        ? `${f.properties.district} · ${t1Label} → ${t2Label}`
                        : "Needs at least two scenes"}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!canRun || launching === f.id}
                    onClick={() => handleTrigger(f)}
                  >
                    {launching === f.id ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <>
                        <Zap className="mr-1.5 h-3.5 w-3.5" />
                        Run
                      </>
                    )}
                  </Button>
                </div>
              );
            })
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" size="sm" onClick={() => setTriggerDialogOpen(false)}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
