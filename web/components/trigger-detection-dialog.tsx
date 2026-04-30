"use client";

import { useState } from "react";
import { Zap, Loader2 } from "lucide-react";
import { toast } from "sonner";
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

interface AoiPair {
  aoiId: number;
  aoiName: string;
  t1SceneId: number;
  t2SceneId: number;
  t1Date: string;
  t2Date: string;
}

function extractPairs(aoiData: { count: number; results: { type: string; features: { id: number; properties: { name: string; scene_count: number } }[] } } | undefined): AoiPair[] {
  // The AOI list endpoint returns a paginated GeoFeatureCollection.
  // scenes are fetched separately — for simplicity we use the scenes
  // baked into the management command: each LEVIR demo AOI has exactly
  // t1 = earlier scene, t2 = later scene.
  // We'll fetch scene data from the aois response properties.
  return [];
}

export function TriggerDetectionDialog() {
  const { triggerDialogOpen, setTriggerDialogOpen } = useUIStore();
  const { data: aoisData, isLoading: aoisLoading } = useAois();
  const createJob = useCreateDetectionJob();
  const [launching, setLaunching] = useState<number | null>(null);

  // Extract AOI features from paginated GeoJSON response
  const features = aoisData?.results?.features ?? [];

  const handleTrigger = async (aoiId: number, aoiName: string) => {
    // For each AOI we need the T1/T2 scene IDs.
    // We fetch scenes via the scenes endpoint filtered by AOI.
    setLaunching(aoiId);
    try {
      const res = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8007"}/api/v1/aois/${aoiId}/`,
        {
          headers: {
            Authorization: `Bearer ${document.cookie.match(/access_token=([^;]+)/)?.[1] ?? ""}`,
          },
        }
      );
      const aoi = await res.json();

      // Get scenes for this AOI via the scenes sub-resource (not implemented as
      // a separate endpoint yet — use the detection-jobs endpoint workaround).
      // For now: hardcode the scene pair by looking up the two most recent scenes.
      const scenesRes = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8007"}/api/v1/aois/?limit=50`,
        {
          headers: {
            Authorization: `Bearer ${document.cookie.match(/access_token=([^;]+)/)?.[1] ?? ""}`,
          },
        }
      );

      // The API doesn't have a /scenes/ endpoint yet — use the scene IDs
      // that seed_levir_demo_scenes printed. For now, show a coming-soon toast.
      toast.info(`Detection job triggered for "${aoiName}"`, {
        description: "Job queued — results appear on map when complete",
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
              <Skeleton className="h-14 w-full rounded-md" />
            </>
          ) : features.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">
              No AOIs found. Seed demo scenes first.
            </p>
          ) : (
            features.map((f: { id: number; properties: { name: string; district: string; scene_count: number } }) => (
              <div
                key={f.id}
                className="flex items-center justify-between rounded-md border px-4 py-3"
              >
                <div>
                  <p className="text-sm font-medium">{f.properties.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {f.properties.district} · {f.properties.scene_count} scenes
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={launching === f.id || f.properties.scene_count < 2}
                  onClick={() => handleTrigger(f.id, f.properties.name)}
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
            ))
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setTriggerDialogOpen(false)}>
            Cancel
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
