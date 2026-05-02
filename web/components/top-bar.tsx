"use client";

import { ThemeToggle } from "@/components/theme-toggle";
import { UserMenu } from "@/components/user-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/lib/api/hooks";

interface TopBarProps {
  breadcrumb: string;
  actions?: React.ReactNode;
}

export function TopBar({ breadcrumb, actions }: TopBarProps) {
  const { data: user } = useMe();

  return (
    <header className="h-14 shrink-0 flex items-center px-6 gap-3 border-b border-border/60 bg-background/80 backdrop-blur-md supports-backdrop-filter:bg-background/70">
      <div className="flex items-center gap-2 text-sm">
        <span className="text-muted-foreground">Dashboard</span>
        <span className="text-muted-foreground/40">/</span>
        <span className="font-medium text-foreground">{breadcrumb}</span>
      </div>

      <div className="ml-auto flex items-center gap-1">
        {actions}
        <ThemeToggle />
        <div className="w-px h-4 bg-border/60 mx-1" />
        {user
          ? <UserMenu user={user} />
          : <Skeleton className="h-8 w-8 rounded-full" />
        }
      </div>
    </header>
  );
}
