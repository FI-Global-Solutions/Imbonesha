"use client";

import { useState } from "react";
import { UserCheck, Loader2 } from "lucide-react";
import { toast } from "sonner";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  Select, SelectContent, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Select as SelectPrimitive } from "@base-ui/react/select";
import { CheckIcon } from "lucide-react";
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
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <div className="flex items-center gap-3 mb-1">
            <div className="h-9 w-9 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
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
            <Skeleton className="h-12 w-full" />
          ) : (
            <Select
              value={inspectorId}
              onValueChange={(v) => setInspectorId(v ?? "")}
              items={Object.fromEntries(workload.map((w) => [String(w.inspector_id), w.name]))}
            >
              <SelectTrigger className="h-12 w-full text-sm">
                <SelectValue placeholder="Select an inspector…" />
              </SelectTrigger>
              <SelectContent className="w-full">
                {workload.length === 0 ? (
                  <div className="py-6 text-center text-sm text-muted-foreground">No inspectors found</div>
                ) : (
                  workload.map((w) => (
                    <SelectPrimitive.Item
                      key={w.inspector_id}
                      value={String(w.inspector_id)}
                      className="relative flex w-full cursor-default items-center rounded-md py-2.5 px-2 text-sm outline-none select-none focus:bg-accent focus:text-accent-foreground data-disabled:pointer-events-none data-disabled:opacity-50"
                    >
                      {/* ItemText only wraps the name — base-ui uses this text in the trigger */}
                      <SelectPrimitive.ItemText className="sr-only">{w.name}</SelectPrimitive.ItemText>
                      {/* Visual row — fully custom, not read by trigger */}
                      <div className="flex items-center justify-between gap-6 w-full pr-6">
                        <div className="flex flex-col gap-0.5">
                          <span className="font-semibold text-sm text-foreground">{w.name}</span>
                          <span className="text-xs text-muted-foreground">{w.district}</span>
                        </div>
                        <div className="flex items-center gap-3 shrink-0">
                          <div className="flex flex-col items-center">
                            <span className="text-sm font-bold tabular-nums text-amber-500">{w.assigned_count}</span>
                            <span className="text-[10px] text-muted-foreground">active</span>
                          </div>
                          <div className="flex flex-col items-center">
                            <span className="text-sm font-bold tabular-nums text-green-500">{w.completed_count}</span>
                            <span className="text-[10px] text-muted-foreground">done</span>
                          </div>
                        </div>
                      </div>
                      <SelectPrimitive.ItemIndicator className="pointer-events-none absolute right-2 flex size-4 items-center justify-center">
                        <CheckIcon className="size-3.5" />
                      </SelectPrimitive.ItemIndicator>
                    </SelectPrimitive.Item>
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
