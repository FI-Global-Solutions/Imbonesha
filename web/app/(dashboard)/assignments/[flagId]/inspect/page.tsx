"use client";

import { useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { format } from "date-fns";
import { ArrowLeft, Loader2, ShieldAlert, ShieldOff, Eye, Lock, AlertTriangle, Building2, Hammer, Layers, PaintBucket, CheckCircle2, Trash2, EyeOff, CalendarDays, Clock } from "lucide-react";
import { toast } from "sonner";
import Link from "next/link";
import { ReactCompareSlider, ReactCompareSliderImage } from "react-compare-slider";
import { Select as SelectPrimitive } from "@base-ui/react/select";
import { CheckIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { useFlag, useFlagImagery } from "@/lib/api/hooks";
import { apiClient } from "@/lib/api/client";
import { SEVERITY_BADGE_CLASS, SEVERITY_LABEL } from "@/lib/severity";
import type { Severity } from "@/lib/api/types";

function authedImageUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  if (typeof document === "undefined") return url;
  const token = document.cookie.match(/(?:^|; )access_token=([^;]*)/)?.[1];
  if (!token) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}token=${encodeURIComponent(decodeURIComponent(token))}`;
}

const VERDICTS = ["confirmed", "dismissed", "monitoring", "inaccessible", "data_error"] as const;

const schema = z.object({
  verdict: z.enum(VERDICTS, { message: "Verdict is required" }),
  notes: z.string().optional(),
  construction_stage: z.string().optional(),
  estimated_floors: z.string().optional(),
  occupancy_observed: z.enum(["yes", "no"]),
  visited_at: z.string().min(1, "Visit date is required"),
});

type FormData = z.infer<typeof schema>;

const VERDICT_OPTIONS = [
  { value: "confirmed",    label: "Confirmed Unauthorized",      description: "Structure built without a valid permit",      icon: ShieldAlert,   color: "text-red-500",    bg: "bg-red-500/10" },
  { value: "dismissed",   label: "Dismissed — False Positive",  description: "Detection was incorrect, no violation found", icon: ShieldOff,     color: "text-slate-500",  bg: "bg-slate-500/10" },
  { value: "monitoring",  label: "Under Monitoring",            description: "Situation needs continued observation",       icon: Eye,           color: "text-amber-500",  bg: "bg-amber-500/10" },
  { value: "inaccessible",label: "Site Inaccessible",           description: "Could not reach or enter the site",          icon: Lock,          color: "text-orange-500", bg: "bg-orange-500/10" },
  { value: "data_error",  label: "Data Error — Wrong Location", description: "Flag points to an incorrect location",       icon: AlertTriangle, color: "text-purple-500", bg: "bg-purple-500/10" },
] as const;

const STAGE_OPTIONS = [
  { value: "foundation",   label: "Foundation",   icon: Layers },
  { value: "walls",        label: "Walls",        icon: Building2 },
  { value: "roofing",      label: "Roofing",      icon: Hammer },
  { value: "finishing",    label: "Finishing",    icon: PaintBucket },
  { value: "completed",    label: "Completed",    icon: CheckCircle2 },
  { value: "demolished",   label: "Demolished",   icon: Trash2 },
  { value: "none_visible", label: "None visible", icon: EyeOff },
] as const;

const VERDICT_ITEMS = Object.fromEntries(VERDICT_OPTIONS.map((o) => [o.value, o.label]));
const STAGE_ITEMS   = Object.fromEntries(STAGE_OPTIONS.map((o)   => [o.value, o.label]));
const OCCUPANCY_ITEMS = { no: "No", yes: "Yes" };

export default function InspectPage() {
  const params = useParams();
  const router = useRouter();
  const flagId = Number(params.flagId);

  const { data: flag, isLoading: flagLoading } = useFlag(flagId);
  const { data: imagery } = useFlagImagery(flagId);

  const t1 = authedImageUrl(imagery?.t1_url);
  const t2 = authedImageUrl(imagery?.t2_url);

  const today = new Date().toISOString().slice(0, 10);
  const [visitDate, setVisitDate] = useState(today);
  const [visitTime, setVisitTime] = useState("09:00");

  const { register, handleSubmit, setValue, watch, formState: { errors, isSubmitting } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { occupancy_observed: "no", visited_at: `${today}T09:00` },
  });

  const watchedVerdict = watch("verdict");
  const showConstructionFields = watchedVerdict === "confirmed" || watchedVerdict === "monitoring";

  function handleVisitDate(e: React.ChangeEvent<HTMLInputElement>) {
    setVisitDate(e.target.value);
    setValue("visited_at", `${e.target.value}T${visitTime}`, { shouldValidate: true });
  }

  function handleVisitTime(e: React.ChangeEvent<HTMLInputElement>) {
    setVisitTime(e.target.value);
    setValue("visited_at", `${visitDate}T${e.target.value}`, { shouldValidate: true });
  }

  async function onSubmit(data: FormData) {
    try {
      await apiClient.post(`/flags/${flagId}/inspect/`, {
        verdict: data.verdict,
        notes: data.notes ?? "",
        construction_stage: data.construction_stage ?? "",
        estimated_floors: data.estimated_floors ? parseInt(data.estimated_floors, 10) : null,
        occupancy_observed: data.occupancy_observed === "yes",
        visited_at: new Date(data.visited_at).toISOString(),
      });
      toast.success("Inspection submitted");
      router.push("/assignments");
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      toast.error(msg ?? "Failed to submit inspection");
    }
  }

  if (flagLoading) {
    return (
      <div className="p-6 space-y-4 max-w-2xl">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-4 w-64" />
        <Skeleton className="h-70 w-full rounded-xl" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }

  if (!flag) {
    return (
      <div className="p-6">
        <p className="text-sm text-muted-foreground">Flag not found or not assigned to you.</p>
        <Link href="/assignments" className="text-sm text-primary mt-2 inline-block">← Back to assignments</Link>
      </div>
    );
  }

  const sev = flag.severity as Severity;

  return (
    <div className="flex flex-col h-full min-h-0 overflow-auto">
      <div className="px-6 py-5 max-w-2xl w-full space-y-6">

        {/* Back link */}
        <Link
          href="/assignments"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to assignments
        </Link>

        {/* Header */}
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className={SEVERITY_BADGE_CLASS[sev]}>
              {SEVERITY_LABEL[sev]}
            </Badge>
            <h1 className="text-xl font-semibold">
              {flag.parcel_upi ?? "Unmatched parcel"}
            </h1>
          </div>
          <p className="text-sm text-muted-foreground">
            {flag.district || "—"}
            {flag.owner_name ? ` · ${flag.owner_name}` : ""}
            {" · "}
            {flag.permit_status === "no_permit" ? "No permit" :
             flag.permit_status === "expired" ? "Expired permit" : "Active permit"}
          </p>
        </div>

        {/* Satellite imagery */}
        {t1 && t2 ? (
          <div className="rounded-xl overflow-hidden border">
            <ReactCompareSlider
              style={{ height: 280 }}
              itemOne={<ReactCompareSliderImage src={t1} alt="Before (T1)" style={{ objectFit: "cover" }} />}
              itemTwo={<ReactCompareSliderImage src={t2} alt="After (T2)" style={{ objectFit: "cover" }} />}
            />
            <div className="flex justify-between px-3 py-1.5 bg-muted/50 text-xs text-muted-foreground">
              <span>Before · {imagery?.t1_captured_at ? format(new Date(imagery.t1_captured_at), "MMM yyyy") : "T1"}</span>
              <span>After · {imagery?.t2_captured_at ? format(new Date(imagery.t2_captured_at), "MMM yyyy") : "T2"}</span>
            </div>
          </div>
        ) : (
          <div className="rounded-xl border h-36 bg-muted/30 flex items-center justify-center">
            <p className="text-sm text-muted-foreground">Imagery loading…</p>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">

          {/* Verdict */}
          <div className="space-y-1.5">
            <Label className="text-sm font-medium">
              Verdict <span className="text-destructive">*</span>
            </Label>
            <Select
              onValueChange={(v) => setValue("verdict", v as FormData["verdict"])}
              items={VERDICT_ITEMS}
            >
              <SelectTrigger className="h-11 w-full text-sm">
                <SelectValue placeholder="Select a verdict…" />
              </SelectTrigger>
              <SelectContent>
                {VERDICT_OPTIONS.map((o) => {
                  const Icon = o.icon;
                  return (
                    <SelectPrimitive.Item
                      key={o.value}
                      value={o.value}
                      className="relative flex w-full cursor-default items-center rounded-md py-2.5 px-2 text-sm outline-none select-none focus:bg-accent data-disabled:pointer-events-none data-disabled:opacity-50"
                    >
                      <SelectPrimitive.ItemText className="sr-only">{o.label}</SelectPrimitive.ItemText>
                      <div className="flex items-center gap-3 w-full pr-6">
                        <div className={`h-8 w-8 rounded-lg ${o.bg} flex items-center justify-center shrink-0`}>
                          <Icon className={`h-4 w-4 ${o.color}`} />
                        </div>
                        <div className="flex flex-col gap-0.5 min-w-0">
                          <span className={`font-semibold text-sm ${o.color}`}>{o.label}</span>
                          <span className="text-xs text-muted-foreground truncate">{o.description}</span>
                        </div>
                      </div>
                      <SelectPrimitive.ItemIndicator className="pointer-events-none absolute right-2 flex size-4 items-center justify-center">
                        <CheckIcon className="size-3.5" />
                      </SelectPrimitive.ItemIndicator>
                    </SelectPrimitive.Item>
                  );
                })}
              </SelectContent>
            </Select>
            {errors.verdict && <p className="text-xs text-destructive">{errors.verdict.message}</p>}
          </div>

          {/* Construction fields — only when relevant */}
          {showConstructionFields && (
            <>
              <div className="space-y-1.5">
                <Label className="text-sm font-medium">Construction stage</Label>
                <Select
                  onValueChange={(v) => setValue("construction_stage", v as string)}
                  items={STAGE_ITEMS}
                >
                  <SelectTrigger className="h-11 w-full text-sm">
                    <SelectValue placeholder="Select stage…" />
                  </SelectTrigger>
                  <SelectContent>
                    {STAGE_OPTIONS.map((o) => {
                      const Icon = o.icon;
                      return (
                        <SelectPrimitive.Item
                          key={o.value}
                          value={o.value}
                          className="relative flex w-full cursor-default items-center rounded-md py-2.5 px-2 text-sm outline-none select-none focus:bg-accent data-disabled:pointer-events-none data-disabled:opacity-50"
                        >
                          <SelectPrimitive.ItemText className="sr-only">{o.label}</SelectPrimitive.ItemText>
                          <div className="flex items-center gap-3 w-full pr-6">
                            <div className="h-7 w-7 rounded-md bg-muted flex items-center justify-center shrink-0">
                              <Icon className="h-3.5 w-3.5 text-muted-foreground" />
                            </div>
                            <span className="font-medium text-sm text-foreground">{o.label}</span>
                          </div>
                          <SelectPrimitive.ItemIndicator className="pointer-events-none absolute right-2 flex size-4 items-center justify-center">
                            <CheckIcon className="size-3.5" />
                          </SelectPrimitive.ItemIndicator>
                        </SelectPrimitive.Item>
                      );
                    })}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <Label htmlFor="estimated_floors" className="text-sm font-medium">Estimated floors</Label>
                  <Input
                    id="estimated_floors"
                    type="number"
                    min={1}
                    max={50}
                    placeholder="e.g. 3"
                    className="h-11"
                    {...register("estimated_floors")}
                  />
                </div>
                <div className="space-y-1.5">
                  <Label className="text-sm font-medium">Occupancy observed?</Label>
                  <Select
                    defaultValue="no"
                    onValueChange={(v) => setValue("occupancy_observed", v as "yes" | "no")}
                    items={OCCUPANCY_ITEMS}
                  >
                    <SelectTrigger className="h-11 w-full text-sm">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectPrimitive.Item value="no" className="relative flex w-full cursor-default items-center rounded-md py-2 px-2 text-sm outline-none select-none focus:bg-accent">
                        <SelectPrimitive.ItemText className="sr-only">No</SelectPrimitive.ItemText>
                        <span className="flex-1 font-medium">No</span>
                        <SelectPrimitive.ItemIndicator className="pointer-events-none absolute right-2 flex size-4 items-center justify-center">
                          <CheckIcon className="size-3.5" />
                        </SelectPrimitive.ItemIndicator>
                      </SelectPrimitive.Item>
                      <SelectPrimitive.Item value="yes" className="relative flex w-full cursor-default items-center rounded-md py-2 px-2 text-sm outline-none select-none focus:bg-accent">
                        <SelectPrimitive.ItemText className="sr-only">Yes</SelectPrimitive.ItemText>
                        <span className="flex-1 font-medium">Yes</span>
                        <SelectPrimitive.ItemIndicator className="pointer-events-none absolute right-2 flex size-4 items-center justify-center">
                          <CheckIcon className="size-3.5" />
                        </SelectPrimitive.ItemIndicator>
                      </SelectPrimitive.Item>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </>
          )}

          {/* Visit date and time */}
          <div className="space-y-1.5">
            <Label className="text-sm font-medium">
              Visit date and time <span className="text-destructive">*</span>
            </Label>
            <div className="grid grid-cols-2 gap-3">
              {/* Date */}
              <div className="relative">
                <CalendarDays className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <input
                  type="date"
                  title="Visit date"
                  value={visitDate}
                  max={today}
                  onChange={handleVisitDate}
                  className="h-11 w-full rounded-md border border-input bg-transparent pl-9 pr-3 text-sm text-foreground shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring [color-scheme:light] dark:[color-scheme:dark]"
                />
              </div>
              {/* Time */}
              <div className="relative">
                <Clock className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <input
                  type="time"
                  title="Visit time"
                  value={visitTime}
                  onChange={handleVisitTime}
                  className="h-11 w-full rounded-md border border-input bg-transparent pl-9 pr-3 text-sm text-foreground shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring [color-scheme:light] dark:[color-scheme:dark]"
                />
              </div>
            </div>
            {/* Hidden field drives validation */}
            <input type="hidden" {...register("visited_at")} />
            {errors.visited_at && <p className="text-xs text-destructive">{errors.visited_at.message}</p>}
          </div>

          {/* Notes */}
          <div className="space-y-1.5">
            <Label htmlFor="notes" className="text-sm font-medium">Notes</Label>
            <Textarea
              id="notes"
              placeholder="Describe what you observed at the site…"
              className="min-h-25 resize-y"
              {...register("notes")}
            />
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-2">
            <Link href="/assignments">
              <Button type="button" variant="outline" className="flex-1">Cancel</Button>
            </Link>
            <Button type="submit" className="flex-1 gap-1.5" disabled={isSubmitting}>
              {isSubmitting && <Loader2 className="h-4 w-4 animate-spin" />}
              {isSubmitting ? "Submitting…" : "Submit inspection"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
