"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Map, TableProperties, BarChart3, FileText, PanelLeftClose, PanelLeftOpen, ClipboardList } from "lucide-react";
import { cn } from "@/lib/utils";
import { useFlags, useMe } from "@/lib/api/hooks";

const ADMIN_NAV = [
  { href: "/",            label: "Map",            icon: Map },
  { href: "/flags",       label: "Flags",          icon: TableProperties, showBadge: true },
  { href: "/analytics",   label: "Analytics",      icon: BarChart3 },
  { href: "/reports",     label: "Reports",        icon: FileText },
];

const INSPECTOR_NAV = [
  { href: "/",            label: "Map",            icon: Map },
  { href: "/assignments", label: "My Assignments", icon: ClipboardList, showBadge: true },
  { href: "/analytics",   label: "Analytics",      icon: BarChart3 },
];

function LogoMark({ collapsed }: { collapsed: boolean }) {
  return (
    <div className={cn(
      "flex flex-col items-center justify-center gap-1.5 border-b border-border/60 shrink-0 py-4",
      collapsed ? "h-14" : "h-24"
    )}>
      <div className={cn(
        "rounded-xl bg-primary/10 flex items-center justify-center shrink-0 overflow-hidden transition-all duration-200",
        collapsed ? "h-8 w-8" : "h-12 w-12"
      )}>
        <Image
          src="/logo.png"
          alt="Imbonesha"
          width={collapsed ? 26 : 40}
          height={collapsed ? 26 : 40}
          className="object-contain"
          priority
        />
      </div>
      {!collapsed && (
        <div className="flex flex-col items-center min-w-0">
          <span className="font-bold text-[13px] tracking-tight text-foreground leading-none">
            Imbonesha
          </span>
          <span className="text-[9px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/50 leading-none mt-1">
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
  const { data: me } = useMe();
  const isInspector = me?.role === "inspector";
  const NAV = isInspector ? INSPECTOR_NAV : ADMIN_NAV;

  // Pending badge: pending flags for admin, assigned flags for inspector
  const { data: pendingData } = useFlags({
    limit: 1,
    status: isInspector ? "assigned" : "pending",
  });
  const pendingCount = pendingData?.count ?? 0;

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
    <aside className={cn(
      "h-full flex flex-col border-r border-border bg-background/95 transition-[width] duration-200 shrink-0",
      collapsed ? "w-[60px]" : "w-[224px]"
    )}>
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
                "group flex items-center gap-3 rounded-lg px-2.5 py-2.5 text-sm font-medium transition-all duration-150",
                active
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-accent hover:text-foreground"
              )}
            >
              <Icon className={cn(
                "h-4 w-4 shrink-0 transition-colors",
                active ? "text-primary" : "text-muted-foreground group-hover:text-foreground"
              )} />
              {!collapsed && (
                <span className="flex-1 truncate">{label}</span>
              )}
              {!collapsed && showBadge && pendingCount > 0 && (
                <span className={cn(
                  "ml-auto text-[10px] font-bold tabular-nums rounded-full px-1.5 py-0.5 leading-none min-w-[18px] text-center",
                  active
                    ? "bg-primary/20 text-primary"
                    : "bg-muted text-muted-foreground"
                )}>
                  {pendingCount > 999 ? "999+" : pendingCount}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <div className="px-2 py-3 border-t border-border/60">
        <button
          type="button"
          onClick={toggle}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn(
            "flex items-center gap-3 w-full rounded-lg px-2.5 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-foreground transition-colors",
            collapsed && "justify-center"
          )}
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
