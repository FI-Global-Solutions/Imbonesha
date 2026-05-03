export type Severity = "critical" | "high" | "medium" | "low";
export type FlagStatus = "pending" | "assigned" | "in_review" | "confirmed" | "dismissed" | "closed";
export type PermitStatus = "active" | "expired" | "revoked" | "pending" | "no_permit" | "no_parcel" | "other" | null;

export interface User {
  id: number;
  email: string;
  username: string;
  role: "admin" | "rha_officer" | "district_admin" | "inspector" | "read_only";
  district: string;
  first_name: string;
  last_name: string;
}

export interface Permit {
  permit_no: string;
  category: string;
  get_category_display: string;
  status: string;
  issued_date: string | null;
  expiry_date: string | null;
  intended_use: string;
  max_floors_allowed: number;
  max_footprint_sqm: number | null;
  applicant_name: string;
}

export interface Parcel {
  upi: string;
  owner_name: string;
  land_use: string;
  district: string;
  sector: string;
  cell: string;
  zone_type: string;
  active_permit: Permit | null;
}

export interface SceneRef {
  id: number;
  captured_at: string;
  source: string;
  cog_path: string;
}

export interface Detection {
  id: number;
  change_type: string;
  confidence: number;
  area_sqm: number;
  centroid_lat: number | null;
  centroid_lng: number | null;
  t1_scene: SceneRef | null;
  t2_scene: SceneRef | null;
}

export interface FlagListItem {
  id: number;
  severity: Severity;
  status: FlagStatus;
  district: string;
  parcel_upi: string | null;
  owner_name: string | null;
  permit_status: PermitStatus;
  centroid_lat: number | null;
  centroid_lng: number | null;
  created_at: string;
  updated_at: string;
}

export interface FlagDetail extends FlagListItem {
  parcel: Parcel | null;
  detection: Detection;
  notes: string;
}

export interface FlagImagery {
  t1_url: string | null;
  t2_url: string | null;
  t1_captured_at: string | null;
  t2_captured_at: string | null;
}

export interface AOI {
  id: number;
  type: "Feature";
  geometry: { type: "Polygon"; coordinates: number[][][] };
  properties: {
    name: string;
    district: string;
    description: string;
    scene_count: number;
    created_at: string;
  };
}

export interface AOICollection {
  type: "FeatureCollection";
  features: AOI[];
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface DetectionJob {
  id: number;
  t1_scene_id: number;
  t2_scene_id: number;
  aoi_name: string;
  status: "queued" | "running" | "completed" | "failed";
  model_version: string;
  detection_count: number;
  started_at: string | null;
  ran_at: string | null;
  error_message: string;
  created_at: string;
}

export interface Report {
  id: string;
  title: string;
  generated_by: number | null;
  generated_by_name: string | null;
  generated_at: string;
  flag_ids: number[];
  flag_count: number;
  file_size: number;
}

export interface AnalyticsKPIs {
  total_flags: number;
  awaiting_review: number;
  confirmed_unauthorized_30d: number;
  avg_time_to_inspection_hours: number | null;
}

export interface FlagsOverTimeRow {
  date: string;
  low: number;
  medium: number;
  high: number;
  critical: number;
}

export interface AnalyticsSummary {
  kpis: AnalyticsKPIs;
  flags_over_time: FlagsOverTimeRow[];
  flags_by_district: { district: string; count: number }[];
  permit_status_breakdown: { active: number; expired: number; no_permit: number; other: number };
  detection_throughput: { week: string; jobs: number; detections: number }[];
}
