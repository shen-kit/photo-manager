export type User = {
  id: string;
  username: string;
  is_active: boolean;
};

export type JobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";
export type NotificationLevel = "info" | "success" | "warning" | "error";
export type NotificationCategory = "scan" | "asset" | "worker" | "face" | "search" | "system";

export type AuthResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
};

export type AssetTag = {
  id: number;
  name: string;
  path: string;
};

export type PersonSummary = {
  id: string | null;
  name: string | null;
};

export type FaceSummary = {
  id: string;
  person: PersonSummary | null;
};

export type FaceBoundingBox = {
  x: number;
  y: number;
  width: number;
  height: number;
  image_width: number;
  image_height: number;
};

export type AssetFace = {
  id: string;
  asset_id: string | null;
  person_id: string | null;
  bounding_box: FaceBoundingBox | null;
  detection_confidence: number | null;
  crop_path: string | null;
  crop_url: string | null;
  is_confirmed: boolean;
  is_excluded: boolean;
  created_at: string;
  updated_at: string;
};

export type Person = {
  id: string;
  name: string | null;
  thumbnail_face_id: string | null;
  thumbnail_crop_path: string | null;
  thumbnail_crop_url: string | null;
  face_count: number;
  asset_count: number;
  is_hidden: boolean;
};

export type PersonListParams = {
  include_hidden?: boolean;
  search?: string;
};

export type PersonUpdatePayload = {
  name?: string | null;
  is_hidden?: boolean;
  thumbnail_face_id?: string | null;
};

export type PersonMergeResponse = {
  faces_moved: number;
  source_deleted: boolean;
  target_person_id: string;
};

export type AssetListItem = {
  id: string;
  captured_at: string | null;
  description: string | null;
  is_favorite: boolean;
  width: number | null;
  height: number | null;
  has_large_preview: boolean;
  small_thumbnail_url: string;
  blurhash: string | null;
  tags: AssetTag[];
  faces: FaceSummary[];
};

export type AssetListResponse = {
  items: AssetListItem[];
  page: number;
  page_size: number;
  total: number;
};

export type AssetDetail = {
  id: string;
  file_hash: string;
  master_path: string;
  mime_type: string;
  captured_at: string | null;
  captured_at_local: string | null;
  description: string | null;
  is_favorite: boolean;
  width: number | null;
  height: number | null;
  has_large_preview: boolean;
  file_size_bytes: number | null;
  video_codec: string | null;
  audio_codec: string | null;
  duration_seconds: number | null;
  preview_status: string | null;
  blurhash: string | null;
  exif_data: Record<string, unknown> | null;
  tags: AssetTag[];
  people: PersonSummary[];
  faces: FaceSummary[];
  large_preview_url: string;
  created_at: string;
};

export type AssetIngestResponse = {
  id: string;
  file_hash: string;
  master_path: string;
  mime_type: string;
  width: number | null;
  height: number | null;
  has_large_preview: boolean;
  video_codec: string | null;
  audio_codec: string | null;
  duration_seconds: number | null;
  preview_status: string | null;
  tiny_thumbnail_url: string;
  small_thumbnail_url: string;
  large_preview_url: string;
  blurhash: string | null;
  queued_job: boolean;
};

export type Job = {
  id: string;
  type: string;
  status: JobStatus;
  progress_current: number;
  progress_total: number | null;
  progress_message: string | null;
  parameters: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  error_message: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type Notification = {
  id: string;
  level: NotificationLevel;
  category: NotificationCategory;
  title: string;
  message: string | null;
  details: Record<string, unknown> | null;
  related_job_id: string | null;
  related_asset_id: string | null;
  created_at: string;
  read_at: string | null;
};

export type AssetUpdatePayload = {
  captured_at?: string | null;
  description?: string | null;
  is_favorite?: boolean;
};

export type SearchResultItem = {
  id: string;
  captured_at: string | null;
  description: string | null;
  is_favorite: boolean;
  width: number | null;
  height: number | null;
  has_large_preview: boolean;
  small_thumbnail_url: string;
  blurhash: string | null;
  score: number;
  distance: number;
  tags: AssetTag[];
  faces: FaceSummary[];
};

export type SearchResponse = {
  items: SearchResultItem[];
  query: string;
  limit: number;
  offset: number;
  total: number;
};
