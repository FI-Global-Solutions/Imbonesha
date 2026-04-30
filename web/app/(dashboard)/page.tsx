import { MapView } from "@/components/map/map-view";
import { FlagDetailSheet } from "@/components/flag-detail-sheet";
import { TriggerDetectionDialog } from "@/components/trigger-detection-dialog";

export default function HomePage() {
  return (
    <>
      <MapView />
      <FlagDetailSheet />
      <TriggerDetectionDialog />
    </>
  );
}
