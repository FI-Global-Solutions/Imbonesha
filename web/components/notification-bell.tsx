"use client";

import { Bell, Check, CheckCheck, Eye } from "lucide-react";
import { formatDistanceToNow } from "date-fns";
import { cn } from "@/lib/utils";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  useWebNotifications,
  useUnreadNotificationCount,
  useMarkNotificationRead,
  useMarkAllNotificationsRead,
} from "@/lib/api/hooks";
import { useUIStore } from "@/lib/store";
import type { WebNotification } from "@/lib/api/types";

const TYPE_LABEL: Record<string, string> = {
  inspection_complete: "Inspection submitted",
  flag_assigned: "Flag assigned",
};

function NotificationItem({ n, onRead }: { n: WebNotification; onRead: (id: string) => void }) {
  const { openDrawer } = useUIStore();

  function handleClick() {
    if (!n.is_read) onRead(n.id);
    if (n.related_flag_id) openDrawer(n.related_flag_id);
  }

  return (
    <button
      type="button"
      onClick={handleClick}
      className={cn(
        "w-full text-left px-4 py-3 flex gap-3 items-start hover:bg-accent/60 transition-colors border-b border-border/40 last:border-0",
        !n.is_read && "bg-primary/5"
      )}
    >
      <div className={cn(
        "mt-0.5 h-2 w-2 rounded-full shrink-0",
        n.is_read ? "bg-transparent" : "bg-primary"
      )} />
      <div className="flex-1 min-w-0 space-y-0.5">
        <p className={cn("text-xs leading-snug", !n.is_read ? "font-semibold text-foreground" : "font-medium text-muted-foreground")}>
          {TYPE_LABEL[n.notification_type] ?? n.notification_type.replace(/_/g, " ")}
        </p>
        <p className="text-xs text-muted-foreground leading-snug truncate">{n.body}</p>
        <p className="text-[10px] text-muted-foreground/60">
          {formatDistanceToNow(new Date(n.created_at), { addSuffix: true })}
        </p>
      </div>
      {n.related_flag_id && (
        <Eye className="h-3.5 w-3.5 text-muted-foreground/40 shrink-0 mt-0.5" />
      )}
    </button>
  );
}

export function NotificationBell() {
  const { data: countData } = useUnreadNotificationCount();
  const { data: list } = useWebNotifications();
  const markRead = useMarkNotificationRead();
  const markAll = useMarkAllNotificationsRead();

  const unread = countData?.count ?? 0;
  const notifications = list?.results ?? [];

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="relative flex h-8 w-8 items-center justify-center rounded-md hover:bg-accent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-label="Notifications"
      >
        <Bell className="h-4 w-4" />
        {unread > 0 && (
          <span className="absolute -top-0.5 -right-0.5 h-4 min-w-4 rounded-full bg-primary text-[9px] font-bold text-primary-foreground flex items-center justify-center px-0.5 tabular-nums">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80 p-0" sideOffset={8}>
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <span className="text-sm font-semibold">Notifications</span>
          {unread > 0 && (
            <button
              type="button"
              onClick={() => markAll.mutate()}
              className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors"
            >
              <CheckCheck className="h-3 w-3" />
              Mark all read
            </button>
          )}
        </div>
        {notifications.length === 0 ? (
          <div className="px-4 py-8 text-center">
            <Check className="h-6 w-6 text-muted-foreground/30 mx-auto mb-2" />
            <p className="text-xs text-muted-foreground">All caught up</p>
          </div>
        ) : (
          <ScrollArea className="max-h-96">
            {notifications.map((n) => (
              <NotificationItem
                key={n.id}
                n={n}
                onRead={(id) => markRead.mutate(id)}
              />
            ))}
          </ScrollArea>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
