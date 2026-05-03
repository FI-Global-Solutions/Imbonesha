"use client";

import { Satellite } from "lucide-react";
import { Button } from "@/components/ui/button";
import { MapView } from "@/components/map/map-view";
import { TriggerDetectionDialog } from "@/components/trigger-detection-dialog";
import { TopBar } from "@/components/top-bar";
import { useUIStore } from "@/lib/store";
import { useDetectionJobs } from "@/lib/api/hooks";

function RunDetectionButton() {
  const setOpen = useUIStore((s) => s.setTriggerDialogOpen);
  const { data: jobs = [] } = useDetectionJobs();
  const hasActive = jobs.some((j) => j.status === "queued" || j.status === "running");

  return (
    <Button
      size="sm"
      variant={hasActive ? "default" : "outline"}
      className="h-8 gap-1.5 text-xs font-medium"
      onClick={() => setOpen(true)}
    >
      <Satellite className={`h-3.5 w-3.5 ${hasActive ? "animate-pulse" : ""}`} />
      {hasActive ? "Job running…" : "Run Detection"}
    </Button>
  );
}

export default function HomePage() {
  return (
    <>
      <TopBar breadcrumb="Map" actions={<RunDetectionButton />} />
      <div className="flex-1 relative overflow-hidden min-h-0">
        <MapView />
        <TriggerDetectionDialog />
      </div>
    </>
  );
}
