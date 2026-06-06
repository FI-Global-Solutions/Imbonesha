"use client";

import { useState, useMemo } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getFilteredRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
  type RowSelectionState,
} from "@tanstack/react-table";
import { formatDistanceToNow, format } from "date-fns";
import {
  Download, Search, X, ChevronUp, ChevronDown, ChevronsUpDown,
  MoreHorizontal, ExternalLink, FileText, Eye, UserCheck, Trash2,
} from "lucide-react";
import { toast } from "sonner";

import { TopBar } from "@/components/top-bar";
import { AssignInspectorDialog } from "@/components/assign-inspector-dialog";
import { GenerateReportDialog } from "@/components/generate-report-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent,
  DropdownMenuItem, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipTrigger, TooltipProvider } from "@/components/ui/tooltip";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";

import { useFlags, useMe, useDeleteFlag, useDeleteFlags } from "@/lib/api/hooks";
import { useUIStore } from "@/lib/store";
import { getCookie } from "@/lib/api/client";
import { SEVERITY_BADGE_CLASS, SEVERITY_LABEL, STATUS_BADGE_CLASS, STATUS_LABEL } from "@/lib/severity";
import type { FlagListItem, Severity, FlagStatus, PermitStatus } from "@/lib/api/types";

const ADMIN_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8007";
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8007";

