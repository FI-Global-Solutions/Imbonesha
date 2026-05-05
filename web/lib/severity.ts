import type { Severity, FlagStatus } from "@/lib/api/types";

export const SEVERITY_LABEL: Record<Severity, string> = {
  critical: "Critical",
  high: "High",
  medium: "Medium",
  low: "Low",
};

export const SEVERITY_COLOR: Record<Severity, string> = {
  critical: "text-red-600 dark:text-red-500",
  high: "text-orange-600 dark:text-orange-500",
  medium: "text-amber-500",
  low: "text-green-600 dark:text-green-500",
};

export const SEVERITY_BG: Record<Severity, string> = {
  critical: "bg-red-600",
  high: "bg-orange-600",
  medium: "bg-amber-500",
  low: "bg-green-600",
};

export const SEVERITY_BADGE_CLASS: Record<Severity, string> = {
  critical: "bg-red-50 text-red-700 border-red-200 dark:bg-red-950 dark:text-red-400 dark:border-red-900",
  high: "bg-orange-50 text-orange-700 border-orange-200 dark:bg-orange-950 dark:text-orange-400 dark:border-orange-900",
  medium: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-400 dark:border-amber-900",
  low: "bg-green-50 text-green-700 border-green-200 dark:bg-green-950 dark:text-green-400 dark:border-green-900",
};

export const STATUS_BADGE_CLASS: Record<FlagStatus, string> = {
  pending:     "bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700",
  assigned:    "bg-blue-50 text-blue-600 border-blue-200 dark:bg-blue-950 dark:text-blue-400 dark:border-blue-900",
  in_review:   "bg-violet-50 text-violet-600 border-violet-200 dark:bg-violet-950 dark:text-violet-400 dark:border-violet-900",
  confirmed:   "bg-red-50 text-red-700 border-red-200 dark:bg-red-950 dark:text-red-400 dark:border-red-900",
  dismissed:   "bg-slate-50 text-slate-500 border-slate-200 dark:bg-slate-800 dark:text-slate-500 dark:border-slate-700",
  monitoring:  "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-950 dark:text-amber-400 dark:border-amber-900",
  inaccessible:"bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700",
  data_error:  "bg-slate-100 text-slate-600 border-slate-200 dark:bg-slate-800 dark:text-slate-400 dark:border-slate-700",
  closed:      "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-950 dark:text-emerald-400 dark:border-emerald-900",
};

export const STATUS_LABEL: Record<FlagStatus, string> = {
  pending:      "Pending",
  assigned:     "Assigned",
  in_review:    "In Review",
  confirmed:    "Confirmed",
  dismissed:    "Dismissed",
  monitoring:   "Monitoring",
  inaccessible: "Inaccessible",
  data_error:   "Data Error",
  closed:       "Closed",
};

// Map marker hex colors for MapLibre
export const SEVERITY_HEX: Record<Severity, string> = {
  critical: "#dc2626",
  high: "#ea580c",
  medium: "#f59e0b",
  low: "#16a34a",
};
