"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useMe } from "@/lib/api/hooks";
import { getCookie } from "@/lib/api/client";
import { Skeleton } from "@/components/ui/skeleton";
import { Sidebar } from "@/components/sidebar";
import { FlagDetailSheet } from "@/components/flag-detail-sheet";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const token = typeof window !== "undefined" ? getCookie("access_token") : null;
  const { data: user, isLoading, isError } = useMe();

  useEffect(() => {
    if (!isLoading && (isError || !token)) {
      router.push("/login");
    }
    // Redirect inspectors away from the map to their assignments
    if (!isLoading && user?.role === "inspector" && typeof window !== "undefined" && window.location.pathname === "/") {
      router.replace("/assignments");
    }
  }, [isLoading, isError, token, router, user]);

  if (isLoading || !user) {
    return (
      <div className="h-screen flex">
        <div className="w-[220px] border-r border-border bg-background shrink-0 flex flex-col">
          <div className="h-14 border-b border-border/60 flex items-center px-4 gap-2.5">
            <Skeleton className="h-5 w-5 rounded" />
            <Skeleton className="h-4 w-28" />
          </div>
          <div className="p-2 space-y-1">
            {[...Array(4)].map((_, i) => (
              <Skeleton key={i} className="h-8 w-full rounded-md" />
            ))}
          </div>
        </div>
        <div className="flex-1 bg-muted/20" />
      </div>
    );
  }

  if (isError) return null;

  return (
    <div className="h-screen flex overflow-hidden">
      <Sidebar />
      <main className="flex-1 min-w-0 flex flex-col overflow-hidden">
        {children}
      </main>
      <FlagDetailSheet />
    </div>
  );
}
