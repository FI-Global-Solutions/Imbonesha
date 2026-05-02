"use client";

import { useState } from "react";
import { format } from "date-fns";
import { toast } from "sonner";
import { FileText } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateReport } from "@/lib/api/hooks";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  preselectedFlagIds?: number[];
  onClose: () => void;
}

export function GenerateReportDialog({ open, onOpenChange, preselectedFlagIds = [], onClose }: Props) {
  const defaultTitle = `Enforcement Report — ${format(new Date(), "d MMM yyyy")}`;
  const [title, setTitle] = useState(defaultTitle);
  const { mutate, isPending } = useCreateReport();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!preselectedFlagIds.length) {
      toast.error("No flags selected for this report.");
      return;
    }
    mutate(
      { flag_ids: preselectedFlagIds, title: title || defaultTitle },
      {
        onSuccess: () => {
          toast.success("Report generated successfully");
          setTitle(defaultTitle);
          onClose();
        },
        onError: () => toast.error("Failed to generate report"),
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[440px]">
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

          <div className="rounded-md bg-muted/50 border border-border px-4 py-3">
            <p className="text-sm text-muted-foreground">
              <span className="font-medium text-foreground">{preselectedFlagIds.length}</span>{" "}
              flag{preselectedFlagIds.length !== 1 ? "s" : ""} selected
            </p>
          </div>

          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose} disabled={isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={isPending || !preselectedFlagIds.length}>
              {isPending ? "Generating…" : "Generate PDF"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
