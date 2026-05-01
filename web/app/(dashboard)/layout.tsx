"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useMe } from "@/lib/api/hooks";
import { getCookie } from "@/lib/api/client";
import { ThemeToggle } from "@/components/theme-toggle";
import { UserMenu } from "@/components/user-menu";
import { Skeleton } from "@/components/ui/skeleton";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const token = typeof window !== "undefined" ? getCookie("access_token") : null;
  const { data: user, isLoading, isError } = useMe();

  useEffect(() => {
    if (!isLoading && (isError || !token)) {
      router.push("/login");
    }
  }, [isLoading, isError, token, router]);

  if (isLoading || !user) {
    return (
      <div className="h-screen flex flex-col">
        <header className="h-14 border-b flex items-center px-6 gap-4">
          <Skeleton className="h-5 w-28" />
          <div className="ml-auto flex gap-2">
            <Skeleton className="h-8 w-8 rounded-full" />
            <Skeleton className="h-8 w-8 rounded-full" />
          </div>
        </header>
        <div className="flex-1 bg-muted/20" />
      </div>
    );
  }

  if (isError) return null;

  return (
    <div className="h-screen flex flex-col">
      <header className="h-14 border-b flex items-center px-6 shrink-0 bg-background z-10">
        <span className="font-bold text-lg tracking-tight text-foreground">Imbonesha</span>
        <div className="ml-auto flex items-center gap-1">
          <ThemeToggle />
          <UserMenu user={user} />
        </div>
      </header>
      <main className="flex-1 relative overflow-hidden">
        {children}
      </main>
    </div>
  );
}