const PERMIT_LABEL: Record<string, { label: string; cls: string }> = {
  active:    { label: "Active",     cls: "bg-green-50 text-green-700 border-green-200 dark:bg-green-950 dark:text-green-400 dark:border-green-900" },
  expired:   { label: "Expired",    cls: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-400 dark:border-amber-900" },
  no_permit: { label: "No permit",  cls: "bg-red-50 text-red-700 border-red-200 dark:bg-red-950 dark:text-red-400 dark:border-red-900" },
  other:     { label: "Other",      cls: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-400 dark:border-amber-900" },
  no_parcel: { label: "No parcel",  cls: "bg-slate-100 text-slate-500 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700" },
};

const col = createColumnHelper<FlagListItem>();

function SortIcon({ sorted }: { sorted: false | "asc" | "desc" }) {
  if (sorted === "asc") return <ChevronUp className="h-3 w-3" />;
  if (sorted === "desc") return <ChevronDown className="h-3 w-3" />;
  return <ChevronsUpDown className="h-3 w-3 opacity-40" />;
}

export default function FlagsPage() {
  const { openDrawer } = useUIStore();
  const { data: me } = useMe();
  const [search, setSearch] = useState("");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sorting, setSorting] = useState<SortingState>([{ id: "created_at", desc: true }]);
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({});
  const [reportDialogOpen, setReportDialogOpen] = useState(false);
  const [assignDialogOpen, setAssignDialogOpen] = useState(false);
  const [preselectedFlagIds, setPreselectedFlagIds] = useState<number[]>([]);
  const [deleteConfirm, setDeleteConfirm] = useState<{ ids: number[] } | null>(null);
  const canAssign = me?.role === "admin" || me?.role === "district_admin";
  const canDelete = me?.role === "admin" || me?.role === "district_admin" || me?.role === "rha_officer";
  const deleteFlag = useDeleteFlag();
  const deleteFlags = useDeleteFlags();

  const { data, isLoading } = useFlags({ limit: 500 });
  const allFlags = data?.results ?? [];

  // Client-side filter (search by UPI / owner / district)
  const filtered = useMemo(() => {
    let rows = allFlags;
    if (severityFilter !== "all") rows = rows.filter((f) => f.severity === severityFilter);
    if (statusFilter !== "all") rows = rows.filter((f) => f.status === statusFilter);
    if (search.trim()) {
      const q = search.toLowerCase();
      rows = rows.filter(
        (f) =>
          f.parcel_upi?.toLowerCase().includes(q) ||
          f.owner_name?.toLowerCase().includes(q) ||
          f.district?.toLowerCase().includes(q)
      );
    }
    return rows;
  }, [allFlags, severityFilter, statusFilter, search]);

  const columns = useMemo(() => [
    col.display({
      id: "select",
      header: ({ table }) => (
        <Checkbox
          checked={table.getIsAllPageRowsSelected()}
          indeterminate={table.getIsSomePageRowsSelected()}
          onCheckedChange={(v) => table.toggleAllPageRowsSelected(!!v)}
          aria-label="Select all"
        />
      ),
      cell: ({ row }) => (
        <Checkbox
          checked={row.getIsSelected()}
          onCheckedChange={(v) => row.toggleSelected(!!v)}
          aria-label="Select row"
          onClick={(e) => e.stopPropagation()}
        />
      ),
      size: 40,
      enableSorting: false,
    }),
    col.accessor("severity", {
      header: ({ column }) => (
        <button
          type="button"
          className="flex items-center gap-1"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
        >
          Severity <SortIcon sorted={column.getIsSorted()} />
        </button>
      ),
      cell: ({ getValue }) => {
        const sev = getValue() as Severity;
        return (
          <Badge variant="outline" className={SEVERITY_BADGE_CLASS[sev]}>
            {SEVERITY_LABEL[sev]}
          </Badge>
        );
      },
    }),
    col.accessor("id", {
      header: "ID",
      cell: ({ getValue }) => (
        <span className="font-mono text-xs text-muted-foreground">#{getValue()}</span>
      ),
      enableSorting: false,
    }),
    col.accessor("parcel_upi", {
      header: "Parcel UPI",
      cell: ({ getValue }) => {
        const v = getValue();
        return v
          ? <span className="font-mono text-xs">{v}</span>
          : <span className="text-muted-foreground text-xs italic">Unmatched</span>;
      },
      enableSorting: false,
    }),
    col.accessor("owner_name", {
      header: "Owner",
      cell: ({ getValue }) => getValue() ?? <span className="text-muted-foreground text-xs">—</span>,
      enableSorting: false,
    }),
    col.accessor("district", {
      header: ({ column }) => (
        <button
          type="button"
          className="flex items-center gap-1"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
        >
          District <SortIcon sorted={column.getIsSorted()} />
        </button>
      ),
      cell: ({ getValue }) => getValue() || <span className="text-muted-foreground text-xs">—</span>,
    }),
    col.accessor("assigned_to_name", {
      header: "Inspector",
      cell: ({ getValue }) => {
        const v = getValue();
        return v
          ? <span className="text-xs font-medium">{v}</span>
          : <span className="text-muted-foreground text-xs">—</span>;
      },
      enableSorting: false,
    }),
    col.accessor("permit_status", {
      header: "Permit",
      cell: ({ getValue }) => {
        const v = (getValue() ?? "no_permit") as string;
        const p = PERMIT_LABEL[v] ?? { label: v, cls: "" };
        return (
          <Badge variant="outline" className={p.cls}>
            {p.label}
          </Badge>
        );
      },
      enableSorting: false,
    }),
    col.accessor("status", {
      header: ({ column }) => (
        <button
          type="button"
          className="flex items-center gap-1"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
        >
          Status <SortIcon sorted={column.getIsSorted()} />
        </button>
      ),
      cell: ({ getValue }) => {
        const v = getValue() as FlagStatus;
        return (
          <Badge variant="outline" className={STATUS_BADGE_CLASS[v]}>
            {STATUS_LABEL[v] ?? v}
          </Badge>
        );
      },
    }),
    col.accessor("created_at", {
      header: ({ column }) => (
        <button
          type="button"
          className="flex items-center gap-1"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
        >
          Flagged <SortIcon sorted={column.getIsSorted()} />
        </button>
      ),
      cell: ({ getValue }) => {
        const d = new Date(getValue());
        return (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger render={<span className="text-sm text-muted-foreground cursor-default" />}>
                {formatDistanceToNow(d, { addSuffix: true })}
              </TooltipTrigger>
              <TooltipContent>
                <p>{format(d, "d MMM yyyy, HH:mm")}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        );
      },
    }),
    col.display({
      id: "actions",
      header: "",
      cell: ({ row }) => {
        const flag = row.original;
        return (
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-7 w-7 opacity-0 group-hover/row:opacity-100 transition-opacity"
                  onClick={(e) => e.stopPropagation()}
                />
              }
            >
              <MoreHorizontal className="h-4 w-4" />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" side="bottom">
              <DropdownMenuItem onClick={() => openDrawer(flag.id)}>
                <Eye className="h-4 w-4" />
                View detail
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={(e) => {
                  e.stopPropagation();
                  setPreselectedFlagIds([flag.id]);
                  setReportDialogOpen(true);
                }}
              >
                <FileText className="h-4 w-4" />
                Generate report
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                render={
                  <a
                    href={`${ADMIN_URL}/admin/flags/flag/${flag.id}/change/`}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={`Open flag #${flag.id} in admin`}
                    onClick={(e) => e.stopPropagation()}
                  />
                }
              >
                <ExternalLink className="h-4 w-4" />
                Open in admin
              </DropdownMenuItem>
              {canDelete && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    className="text-destructive focus:text-destructive"
                    onClick={(e) => {
                      e.stopPropagation();
                      setDeleteConfirm({ ids: [flag.id] });
                    }}
                  >
                    <Trash2 className="h-4 w-4" />
                    Delete flag
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        );
      },
      size: 48,
      enableSorting: false,
    }),
  ], [openDrawer]);

  const table = useReactTable({
    data: filtered,
    columns,
    state: { sorting, rowSelection },
    onSortingChange: setSorting,
    onRowSelectionChange: setRowSelection,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    enableRowSelection: true,
  });

  const selectedRows = table.getSelectedRowModel().rows;
  const selectedIds = selectedRows.map((r) => r.original.id);

  function handleCsvExport() {
    const token = getCookie("access_token");
    const params = new URLSearchParams();
    if (severityFilter !== "all") params.set("severity", severityFilter);
    if (statusFilter !== "all") params.set("status", statusFilter);
    const url = `${API_URL}/api/v1/flags/export.csv/?${params}`;
    const a = document.createElement("a");
    a.href = url;
    if (token) a.href += `${params.toString() ? "&" : ""}token=${encodeURIComponent(token)}`;
    a.download = "";
    a.click();
    toast.success("CSV download started");
  }

  const csvButton = (
    <Button variant="outline" size="sm" onClick={handleCsvExport} className="gap-1.5 h-8">
      <Download className="h-3.5 w-3.5" />
      Export CSV
    </Button>
  );

  return (
    <div className="flex flex-col h-full min-h-0">
      <TopBar breadcrumb="Flags" actions={csvButton} />

      <div className="flex-1 min-h-0 overflow-auto">
        <div className="px-6 py-5 space-y-4">
          {/* Page header */}
          <div>
            <h1 className="text-xl font-semibold text-foreground">Flags</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              {isLoading ? "Loading…" : `${filtered.length} flag${filtered.length !== 1 ? "s" : ""}`}
              {data && filtered.length !== data.count ? ` (filtered from ${data.count})` : ""}
            </p>
          </div>

          {/* Filter bar */}
          <div className="flex flex-wrap gap-2 items-center">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                placeholder="Search UPI, owner, district…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-8 h-8 w-64 text-sm"
              />
              {search && (
                <button
                  type="button"
                  title="Clear search"
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  onClick={() => setSearch("")}
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>

            <Select value={severityFilter} onValueChange={(v) => setSeverityFilter(v ?? "all")}>
              <SelectTrigger className="h-8 w-36 text-sm">
                <SelectValue placeholder="All severities" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All severities</SelectItem>
                <SelectItem value="critical">Critical</SelectItem>
                <SelectItem value="high">High</SelectItem>
                <SelectItem value="medium">Medium</SelectItem>
                <SelectItem value="low">Low</SelectItem>
              </SelectContent>
            </Select>

            <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v ?? "all")}>
              <SelectTrigger className="h-8 w-36 text-sm">
                <SelectValue placeholder="All statuses" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="pending">Pending</SelectItem>
                <SelectItem value="assigned">Assigned</SelectItem>
                <SelectItem value="in_review">In review</SelectItem>
                <SelectItem value="confirmed">Confirmed</SelectItem>
                <SelectItem value="dismissed">Dismissed</SelectItem>
                <SelectItem value="monitoring">Monitoring</SelectItem>
                <SelectItem value="inaccessible">Inaccessible</SelectItem>
                <SelectItem value="data_error">Data error</SelectItem>
                <SelectItem value="closed">Closed</SelectItem>
              </SelectContent>
            </Select>

            {(severityFilter !== "all" || statusFilter !== "all" || search) && (
              <Button
                variant="ghost"
                size="sm"
                className="h-8 text-muted-foreground gap-1"
                onClick={() => { setSeverityFilter("all"); setStatusFilter("all"); setSearch(""); }}
              >
                <X className="h-3.5 w-3.5" /> Clear filters
              </Button>
            )}
          </div>

          {/* Table */}
          <div className="rounded-lg border border-border overflow-hidden">
            <Table>
              <TableHeader>
                {table.getHeaderGroups().map((hg) => (
                  <TableRow key={hg.id} className="hover:bg-transparent">
                    {hg.headers.map((header) => (
                      <TableHead
                        key={header.id}
                        className="h-9 text-xs font-medium text-muted-foreground"
                        style={{ width: header.getSize() !== 150 ? header.getSize() : undefined }}
                      >
                        {flexRender(header.column.columnDef.header, header.getContext())}
                      </TableHead>
                    ))}
                  </TableRow>
                ))}
              </TableHeader>
              <TableBody>
                {isLoading
                  ? [...Array(8)].map((_, i) => (
                    <TableRow key={i}>
                      {columns.map((_, ci) => (
                        <TableCell key={ci}><Skeleton className="h-4 w-full" /></TableCell>
                      ))}
                    </TableRow>
                  ))
                  : table.getRowModel().rows.length === 0
                    ? (
                      <TableRow>
                        <TableCell colSpan={columns.length} className="h-32 text-center">
                          <div className="text-sm text-muted-foreground">
                            No flags match your filters.
                          </div>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="mt-2 text-muted-foreground"
                            onClick={() => { setSeverityFilter("all"); setStatusFilter("all"); setSearch(""); }}
                          >
                            Clear filters
                          </Button>
                        </TableCell>
                      </TableRow>
                    )
                    : table.getRowModel().rows.map((row) => {
                      const sev = row.original.severity;
                      const stripeColor = sev === "critical" ? "before:bg-red-500" : sev === "high" ? "before:bg-orange-500" : sev === "medium" ? "before:bg-yellow-500" : "before:bg-slate-400/40";
                      return (
                        <TableRow
                          key={row.id}
                          className={`group/row cursor-pointer hover:bg-accent/40 relative before:absolute before:left-0 before:top-1/2 before:-translate-y-1/2 before:w-[3px] before:h-[60%] before:rounded-r-full before:opacity-70 ${stripeColor}`}
                          onClick={() => openDrawer(row.original.id)}
                          data-state={row.getIsSelected() ? "selected" : undefined}
                        >
                          {row.getVisibleCells().map((cell) => (
                            <TableCell key={cell.id} className="py-2.5">
                              {flexRender(cell.column.columnDef.cell, cell.getContext())}
                            </TableCell>
                          ))}
                        </TableRow>
                      );
                    })
                }
              </TableBody>
            </Table>
          </div>

          <p className="text-xs text-muted-foreground">
            {table.getRowModel().rows.length} of {filtered.length} rows shown
          </p>
        </div>
      </div>

      {/* Bulk action bar */}
      {selectedIds.length > 0 && (
        <div className="shrink-0 border-t border-border bg-background px-6 py-3 flex items-center gap-3">
          <span className="text-sm font-medium">
            {selectedIds.length} selected
          </span>
          {canAssign && (
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5"
              onClick={() => setAssignDialogOpen(true)}
            >
              <UserCheck className="h-3.5 w-3.5" />
              Assign inspector
            </Button>
          )}
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5"
            onClick={() => {
              setPreselectedFlagIds(selectedIds);
              setReportDialogOpen(true);
            }}
          >
            <FileText className="h-3.5 w-3.5" />
            Generate report
          </Button>
          {canDelete && (
            <Button
              size="sm"
              variant="destructive"
              className="gap-1.5"
              onClick={() => setDeleteConfirm({ ids: selectedIds })}
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete {selectedIds.length} flag{selectedIds.length !== 1 ? "s" : ""}
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            className="text-muted-foreground ml-auto"
            onClick={() => setRowSelection({})}
          >
            <X className="h-3.5 w-3.5 mr-1" /> Deselect
          </Button>
        </div>
      )}

      <GenerateReportDialog
        open={reportDialogOpen}
        onOpenChange={setReportDialogOpen}
        preselectedFlagIds={preselectedFlagIds}
        onClose={() => { setReportDialogOpen(false); setPreselectedFlagIds([]); setRowSelection({}); }}
      />

      <AssignInspectorDialog
        open={assignDialogOpen}
        onOpenChange={setAssignDialogOpen}
        flagIds={selectedIds}
        onSuccess={() => setRowSelection({})}
      />

      <Dialog open={!!deleteConfirm} onOpenChange={(o) => { if (!o) setDeleteConfirm(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              Delete {deleteConfirm?.ids.length === 1 ? "flag" : `${deleteConfirm?.ids.length} flags`}?
            </DialogTitle>
            <DialogDescription>
              This permanently removes the {deleteConfirm?.ids.length === 1 ? "flag" : "selected flags"} and
              associated audit logs. This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirm(null)}>Cancel</Button>
            <Button
              variant="destructive"
              onClick={async () => {
                if (!deleteConfirm) return;
                try {
                  if (deleteConfirm.ids.length === 1) {
                    await deleteFlag.mutateAsync(deleteConfirm.ids[0]);
                    toast.success("Flag deleted");
                  } else {
                    const res = await deleteFlags.mutateAsync(deleteConfirm.ids);
                    toast.success(`${res.deleted} flags deleted`);
                  }
                  setRowSelection({});
                  setDeleteConfirm(null);
                } catch {
                  toast.error("Failed to delete flag(s)");
                }
              }}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
