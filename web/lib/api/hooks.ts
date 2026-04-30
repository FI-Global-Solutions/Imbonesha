import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "./client";
import type {
  User, FlagListItem, FlagDetail, FlagImagery,
  PaginatedResponse, DetectionJob,
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
}

export function useFlags(filters: FlagFilters = {}) {
  return useQuery<PaginatedResponse<FlagListItem>>({
    queryKey: ["flags", filters],
    queryFn: () =>
      apiClient.get("/flags/", { params: { ...filters, limit: filters.limit ?? 200 } })
        .then((r) => r.data),
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

// ── AOIs ──────────────────────────────────────────────────────────────────────

export function useAois() {
  return useQuery({
    queryKey: ["aois"],
    queryFn: () => apiClient.get("/aois/").then((r) => r.data),
    staleTime: 5 * 60_000,
  });
}

// ── Detection jobs ────────────────────────────────────────────────────────────

export function useCreateDetectionJob() {
  const qc = useQueryClient();
  return useMutation<DetectionJob, Error, { t1_scene_id: number; t2_scene_id: number }>({
    mutationFn: (payload) =>
      apiClient.post("/detection-jobs/", payload).then((r) => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["flags"] });
    },
  });
}
