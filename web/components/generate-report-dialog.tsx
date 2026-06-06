"use client";

import { useState, useMemo } from "react";
import { format } from "date-fns";
import { toast } from "sonner";
import { FileText, Search } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { useCreateReport, useFlags } from "@/lib/api/hooks";
import { SEVERITY_BADGE_CLASS, SEVERITY_LABEL, STATUS_LABEL } from "@/lib/severity";
import type { Severity, FlagStatus } from "@/lib/api/types";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preselectedFlagIds?: number[];
  onClose: () => void;
}

const STATUS_OPTIONS: FlagStatus[] = ["confirmed", "monitoring", "pending", "assigned", "dismissed"];

export function GenerateReportDialog({ open, onOpenChange, preselectedFlagIds = [], onClose }: Props) {
  const defaultTitle = `Enforcement Report — ${format(new Date(), "d MMM yyyy")}`;
  const [title, setTitle] = useState(defaultTitle);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [statusFilter, setStatusFilter] = useState<FlagStatus | "">("");
  const [search, setSearch] = useState("");
  const { mutate, isPending } = useCreateReport();

  // Only fetch flags for selection when dialog is opened from Reports page (no preselection)
  const needsFlagPicker = preselectedFlagIds.length === 0;
  const { data: flagsData, isLoading: flagsLoading } = useFlags(
    needsFlagPicker && open
      ? { status: statusFilter || undefined, limit: 200 }
      : { limit: 0 }
  );

  const filteredFlags = useMemo(() => {
    const flags = flagsData?.results ?? [];
    if (!search.trim()) return flags;
    const q = search.toLowerCase();
    return flags.filter(
      (f) =>
        f.parcel_upi?.toLowerCase().includes(q) ||
        f.owner_name?.toLowerCase().includes(q) ||
        f.district?.toLowerCase().includes(q)
    );
  }, [flagsData, search]);

  const effectiveIds = preselectedFlagIds.length > 0
    ? preselectedFlagIds
    : Array.from(selectedIds);

  function toggleFlag(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  function toggleAll() {
    if (selectedIds.size === filteredFlags.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredFlags.map((f) => f.id)));
    }
  }

  function handleClose() {
    setSelectedIds(new Set());
    setSearch("");
    setStatusFilter("");
    setTitle(defaultTitle);
    onClose();
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!effectiveIds.length) {
      toast.error("Select at least one flag to include in the report.");
      return;
    }
    mutate(
      { flag_ids: effectiveIds, title: title || defaultTitle },
      {
        onSuccess: () => {
          toast.success("Report generated successfully");
          handleClose();
        },
        onError: () => toast.error("Failed to generate report"),
      }
    );
  }

  const allSelected = filteredFlags.length > 0 && selectedIds.size === filteredFlags.length;

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) handleClose(); else onOpenChange(true); }}>
      <DialogContent className={needsFlagPicker ? "sm:max-w-[560px]" : "sm:max-w-[440px]"}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Generate report
          </DialogTitle>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 pt-1">
          <div className="space-y-1.5">
            <Label htmlFor="report-title">Title</Label>
            <Input
              id="report-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder={defaultTitle}
            />
          </div>

          {preselectedFlagIds.length > 0 ? (
            <div className="rounded-md bg-muted/50 border border-border px-4 py-3">
              <p className="text-sm text-muted-foreground">
                <span className="font-medium text-foreground">{preselectedFlagIds.length}</span>{" "}
                flag{preselectedFlagIds.length !== 1 ? "s" : ""} selected
              </p>
            </div>
          ) : (
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                {/* Status filter chips */}
                <div className="flex flex-wrap gap-1.5 flex-1">
                  <button
                    type="button"
                    onClick={() => setStatusFilter("")}
                    className={`text-[11px] px-2 py-0.5 rounded-full border transition-colors ${
                      statusFilter === ""
                        ? "bg-primary text-primary-foreground border-primary"
                        : "border-border text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    All
                  </button>
                  {STATUS_OPTIONS.map((s) => (
                    <button
                      key={s}
                      type="button"
                      onClick={() => setStatusFilter(s === statusFilter ? "" : s)}
                      className={`text-[11px] px-2 py-0.5 rounded-full border transition-colors ${
                        statusFilter === s
                          ? "bg-primary text-primary-foreground border-primary"
                          : "border-border text-muted-foreground hover:text-foreground"
                      }`}
                    >
                      {STATUS_LABEL[s]}
                    </button>
                  ))}
                </div>
              </div>

              {/* Search */}
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
                <Input
                  placeholder="Search by UPI, owner, district…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="pl-8 h-8 text-sm"
                />
              </div>

              {/* Flag list */}
              <div className="rounded-md border border-border overflow-hidden">
                {/* Select all header */}
                <div className="flex items-center gap-3 px-3 py-2 bg-muted/40 border-b border-border">
                  <Checkbox
                    id="select-all"
                    checked={allSelected}
                    onCheckedChange={toggleAll}
                  />
                  <label htmlFor="select-all" className="text-xs font-medium text-muted-foreground cursor-pointer select-none">
                    {selectedIds.size > 0
                      ? `${selectedIds.size} flag${selectedIds.size !== 1 ? "s" : ""} selected`
                      : `Select all (${filteredFlags.length})`}
                  </label>
                </div>

                <ScrollArea className="h-52">
                  {flagsLoading ? (
                    <div className="p-3 space-y-2">
                      {[...Array(4)].map((_, i) => (
                        <div key={i} className="flex items-center gap-3">
                          <Skeleton className="h-4 w-4 rounded" />
                          <Skeleton className="h-4 flex-1" />
                          <Skeleton className="h-4 w-16" />
                        </div>
                      ))}
                    </div>
                  ) : filteredFlags.length === 0 ? (
                    <div className="py-8 text-center">
                      <p className="text-xs text-muted-foreground">No flags match your filters</p>
                    </div>
                  ) : (
                    filteredFlags.map((flag) => (
                      <label
                        key={flag.id}
                        className="flex items-center gap-3 px-3 py-2 hover:bg-accent/50 cursor-pointer border-b border-border/40 last:border-0"
                      >
                        <Checkbox
                          checked={selectedIds.has(flag.id)}
                          onCheckedChange={() => toggleFlag(flag.id)}
                        />
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-medium truncate">
                            {flag.parcel_upi ?? `Flag #${flag.id}`}
                          </p>
                          {(flag.owner_name || flag.district) && (
                            <p className="text-[10px] text-muted-foreground truncate">
                              {[flag.owner_name, flag.district].filter(Boolean).join(" · ")}
                            </p>
                          )}
                        </div>
                        <Badge
                          variant="outline"
                          className={`text-[9px] px-1.5 py-0 shrink-0 ${SEVERITY_BADGE_CLASS[flag.severity as Severity]}`}
                        >
                          {SEVERITY_LABEL[flag.severity as Severity]}
                        </Badge>
                      </label>
                    ))
                  )}
                </ScrollArea>
              </div>
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={handleClose} disabled={isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending || effectiveIds.length === 0}>
              {isPending ? "Generating…" : `Generate PDF${effectiveIds.length > 0 ? ` (${effectiveIds.length})` : ""}`}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
