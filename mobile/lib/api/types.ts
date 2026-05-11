export type Severity = 'critical' | 'high' | 'medium' | 'low';
export type FlagStatus =
  | 'pending' | 'assigned' | 'in_review' | 'confirmed'
  | 'dismissed' | 'monitoring' | 'inaccessible' | 'data_error' | 'closed';
export type InspectionVerdict =
  | 'confirmed' | 'dismissed' | 'monitoring' | 'inaccessible' | 'data_error';

export interface User {
  id: number;
  email: string;
  username: string;
  role: 'admin' | 'rha_officer' | 'district_admin' | 'inspector' | 'read_only';
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

export interface Detection {
  id: number;
  change_type: string;
  confidence: number;
  area_sqm: number;
  centroid_lat: number | null;
  centroid_lng: number | null;
}

export interface Inspection {
  id: number;
  verdict: string;
  notes: string;
  construction_stage: string;
  estimated_floors: number | null;
  occupancy_observed: boolean;
  visited_at: string | null;
  submitted_at: string;
  inspector_name: string;
}

export interface InspectionPhoto {
  id: string;
  url: string | null;
  caption: string;
  latitude: number;
  longitude: number;
  accuracy_meters: number | null;
  captured_at: string;
  distance_from_site_m: number | null;
  uploaded_at: string;
}

export interface FlagListItem {
  id: number;
  severity: Severity;
  status: FlagStatus;
  district: string;
  parcel_upi: string | null;
  owner_name: string | null;
  permit_status: string | null;
  centroid_lat: number | null;
  centroid_lng: number | null;
  assigned_to_name: string | null;
  assigned_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface FlagDetail extends FlagListItem {
  parcel: Parcel | null;
  detection: Detection;
  notes: string;
  inspections: Inspection[];
  photos: InspectionPhoto[];
  available_transitions: string[];
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface SubmitInspectionPayload {
  verdict: InspectionVerdict;
  notes: string;
  construction_stage: string;
  estimated_floors: number | null;
  occupancy_observed: boolean;
  visited_at: string;
  photo_ids: string[];
}

export interface UploadPhotoPayload {
  flagId: number;
  uri: string;
  latitude: number;
  longitude: number;
  accuracy: number | null;
  capturedAt: string;
  caption?: string;
}
