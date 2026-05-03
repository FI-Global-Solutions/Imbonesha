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
    <header className="h-14 shrink-0 flex items-center px-6 gap-3 border-b border-border/60 bg-background/90 backdrop-blur-md">
      <div className="flex items-center gap-2 text-sm">
        <span className="text-muted-foreground/60 font-medium">Dashboard</span>
        <span className="text-muted-foreground/30 text-xs">/</span>
        <span className="font-semibold text-foreground">{breadcrumb}</span>
      </div>

      <div className="ml-auto flex items-center gap-1.5">
        {actions && (
          <>
            {actions}
            <div className="w-px h-4 bg-border/60 mx-0.5" />
          </>
        )}
        <ThemeToggle />
        <div className="w-px h-4 bg-border/60 mx-0.5" />
        {user
          ? <UserMenu user={user} />
          : <Skeleton className="h-8 w-8 rounded-full" />
        }
      </div>
    </header>
  );
}
