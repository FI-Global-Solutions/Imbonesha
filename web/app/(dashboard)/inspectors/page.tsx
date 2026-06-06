"use client";

import { useState } from "react";
import { toast } from "sonner";
import { UserCheck, UserX, MapPin, Phone, Mail, Search } from "lucide-react";
import { TopBar } from "@/components/top-bar";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { useInspectors, useToggleInspectorActive } from "@/lib/api/hooks";
import type { Inspector } from "@/lib/api/types";
import { cn } from "@/lib/utils";

function InspectorRow({ inspector }: { inspector: Inspector }) {
  const toggle = useToggleInspectorActive();
  const initials = inspector.full_name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .slice(0, 2)
    .toUpperCase() || inspector.email[0].toUpperCase();

  function handleToggle() {
    toggle.mutate(inspector.id, {
      onSuccess: (updated) => {
        toast.success(
          updated.is_active
            ? `${updated.full_name} activated`
            : `${updated.full_name} deactivated`
        );
      },
      onError: () => toast.error("Failed to update inspector status"),
    });
  }

  return (
    <div className={cn(
      "flex items-center gap-4 py-4 px-5 border-b border-border/40 last:border-0 transition-colors",
      !inspector.is_active && "opacity-60"
    )}>
      {/* Avatar */}
      <div className={cn(
        "h-9 w-9 rounded-full flex items-center justify-center shrink-0 text-xs font-bold",
        inspector.is_active
          ? "bg-primary/10 text-primary"
          : "bg-muted text-muted-foreground"
      )}>
        {initials}
      </div>

      {/* Name + contact */}
      <div className="flex-1 min-w-0 space-y-0.5">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-foreground truncate">{inspector.full_name}</p>
          <Badge
            variant="outline"
            className={cn(
              "text-[10px] px-1.5 py-0 shrink-0",
              inspector.is_active
                ? "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-400"
                : "border-slate-200 bg-slate-50 text-slate-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400"
            )}
          >
            {inspector.is_active ? "Active" : "Inactive"}
          </Badge>
        </div>
        <div className="flex items-center flex-wrap gap-x-3 gap-y-0.5">
          <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
            <Mail className="h-3 w-3 shrink-0" />
            {inspector.email}
          </span>
          {inspector.district && (
            <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
              <MapPin className="h-3 w-3 shrink-0" />
              {inspector.district}
            </span>
          )}
          {inspector.phone_number && (
            <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
              <Phone className="h-3 w-3 shrink-0" />
              {inspector.phone_number}
            </span>
          )}
        </div>
      </div>

      {/* Toggle button */}
      <Button
        variant="outline"
        size="sm"
        className={cn(
          "gap-1.5 h-8 shrink-0",
          inspector.is_active
            ? "text-destructive hover:bg-destructive/10 hover:text-destructive border-destructive/30"
            : "text-emerald-700 hover:bg-emerald-50 hover:text-emerald-700 border-emerald-300 dark:text-emerald-400 dark:border-emerald-800 dark:hover:bg-emerald-950"
        )}
        onClick={handleToggle}
        disabled={toggle.isPending}
      >
        {inspector.is_active
          ? <><UserX className="h-3.5 w-3.5" />Deactivate</>
          : <><UserCheck className="h-3.5 w-3.5" />Activate</>
        }
      </Button>
    </div>
  );
}

export default function InspectorsPage() {
  const { data: inspectors, isLoading } = useInspectors();
  const [search, setSearch] = useState("");

  const filtered = (inspectors ?? []).filter((i) => {
    const q = search.toLowerCase();
    return (
      !q ||
      i.full_name.toLowerCase().includes(q) ||
      i.email.toLowerCase().includes(q) ||
      i.district.toLowerCase().includes(q)
    );
  });

  const activeCount = (inspectors ?? []).filter((i) => i.is_active).length;
  const totalCount = (inspectors ?? []).length;

  return (
    <div className="flex flex-col h-full min-h-0">
      <TopBar breadcrumb="Inspectors" />

      <div className="flex-1 min-h-0 overflow-auto">
        <div className="px-6 py-5 max-w-3xl space-y-4">
          {/* Header */}
          <div className="flex items-end justify-between gap-4">
            <div>
              <h1 className="text-xl font-semibold text-foreground">Inspectors</h1>
              {!isLoading && (
                <p className="text-sm text-muted-foreground mt-0.5">
                  {activeCount} active · {totalCount - activeCount} inactive
                </p>
              )}
            </div>
            <div className="relative w-64">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground pointer-events-none" />
              <Input
                placeholder="Search by name, email, district…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-8 h-8 text-sm"
              />
            </div>
          </div>

          {/* List */}
          <div className="rounded-lg border border-border overflow-hidden">
            {isLoading ? (
              <div>
                {[...Array(5)].map((_, i) => (
                  <div key={i} className="flex items-center gap-4 py-4 px-5 border-b border-border/40 last:border-0">
                    <Skeleton className="h-9 w-9 rounded-full shrink-0" />
                    <div className="flex-1 space-y-1.5">
                      <Skeleton className="h-4 w-48" />
                      <Skeleton className="h-3 w-64" />
                    </div>
                    <Skeleton className="h-8 w-24" />
                  </div>
                ))}
              </div>
            ) : filtered.length === 0 ? (
              <div className="py-16 text-center">
                <UserCheck className="h-8 w-8 text-muted-foreground/30 mx-auto mb-3" />
                <p className="text-sm font-medium text-foreground">
                  {search ? "No inspectors match your search" : "No inspectors yet"}
                </p>
                <p className="text-xs text-muted-foreground mt-1">
                  {search ? "Try a different name or district" : "Inspectors are created via the Django admin"}
                </p>
              </div>
            ) : (
              filtered.map((inspector) => (
                <InspectorRow key={inspector.id} inspector={inspector} />
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
