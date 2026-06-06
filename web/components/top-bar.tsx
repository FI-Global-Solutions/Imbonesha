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
    <header className="h-14 shrink-0 flex items-center px-5 gap-3 border-b border-border/50 bg-background/80 backdrop-blur-md">
      <div className="flex items-center gap-2">
        <span className="text-[12px] font-medium text-muted-foreground/50 tracking-wide">Dashboard</span>
        <span className="text-muted-foreground/25 text-[11px]">/</span>
        <span className="text-[13px] font-semibold text-foreground tracking-tight">{breadcrumb}</span>
      </div>

      <div className="ml-auto flex items-center gap-1.5">
        {actions && (
          <>
            {actions}
            <div className="w-px h-4 bg-border mx-1" />
          </>
        )}
        <ThemeToggle />
        <div className="w-px h-4 bg-border mx-1" />
        {user
          ? <UserMenu user={user} />
          : <Skeleton className="h-8 w-8 rounded-full" />
        }
      </div>
    </header>
  );
}
