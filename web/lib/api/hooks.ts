import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "./client";
import type {
  User, FlagListItem, FlagDetail, FlagImagery,
  PaginatedResponse, DetectionJob, Report, AnalyticsSummary,
  InspectorWorkload, WebNotification, NotificationListResponse,
} from "./types";

// ── Auth ──────────────────────────────────────────────────────────────────────

export function useMe() {
  return useQuery<User>({
    queryKey: ["me"],
    queryFn: () => apiClient.get("/me/").then((r) => r.data),
    staleTime: 5 * 60_000,
    retry: false,
  });
}

// ── Flags ─────────────────────────────────────────────────────────────────────

export interface FlagFilters {
  severity?: string;
  status?: string;
  district?: string;
  limit?: number;
  has_parcel?: boolean;
}

export function useFlags(filters: FlagFilters = {}) {
  const params = {
    has_parcel: true,   // hide unparented flags from dashboard by default
    ...filters,
    limit: filters.limit ?? 200,
  };
  return useQuery<PaginatedResponse<FlagListItem>>({
    queryKey: ["flags", params],
    queryFn: () => apiClient.get("/flags/", { params }).then((r) => r.data),
    staleTime: 30_000,
  });
}

export function useFlag(id: number | null) {
  return useQuery<FlagDetail>({
    queryKey: ["flag", id],
    queryFn: () => apiClient.get(`/flags/${id}/`).then((r) => r.data),
    enabled: id !== null,
    staleTime: 30_000,
  });
}

export function useFlagImagery(id: number | null) {
  return useQuery<FlagImagery>({
    queryKey: ["flag-imagery", id],
    queryFn: () => apiClient.get(`/flags/${id}/imagery/`).then((r) => r.data),
    enabled: id !== null,
    staleTime: 10 * 60_000,
  });
}

// ── Flag mutations ────────────────────────────────────────────────────────────

export function useAssignFlag() {
  const qc = useQueryClient();
  return useMutation<FlagDetail, Error, { flagId: number; inspector_id: number }>({
    mutationFn: ({ flagId, inspector_id }) =>
      apiClient.post(`/flags/${flagId}/assign/`, { inspector_id }).then((r) => r.data),
    onSuccess: (_, { flagId }) => {
      qc.invalidateQueries({ queryKey: ["flags"] });
      qc.invalidateQueries({ queryKey: ["flag", flagId] });
      qc.invalidateQueries({ queryKey: ["inspector-workload"] });
    },
  });
}

export function useUnassignFlag() {
  const qc = useQueryClient();
  return useMutation<FlagDetail, Error, number>({
    mutationFn: (flagId) =>
      apiClient.post(`/flags/${flagId}/unassign/`).then((r) => r.data),
    onSuccess: (_, flagId) => {
      qc.invalidateQueries({ queryKey: ["flags"] });
      qc.invalidateQueries({ queryKey: ["flag", flagId] });
      qc.invalidateQueries({ queryKey: ["inspector-workload"] });
    },
  });
}

export function useBulkAssignFlags() {
  const qc = useQueryClient();
  return useMutation<{ assigned: number; skipped: number; errors: unknown[] }, Error, { flag_ids: number[]; inspector_id: number }>({
    mutationFn: (payload) =>
      apiClient.post("/flags/bulk-assign/", payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["flags"] });
      qc.invalidateQueries({ queryKey: ["inspector-workload"] });
    },
  });
}

export function useInspectorWorkload() {
  return useQuery<InspectorWorkload[]>({
    queryKey: ["inspector-workload"],
    queryFn: () => apiClient.get("/inspectors/workload/").then((r) => r.data),
    staleTime: 30_000,
  });
}

// ── AOIs ──────────────────────────────────────────────────────────────────────

export function useAois() {
  return useQuery({
    queryKey: ["aois"],
    queryFn: () => apiClient.get("/aois/").then((r) => r.data),
    staleTime: 5 * 60_000,
  });
}

