from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.auth import get_current_user
from app.models import User
from app.services.jobs.dispatcher import (
    INTENT_MAINTENANCE,
    RUN_SYSTEM_INTEGRITY_DIAGNOSTIC_JOB_NAME,
    RUN_SYSTEM_INTEGRITY_REPAIR_JOB_NAME,
    diagnostic_repair_dedup_key,
    diagnostic_run_dedup_key,
    dispatch_with_new_session,
)
from app.services.system_integrity import DIAGNOSTIC_DEFINITION_BY_KEY
from app.services.system_integrity.service import (
    SystemIntegrityService,
    get_system_integrity_service,
)
from app.services.system_integrity.schemas import (
    DiagnosticDefinitionListRead,
    DiagnosticRunDetailRead,
    DiagnosticRunItemPageRead,
    DiagnosticRunListRead,
    DiagnosticRunResponse,
)

router = APIRouter(prefix="/system/integrity")


@router.get("/diagnostics", response_model=DiagnosticDefinitionListRead)
def list_diagnostics(
    service: SystemIntegrityService = Depends(get_system_integrity_service),
    current_user: User = Depends(get_current_user),
) -> DiagnosticDefinitionListRead:
    del current_user
    return service.list_definitions()


@router.post("/diagnostics/{diagnostic_key}/run", response_model=DiagnosticRunResponse)
async def run_diagnostic(
    diagnostic_key: str,
    service: SystemIntegrityService = Depends(get_system_integrity_service),
    current_user: User = Depends(get_current_user),
) -> DiagnosticRunResponse:
    definition = DIAGNOSTIC_DEFINITION_BY_KEY.get(diagnostic_key)
    if definition is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Diagnostic not found",
        )
    run = service.create_run(
        diagnostic_key=diagnostic_key,
        requested_by_user_id=current_user.id,
    )
    dispatch = await dispatch_with_new_session(
        job_name=RUN_SYSTEM_INTEGRITY_DIAGNOSTIC_JOB_NAME,
        args=[str(run.id)],
        type=RUN_SYSTEM_INTEGRITY_DIAGNOSTIC_JOB_NAME,
        parameters={"run_id": str(run.id), "diagnostic_key": diagnostic_key},
        intent=INTENT_MAINTENANCE,
        dedup_key=diagnostic_run_dedup_key(diagnostic_key),
        job_key=f"diagnostic:{diagnostic_key}",
        is_visible=True,
        force=False,
    )
    run = service.attach_related_job(run_id=run.id, related_job_id=dispatch.job.id)
    return DiagnosticRunResponse(run=service.get_run_read(run))


@router.get("/diagnostics/{diagnostic_key}/latest", response_model=DiagnosticRunResponse)
def get_latest_diagnostic_run(
    diagnostic_key: str,
    service: SystemIntegrityService = Depends(get_system_integrity_service),
    current_user: User = Depends(get_current_user),
) -> DiagnosticRunResponse:
    del current_user
    return DiagnosticRunResponse(run=service.get_latest_run(diagnostic_key=diagnostic_key))


@router.get("/runs", response_model=DiagnosticRunListRead)
def list_runs(
    diagnostic_key: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    service: SystemIntegrityService = Depends(get_system_integrity_service),
    current_user: User = Depends(get_current_user),
) -> DiagnosticRunListRead:
    del current_user
    return service.list_runs(diagnostic_key=diagnostic_key, limit=limit, offset=offset)


@router.get("/runs/{run_id}", response_model=DiagnosticRunDetailRead)
def get_run(
    run_id: UUID,
    service: SystemIntegrityService = Depends(get_system_integrity_service),
    current_user: User = Depends(get_current_user),
) -> DiagnosticRunDetailRead:
    del current_user
    return service.get_run_detail(run_id)


@router.get("/runs/{run_id}/items", response_model=DiagnosticRunItemPageRead)
def list_run_items(
    run_id: UUID,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    service: SystemIntegrityService = Depends(get_system_integrity_service),
    current_user: User = Depends(get_current_user),
) -> DiagnosticRunItemPageRead:
    del current_user
    return service.list_run_items(run_id=run_id, limit=limit, offset=offset)


@router.post("/runs/{run_id}/repair", response_model=DiagnosticRunResponse)
async def repair_run(
    run_id: UUID,
    service: SystemIntegrityService = Depends(get_system_integrity_service),
    current_user: User = Depends(get_current_user),
) -> DiagnosticRunResponse:
    run = service.get_run_model(run_id)
    if run.repair_job_key is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Diagnostic does not support repair",
        )
    if run.status != "completed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Diagnostic run must be completed before repair",
        )
    dispatch = await dispatch_with_new_session(
        job_name=RUN_SYSTEM_INTEGRITY_REPAIR_JOB_NAME,
        args=[str(run.id)],
        type=RUN_SYSTEM_INTEGRITY_REPAIR_JOB_NAME,
        parameters={
            "diagnostic_run_id": str(run.id),
            "repair_job_key": run.repair_job_key,
        },
        intent=INTENT_MAINTENANCE,
        dedup_key=diagnostic_repair_dedup_key(run.id),
        job_key=f"diagnostic:repair:{run.repair_job_key}",
        is_visible=True,
        force=False,
    )
    run = service.attach_latest_repair_job(
        run_id=run.id,
        latest_repair_job_id=dispatch.job.id,
    )
    del current_user
    return DiagnosticRunResponse(run=service.get_run_read(run))
