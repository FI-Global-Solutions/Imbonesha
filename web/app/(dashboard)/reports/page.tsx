"use client";

import { useState } from "react";
import { formatDistanceToNow, format } from "date-fns";
import { FileText, Download, Trash2, Plus } from "lucide-react";
import { toast } from "sonner";

import { TopBar } from "@/components/top-bar";
import { GenerateReportDialog } from "@/components/generate-report-dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from "@/components/ui/tooltip";

import { useReports, useDeleteReport } from "@/lib/api/hooks";
import { getCookie } from "@/lib/api/client";
import type { Report } from "@/lib/api/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8007";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function ReportRow({ report }: { report: Report }) {
  const { mutate: deleteReport, isPending } = useDeleteReport();

  function handleDownload() {
    const token = getCookie("access_token");
    const url = `${API_URL}/api/v1/reports/${report.id}/download/${token ? `?token=${encodeURIComponent(token)}` : ""}`;
    const a = document.createElement("a");
    a.href = url;
    a.download = `imbonesha-report-${report.id}.pdf`;
    a.click();
    toast.success("Download started");
  }

  function handleDelete() {
    if (!confirm("Delete this report? This cannot be undone.")) return;
    deleteReport(report.id, {
      onSuccess: () => toast.success("Report deleted"),
      onError: () => toast.error("Failed to delete report"),
    });
  }

  return (
    <div className="flex items-center gap-4 py-4 group">
      <div className="h-9 w-9 rounded-lg bg-muted flex items-center justify-center shrink-0">
        <FileText className="h-4 w-4 text-muted-foreground" />
      </div>

      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-foreground truncate">{report.title}</p>
        <div className="flex items-center gap-2 mt-0.5">
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger render={<span className="text-xs text-muted-foreground cursor-default" />}>
                {formatDistanceToNow(new Date(report.generated_at), { addSuffix: true })}
              </TooltipTrigger>
              <TooltipContent>
                {format(new Date(report.generated_at), "d MMM yyyy, HH:mm")}
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
          {report.generated_by_name && (
            <>
              <span className="text-muted-foreground/40 text-xs">·</span>
              <span className="text-xs text-muted-foreground">{report.generated_by_name}</span>
            </>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3 shrink-0">
        <span className="text-xs text-muted-foreground tabular-nums">
          {report.flag_count} flag{report.flag_count !== 1 ? "s" : ""}
        </span>
        {report.file_size > 0 && (
          <span className="text-xs text-muted-foreground tabular-nums">
            {formatBytes(report.file_size)}
          </span>
        )}
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5 h-7"
          onClick={handleDownload}
        >
          <Download className="h-3.5 w-3.5" />
          Download
        </Button>
        <Button
          variant="ghost"
          size="icon"
          className="h-7 w-7 text-muted-foreground hover:text-destructive opacity-0 group-hover:opacity-100 transition-opacity"
          onClick={handleDelete}
          disabled={isPending}
        >
          <Trash2 className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}

export default function ReportsPage() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const { data, isLoading } = useReports();
  const reports = data?.results ?? [];

  const generateButton = (
    <Button size="sm" className="gap-1.5 h-8" onClick={() => setDialogOpen(true)}>
      <Plus className="h-3.5 w-3.5" />
      Generate report
    </Button>
  );

  return (
    <div className="flex flex-col h-full min-h-0">
      <TopBar breadcrumb="Reports" actions={generateButton} />

      <div className="flex-1 min-h-0 overflow-auto">
        <div className="px-6 py-5 max-w-3xl space-y-4">
          {/* Page header */}
          <div>
            <h1 className="text-xl font-semibold text-foreground">Reports</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              PDF enforcement reports generated from flag selections
            </p>
          </div>

          {/* Reports list */}
          {isLoading ? (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="flex items-center gap-4 py-4">
                  <Skeleton className="h-9 w-9 rounded-lg" />
                  <div className="flex-1 space-y-1.5">
                    <Skeleton className="h-4 w-64" />
                    <Skeleton className="h-3 w-40" />
                  </div>
                  <Skeleton className="h-7 w-24" />
                </div>
              ))}
            </div>
          ) : reports.length === 0 ? (
            <div className="py-16 text-center">
              <div className="h-12 w-12 rounded-xl bg-muted flex items-center justify-center mx-auto mb-4">
                <FileText className="h-6 w-6 text-muted-foreground" />
              </div>
              <p className="text-sm font-medium text-foreground">No reports yet</p>
              <p className="text-sm text-muted-foreground mt-1">
                Generate your first report from the Flags view or here.
              </p>
              <Button
                className="mt-4 gap-1.5"
                onClick={() => setDialogOpen(true)}
              >
                <Plus className="h-4 w-4" />
                Generate report
              </Button>
            </div>
          ) : (
            <div>
              {reports.map((report, i) => (
                <div key={report.id}>
                  <ReportRow report={report} />
                  {i < reports.length - 1 && <Separator />}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <GenerateReportDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        preselectedFlagIds={[]}
        onClose={() => setDialogOpen(false)}
      />
    </div>
  );
}
