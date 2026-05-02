import { MapView } from "@/components/map/map-view";
import { TriggerDetectionDialog } from "@/components/trigger-detection-dialog";

export default function HomePage() {
  return (
    <div className="flex-1 relative overflow-hidden min-h-0">
      <MapView />
      <TriggerDetectionDialog />
    </div>
  );
}
