"use client";

import { useState } from "react";
import { UserCheck, Loader2 } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useInspectorWorkload, useBulkAssignFlags, useAssignFlag } from "@/lib/api/hooks";

interface Props {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  flagIds: number[];
  onSuccess?: () => void;
}

export function AssignInspectorDialog({ open, onOpenChange, flagIds, onSuccess }: Props) {
  const [inspectorId, setInspectorId] = useState<string>("");
  const { data: workload = [], isLoading } = useInspectorWorkload();
  const bulkAssign = useBulkAssignFlags();
  const singleAssign = useAssignFlag();

  const isSingle = flagIds.length === 1;

  async function handleSubmit() {
    if (!inspectorId) return;
    const id = parseInt(inspectorId, 10);
    const inspector = workload.find((w) => w.inspector_id === id);
    const name = inspector?.name ?? "inspector";

    try {
      if (isSingle) {
        await singleAssign.mutateAsync({ flagId: flagIds[0], inspector_id: id });
        toast.success(`Flag assigned to ${name}`);
      } else {
        const result = await bulkAssign.mutateAsync({ flag_ids: flagIds, inspector_id: id });
        toast.success(`Assigned ${result.assigned} flag${result.assigned !== 1 ? "s" : ""} to ${name}`, {
          description: result.skipped > 0 ? `${result.skipped} skipped (already closed or in terminal state)` : undefined,
        });
      }
      onSuccess?.();
      onOpenChange(false);
      setInspectorId("");
    } catch {
      toast.error("Failed to assign flags");
    }
  }

  const isPending = bulkAssign.isPending || singleAssign.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-1">
            <div className="h-9 w-9 rounded-xl bg-primary/10 flex items-center justify-center">
              <UserCheck className="h-4 w-4 text-primary" />
            </div>
            <div>
              <DialogTitle className="text-base">Assign inspector</DialogTitle>
              <DialogDescription className="text-xs mt-0.5">
                {isSingle ? "Assign 1 flag" : `Assign ${flagIds.length} flags`} to a field inspector
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4 pt-1">
          {isLoading ? (
            <Skeleton className="h-10 w-full" />
          ) : (
            <Select value={inspectorId} onValueChange={(v) => setInspectorId(v ?? "")}>
              <SelectTrigger className="h-10">
                <SelectValue placeholder="Select inspector…" />
              </SelectTrigger>
              <SelectContent>
                {workload.length === 0 ? (
                  <div className="py-4 text-center text-sm text-muted-foreground">No inspectors found</div>
                ) : (
                  workload.map((w) => (
                    <SelectItem key={w.inspector_id} value={String(w.inspector_id)}>
                      <div className="flex flex-col">
                        <span className="font-medium">{w.name}</span>
                        <span className="text-xs text-muted-foreground">
                          {w.district} · {w.assigned_count} assigned · {w.completed_count} completed
                        </span>
                      </div>
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
          )}

          <div className="flex gap-2 justify-end">
            <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              size="sm"
              disabled={!inspectorId || isPending}
              onClick={handleSubmit}
              className="gap-1.5"
            >
              {isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <UserCheck className="h-3.5 w-3.5" />}
              Assign
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
