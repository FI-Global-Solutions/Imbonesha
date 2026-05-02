"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Map, TableProperties, BarChart3, FileText, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { cn } from "@/lib/utils";
import { useFlags } from "@/lib/api/hooks";

const NAV = [
  { href: "/", label: "Map", icon: Map },
  { href: "/flags", label: "Flags", icon: TableProperties, showBadge: true },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/reports", label: "Reports", icon: FileText },
];

function LogoMark({ collapsed }: { collapsed: boolean }) {
  return (
    <div className={cn("flex items-center gap-2.5 px-4 h-14 border-b border-border/60 shrink-0", collapsed && "justify-center px-0")}>
      <svg width="22" height="22" viewBox="0 0 28 28" fill="none" aria-hidden className="shrink-0">
        <polygon points="14,2 25,8 25,20 14,26 3,20 3,8" fill="currentColor" className="text-primary" opacity="0.15" />
        <polygon points="14,2 25,8 25,20 14,26 3,20 3,8" fill="none" stroke="currentColor" strokeWidth="1.5" className="text-primary" />
        <line x1="14" y1="9" x2="14" y2="13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" className="text-primary" />
        <line x1="14" y1="15" x2="14" y2="19" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" className="text-primary" />
        <line x1="9" y1="14" x2="13" y2="14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" className="text-primary" />
        <line x1="15" y1="14" x2="19" y2="14" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" className="text-primary" />
        <circle cx="14" cy="14" r="1.5" fill="currentColor" className="text-primary" />
      </svg>
      {!collapsed && (
        <div className="flex flex-col min-w-0">
          <span className="font-semibold text-[14px] tracking-tight text-foreground leading-none truncate">
            Imbonesha
          </span>
          <span className="text-[9px] font-medium uppercase tracking-widest text-muted-foreground/60 leading-none mt-0.5">
            RHA · Change Detection
          </span>
        </div>
      )}
    </div>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const { data } = useFlags({ limit: 1, status: "pending" });
  const pendingCount = data?.count ?? 0;

  useEffect(() => {
    const stored = localStorage.getItem("sidebar-collapsed");
    if (stored !== null) setCollapsed(stored === "true");
  }, []);

  function toggle() {
    const next = !collapsed;
    setCollapsed(next);
    localStorage.setItem("sidebar-collapsed", String(next));
  }

  return (
    <aside
      className={cn(
        "h-full flex flex-col border-r border-border bg-background transition-[width] duration-200 shrink-0",
        collapsed ? "w-[60px]" : "w-[220px]"
      )}
    >
      <LogoMark collapsed={collapsed} />

      <nav className="flex-1 px-2 py-3 space-y-0.5 overflow-y-auto">
        {NAV.map(({ href, label, icon: Icon, showBadge }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              title={collapsed ? label : undefined}
              className={cn(
                "flex items-center gap-3 rounded-md px-2.5 py-2 text-sm transition-colors",
                active
                  ? "bg-accent text-accent-foreground font-medium"
                  : "text-muted-foreground hover:bg-accent/50 hover:text-foreground"
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              {!collapsed && (
                <span className="flex-1 truncate">{label}</span>
              )}
              {!collapsed && showBadge && pendingCount > 0 && (
                <span className="ml-auto text-[11px] font-medium tabular-nums bg-muted text-muted-foreground rounded px-1.5 py-0.5 leading-none">
                  {pendingCount > 999 ? "999+" : pendingCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="px-2 py-3 border-t border-border/60">
        <button
          onClick={toggle}
          className={cn(
            "flex items-center gap-3 w-full rounded-md px-2.5 py-2 text-sm text-muted-foreground hover:bg-accent/50 hover:text-foreground transition-colors",
            collapsed && "justify-center"
          )}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed
            ? <PanelLeftOpen className="h-4 w-4 shrink-0" />
            : <><PanelLeftClose className="h-4 w-4 shrink-0" /><span>Collapse</span></>
          }
        </button>
      </div>
    </aside>
  );
}
