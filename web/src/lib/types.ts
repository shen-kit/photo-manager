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

export type MediaKind = "image" | "video";

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
  thumbnail_path: string | null;
  thumbnail_url: string | null;
  thumbnail_manually_set: boolean;
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

export type AssetGridItem = {
  id: string;
  mime_type: string;
  media_kind: MediaKind;
  captured_at: string | null;
  timeline_day: string;
  is_favorite: boolean;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  has_large_preview: boolean;
  small_thumbnail_url: string;
  blurhash: string | null;
};

export type CursorPage<T> = {
  items: T[];
  next_cursor: string | null;
  has_more: boolean;
};

export type AssetGridPage = CursorPage<AssetGridItem>;

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
  preview_url: string;
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
  preview_url: string;
  blurhash: string | null;
  queued_job: boolean;
};

export type AssetPreviewEnsureStatus =
  | "ready"
  | "generating"
  | "failed"
  | "unsupported"
  | "not_found";

export type AssetPreviewEnsureItem = {
  asset_id: string;
  status: AssetPreviewEnsureStatus;
  preview_url: string | null;
  job_id: string | null;
  error: string | null;
};

export type AssetPreviewEnsureResponse = {
  items: AssetPreviewEnsureItem[];
};

export type Job = {
  id: string;
  type: string;
  job_key: string | null;
  status: JobStatus;
  progress_current: number;
  progress_total: number | null;
  progress_message: string | null;
  parameters: Record<string, unknown> | null;
  result: Record<string, unknown> | null;
  error_message: string | null;
  parent_job_id: string | null;
  related_asset_id: string | null;
  is_visible: boolean;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
};

export type ManualJobMode = "global" | "batched";

export type ManualJobParameter = {
  name: string;
  type: "boolean" | "integer" | "number";
  required: boolean;
  default: unknown;
  description: string | null;
  minimum: number | null;
  maximum: number | null;
  step: number | null;
};

export type ManualJobDefinition = {
  job_key: string;
  title: string;
  description: string;
  category: string;
  mode: ManualJobMode;
  supports_dry_run: boolean;
  batch_size: number | null;
  pending_count: number | null;
  active_job_id: string | null;
  active_status: JobStatus | null;
  last_job_id: string | null;
  last_status: JobStatus | null;
  last_finished_at: string | null;
  parameters: ManualJobParameter[];
  default_params: Record<string, unknown>;
};

export type ManualJobCatalog = {
  items: ManualJobDefinition[];
};

export type ManualJobRunPayload = {
  params?: Record<string, unknown>;
};

export type ManualJobRunResponse = {
  job: Job;
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
  mime_type: string;
  media_kind: MediaKind;
  captured_at: string | null;
  timeline_day: string;
  is_favorite: boolean;
  width: number | null;
  height: number | null;
  duration_seconds: number | null;
  has_large_preview: boolean;
  small_thumbnail_url: string;
  blurhash: string | null;
  score: number;
  distance: number;
};

export type SearchResponse = {
  items: SearchResultItem[];
  query: string;
  next_cursor: string | null;
  has_more: boolean;
};

export type TrashSort =
  | "deleted_at_desc"
  | "deleted_at_asc"
  | "taken_at_desc"
  | "taken_at_asc";

export type TrashAssetListItem = {
  id: string;
  deleted_at: string;
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

export type TrashAssetListResponse = {
  items: TrashAssetListItem[];
  page: number;
  page_size: number;
  total: number;
};

export type TrashAssetDetail = {
  id: string;
  file_hash: string;
  master_path: string;
  mime_type: string;
  deleted_at: string;
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
  preview_url: string;
  created_at: string;
};

export type RestoredAssetDetail = Omit<TrashAssetDetail, "deleted_at">;

export type TimelineBucketCover = {
  id: string;
  media_kind: MediaKind;
  small_thumbnail_url: string;
  blurhash: string | null;
};

export type TimelineMonthBucket = {
  month: string;
  asset_count: number;
  first_timeline_at: string;
  last_timeline_at: string;
  cover: TimelineBucketCover | null;
};

export type TimelineDayBucket = {
  day: string;
  asset_count: number;
  first_timeline_at: string;
  last_timeline_at: string;
  cover: TimelineBucketCover | null;
};

export type TrashRestoreJobSummary = {
  queued_metadata_job: boolean;
  queued_embedding_job: boolean;
  queued_face_job: boolean;
  ran_face_matching: boolean;
  matched_faces: number;
};

export type TrashRestoreResponse = {
  asset: RestoredAssetDetail;
  jobs: TrashRestoreJobSummary;
};

export type TrashBulkRestorePayload = {
  asset_ids: string[];
};

export type TrashRestoreFailure = {
  asset_id: string;
  detail: string;
};

export type TrashBulkRestoreResponse = {
  requested: number;
  restored: number;
  failed: number;
  items: TrashRestoreResponse[];
  failures: TrashRestoreFailure[];
};
