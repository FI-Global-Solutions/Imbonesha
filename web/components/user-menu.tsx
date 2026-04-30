"use client";

import { useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { deleteCookie } from "@/lib/api/client";
import type { User } from "@/lib/api/types";

const ROLE_LABELS: Record<string, string> = {
  admin: "Administrator",
  rha_officer: "RHA Officer",
  district_admin: "District Admin",
  inspector: "Inspector",
  read_only: "Read Only",
};

export function UserMenu({ user }: { user: User }) {
  const router = useRouter();
  const initials = user.email.slice(0, 2).toUpperCase();

  const logout = () => {
    deleteCookie("access_token");
    deleteCookie("refresh_token");
    router.push("/login");
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        className="rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring cursor-pointer"
        aria-label="User menu"
      >
        <Avatar className="h-8 w-8">
          <AvatarFallback className="text-xs bg-primary/10 text-primary font-medium">
            {initials}
          </AvatarFallback>
        </Avatar>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-52">
        <DropdownMenuLabel className="font-normal">
          <div className="flex flex-col gap-0.5">
            <span className="text-sm font-medium truncate">{user.email}</span>
            <span className="text-xs text-muted-foreground">{ROLE_LABELS[user.role] ?? user.role}</span>
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={logout} className="text-destructive focus:text-destructive">
          <LogOut className="mr-2 h-4 w-4" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
