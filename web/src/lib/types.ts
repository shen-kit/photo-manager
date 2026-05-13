export type User = {
  id: string;
  username: string;
  is_active: boolean;
};

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

export type AssetScanResponse = {
  scanned_files: number;
  already_ingested: number;
  enqueued_jobs: number;
};

export type AssetUpdatePayload = {
  captured_at?: string | null;
  description?: string | null;
  is_favorite?: boolean;
};
