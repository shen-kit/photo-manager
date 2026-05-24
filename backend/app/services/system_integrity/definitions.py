from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DiagnosticDefinition:
    key: str
    title: str
    description: str
    repair_job_key: str | None = None

    @property
    def supports_repair(self) -> bool:
        return self.repair_job_key is not None


CHECK_ORIGINALS_EXIST = "check_originals_exist"
CHECK_ASSET_DERIVATIVES = "check_asset_derivatives"
CHECK_CLIP_EMBEDDINGS = "check_clip_embeddings"
CHECK_FACE_PROCESSING = "check_face_processing"
CHECK_ORIGINAL_FILES_WITHOUT_DB_ASSETS = "check_original_files_without_db_assets"
CHECK_PROCESSED_FILES_WITHOUT_DB_ASSETS = "check_processed_files_without_db_assets"
CHECK_PEOPLE_WITHOUT_ACTIVE_FACES = "check_people_without_active_faces"

REPAIR_ASSET_DERIVATIVES = "repair_asset_derivatives"
REPAIR_CLIP_EMBEDDINGS = "repair_clip_embeddings"
REPAIR_FACE_PROCESSING = "repair_face_processing"
REPAIR_PROCESSED_ORPHAN_FILES = "repair_processed_orphan_files"
REPAIR_PEOPLE_WITHOUT_ACTIVE_FACES = "repair_people_without_active_faces"

DIAGNOSTIC_JOB_PREFIX = "diagnostic:"

DIAGNOSTIC_DEFINITIONS = (
    DiagnosticDefinition(
        key=CHECK_ORIGINALS_EXIST,
        title="Check Originals Exist",
        description="Find asset records whose source originals are missing or invalid.",
    ),
    DiagnosticDefinition(
        key=CHECK_ASSET_DERIVATIVES,
        title="Check Asset Derivatives",
        description="Find assets missing expected processed thumbnails, previews, or video previews.",
        repair_job_key=REPAIR_ASSET_DERIVATIVES,
    ),
    DiagnosticDefinition(
        key=CHECK_CLIP_EMBEDDINGS,
        title="Check CLIP Embeddings",
        description="Find assets missing or outdated CLIP embedding state for the current default model.",
        repair_job_key=REPAIR_CLIP_EMBEDDINGS,
    ),
    DiagnosticDefinition(
        key=CHECK_FACE_PROCESSING,
        title="Check Face Processing",
        description="Find assets missing or outdated face processing state for the current default model.",
        repair_job_key=REPAIR_FACE_PROCESSING,
    ),
    DiagnosticDefinition(
        key=CHECK_ORIGINAL_FILES_WITHOUT_DB_ASSETS,
        title="Check Original Files Without DB Assets",
        description="Find original files on disk that do not map to asset rows.",
    ),
    DiagnosticDefinition(
        key=CHECK_PROCESSED_FILES_WITHOUT_DB_ASSETS,
        title="Check Processed Files Without DB Assets",
        description="Find processed files on disk that do not map to known asset or people outputs.",
        repair_job_key=REPAIR_PROCESSED_ORPHAN_FILES,
    ),
    DiagnosticDefinition(
        key=CHECK_PEOPLE_WITHOUT_ACTIVE_FACES,
        title="Check People Without Active Faces",
        description="Find people records with no active faces on non-deleted assets.",
        repair_job_key=REPAIR_PEOPLE_WITHOUT_ACTIVE_FACES,
    ),
)

DIAGNOSTIC_DEFINITION_BY_KEY = {
    definition.key: definition for definition in DIAGNOSTIC_DEFINITIONS
}