// ── Detection jobs ────────────────────────────────────────────────────────────

export function useDetectionJobs() {
  return useQuery<DetectionJob[]>({
    queryKey: ["detection-jobs"],
    queryFn: () => apiClient.get("/detection-jobs/").then((r) => r.data.results ?? r.data),
    staleTime: 10_000,
    refetchInterval: 8_000,
  });
}

export function useDetectionJob(id: number | null) {
  return useQuery<DetectionJob>({
    queryKey: ["detection-job", id],
    queryFn: () => apiClient.get(`/detection-jobs/${id}/`).then((r) => r.data),
    enabled: id !== null,
    // Poll every 3 s while job is active, stop once terminal.
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 3_000 : false;
    },
  });
}

export function useCreateDetectionJob() {
  const qc = useQueryClient();
  return useMutation<DetectionJob, Error, { t1_scene_id: number; t2_scene_id: number }>({
    mutationFn: (payload) =>
      apiClient.post("/detection-jobs/", payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["flags"] });
      qc.invalidateQueries({ queryKey: ["detection-jobs"] });
    },
  });
}

// ── Analytics ─────────────────────────────────────────────────────────────────

export function useAnalytics() {
  return useQuery<AnalyticsSummary>({
    queryKey: ["analytics"],
    queryFn: () => apiClient.get("/analytics/summary/").then((r) => r.data),
    staleTime: 60_000,
  });
}

// ── Reports ───────────────────────────────────────────────────────────────────

export function useReports() {
  return useQuery<PaginatedResponse<Report>>({
    queryKey: ["reports"],
    queryFn: () => apiClient.get("/reports/").then((r) => r.data),
    staleTime: 30_000,
  });
}

export function useCreateReport() {
  const qc = useQueryClient();
  return useMutation<Report, Error, { flag_ids: number[]; title: string }>({
    mutationFn: (payload) =>
      apiClient.post("/reports/", payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reports"] });
    },
  });
}

export function useDeleteReport() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => apiClient.delete(`/reports/${id}/`).then(() => {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["reports"] });
    },
  });
}

export function useDeleteFlag() {
  const qc = useQueryClient();
  return useMutation<void, Error, number>({
    mutationFn: (id) => apiClient.delete(`/flags/${id}/`).then(() => {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["flags"] });
    },
  });
}

export function useDeleteFlags() {
  const qc = useQueryClient();
  return useMutation<{ deleted: number }, Error, number[]>({
    mutationFn: (ids) => apiClient.delete("/flags/bulk-delete/", { data: { ids } }).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["flags"] });
    },
  });
}

// ── Notifications (web) ───────────────────────────────────────────────────────

export function useWebNotifications() {
  return useQuery<NotificationListResponse>({
    queryKey: ["web-notifications"],
    queryFn: () => apiClient.get("/notifications/", { params: { limit: 20 } }).then((r) => r.data),
    refetchInterval: 30_000,
    staleTime: 20_000,
  });
}

export function useUnreadNotificationCount() {
  return useQuery<{ count: number }>({
    queryKey: ["web-notifications-unread"],
    queryFn: () => apiClient.get("/notifications/unread-count/").then((r) => r.data),
    refetchInterval: 30_000,
    staleTime: 20_000,
  });
}

export function useMarkNotificationRead() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (id) => apiClient.patch(`/notifications/${id}/read/`).then(() => {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["web-notifications"] });
      qc.invalidateQueries({ queryKey: ["web-notifications-unread"] });
    },
  });
}

export function useMarkAllNotificationsRead() {
  const qc = useQueryClient();
  return useMutation<void, Error, void>({
    mutationFn: () => apiClient.post("/notifications/mark-all-read/").then(() => {}),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["web-notifications"] });
      qc.invalidateQueries({ queryKey: ["web-notifications-unread"] });
    },
  });
}
