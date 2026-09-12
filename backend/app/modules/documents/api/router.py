"""Authenticated HTTP endpoints for the private document vault."""
from __future__ import annotations

from datetime import date
from urllib.parse import quote

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import Response, StreamingResponse
from pydantic import ValidationError
from starlette.background import BackgroundTask

from app.core.deps import (
    DbDep,
    get_employee_user,
    get_hr_manager_user,
    get_manager_user,
    get_operations_admin_user,
    require_permission,
)
from app.core.rate_limit import _client_ip
from app.modules.documents import services, storage
from app.modules.documents.schemas import (
    DocumentCreate,
    DocumentListRead,
    DocumentRead,
    DocumentUpdate,
    ExpiringDocumentRead,
)


router = APIRouter(prefix="/documents", tags=["documents"])


def _request_context(request: Request) -> dict[str, str | None]:
    return {
        "ip_address": _client_ip(request),
        "user_agent": request.headers.get("user-agent"),
    }


def _translate_error(exc: Exception) -> None:
    # Multipart upload fields are assembled into DocumentCreate manually, so
    # Pydantic validation errors do not pass through FastAPI's normal request
    # validation handler. Preserve the public 422 contract instead of leaking
    # an internal 500 for invalid dates, scope, visibility, or title values.
    if isinstance(exc, ValidationError):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            exc.errors(include_url=False, include_context=False, include_input=False),
        ) from exc
    if isinstance(exc, services.DocumentNotFoundError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    if isinstance(exc, services.DocumentConflictError):
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    if isinstance(exc, services.DocumentBranchRequiredError):
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    if isinstance(exc, (services.DocumentSubjectError, storage.InvalidDocumentFileError)):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    if isinstance(exc, storage.DocumentStorageError):
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            {"code": "DOCUMENT_STORAGE_ERROR", "message": "تعذر فتح مخزن الوثائق بأمان"},
        ) from exc
    raise exc


def _create_payload(
    *,
    scope: str,
    employee_id: int | None,
    doc_type: str,
    visibility: str,
    title: str,
    description: str | None,
    issue_date: date | None,
    expiry_date: date | None,
    replaces_document_id: str | None,
) -> DocumentCreate:
    return DocumentCreate(
        scope=scope,
        employee_id=employee_id,
        doc_type=doc_type,
        visibility=visibility,
        title=title,
        description=description,
        issue_date=issue_date,
        expiry_date=expiry_date,
        replaces_document_id=replaces_document_id,
    )


def _download_response(download: services.DocumentDownload) -> StreamingResponse:
    filename = download.document.original_filename.replace('"', "")
    ascii_extension = ".pdf" if download.document.mime_type == "application/pdf" else {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }.get(download.document.mime_type, "")
    fallback = f"document{ascii_extension}"

    def chunks():
        while chunk := download.file.read(256 * 1024):
            yield chunk

    return StreamingResponse(
        chunks(),
        media_type=download.document.mime_type,
        headers={
            "Cache-Control": "no-store, private, max-age=0",
            "Pragma": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox",
            "Content-Length": str(download.document.size_bytes),
            "Content-Disposition": (
                f"attachment; filename=\"{fallback}\"; "
                f"filename*=UTF-8''{quote(filename, safe='')}"
            ),
        },
        background=BackgroundTask(download.file.close),
    )


# Literal routes stay above parameterized routes; Starlette matches by order.
@router.post(
    "/branch/upload",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("documents.branch", "manage", 60))],
)
def upload_branch_document(
    request: Request,
    db: DbDep,
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    title: str = Form(...),
    visibility: str = Form("management"),
    description: str | None = Form(None),
    issue_date: date | None = Form(None),
    expiry_date: date | None = Form(None),
    replaces_document_id: str | None = Form(None),
    user=Depends(get_manager_user),
):
    try:
        return services.upload_document(
            db,
            user=user,
            data=_create_payload(
                scope="branch",
                employee_id=None,
                doc_type=doc_type,
                visibility=visibility,
                title=title,
                description=description,
                issue_date=issue_date,
                expiry_date=expiry_date,
                replaces_document_id=replaces_document_id,
            ),
            file_stream=file.file,
            original_filename=file.filename,
            declared_content_type=file.content_type,
            **_request_context(request),
        )
    except Exception as exc:
        _translate_error(exc)


@router.get(
    "/branch",
    response_model=DocumentListRead,
    dependencies=[Depends(require_permission("documents.branch", "view", 50))],
)
def list_branch_documents(
    request: Request,
    db: DbDep,
    doc_type: str | None = Query(None, max_length=50),
    search: str | None = Query(None, min_length=1, max_length=100),
    expiring_within_days: int | None = Query(None, ge=0, le=365),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    user=Depends(get_operations_admin_user),
):
    try:
        return services.list_for_scope(
            db,
            user=user,
            scope="branch",
            doc_type=doc_type,
            search=search,
            expiring_within_days=expiring_within_days,
            page=page,
            size=size,
            **_request_context(request),
        )
    except Exception as exc:
        _translate_error(exc)


@router.get(
    "/branch/expiring",
    response_model=list[ExpiringDocumentRead],
    dependencies=[Depends(require_permission("documents.branch", "view", 50))],
)
def list_expiring_branch_documents(
    request: Request,
    db: DbDep,
    days: int = Query(60, ge=0, le=365),
    user=Depends(get_operations_admin_user),
):
    try:
        return services.list_expiring_documents(
            db,
            user=user,
            within_days=days,
            include_employee=False,
            **_request_context(request),
        )
    except Exception as exc:
        _translate_error(exc)


@router.get(
    "/branch/deleted",
    response_model=DocumentListRead,
    dependencies=[Depends(require_permission("documents.branch", "manage", 60))],
)
def list_deleted_branch_documents(
    request: Request,
    db: DbDep,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    user=Depends(get_manager_user),
):
    try:
        return services.list_for_scope(
            db,
            user=user,
            scope="branch",
            page=page,
            size=size,
            only_deleted=True,
            **_request_context(request),
        )
    except Exception as exc:
        _translate_error(exc)


@router.get(
    "/branch/{document_id}",
    response_model=DocumentRead,
    dependencies=[Depends(require_permission("documents.branch", "view", 50))],
)
def get_branch_document(
    document_id: str,
    request: Request,
    db: DbDep,
    user=Depends(get_operations_admin_user),
):
    try:
        return services.get_document_read(
            db, user=user, public_id=document_id, expected_scope="branch",
            **_request_context(request),
        )
    except Exception as exc:
        _translate_error(exc)


@router.get(
    "/branch/{document_id}/download",
    dependencies=[Depends(require_permission("documents.branch", "view", 50))],
)
def download_branch_document(
    document_id: str,
    request: Request,
    db: DbDep,
    user=Depends(get_operations_admin_user),
):
    try:
        return _download_response(services.download_document(
            db, user=user, public_id=document_id, expected_scope="branch",
            **_request_context(request),
        ))
    except Exception as exc:
        _translate_error(exc)


@router.patch(
    "/branch/{document_id}",
    response_model=DocumentRead,
    dependencies=[Depends(require_permission("documents.branch", "manage", 60))],
)
def update_branch_document(
    document_id: str,
    data: DocumentUpdate,
    request: Request,
    db: DbDep,
    user=Depends(get_manager_user),
):
    try:
        return services.update_document(
            db, user=user, public_id=document_id, expected_scope="branch", data=data,
            **_request_context(request),
        )
    except Exception as exc:
        _translate_error(exc)


@router.delete(
    "/branch/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("documents.branch", "manage", 60))],
)
def delete_branch_document(
    document_id: str,
    request: Request,
    db: DbDep,
    user=Depends(get_manager_user),
):
    try:
        services.soft_delete_document(
            db, user=user, public_id=document_id, expected_scope="branch",
            **_request_context(request),
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as exc:
        _translate_error(exc)


@router.post(
    "/branch/{document_id}/restore",
    response_model=DocumentRead,
    dependencies=[Depends(require_permission("documents.branch", "manage", 60))],
)
def restore_branch_document(
    document_id: str,
    request: Request,
    db: DbDep,
    user=Depends(get_manager_user),
):
    try:
        return services.restore_document(
            db, user=user, public_id=document_id, expected_scope="branch",
            **_request_context(request),
        )
    except Exception as exc:
        _translate_error(exc)


@router.get(
    "/employee/expiring",
    response_model=list[ExpiringDocumentRead],
    dependencies=[Depends(require_permission("documents.employee", "view", 70))],
)
def list_expiring_employee_documents(
    request: Request,
    db: DbDep,
    days: int = Query(60, ge=0, le=365),
    user=Depends(get_hr_manager_user),
):
    try:
        return services.list_expiring_documents(
            db,
            user=user,
            within_days=days,
            include_employee=True,
            **_request_context(request),
        )
    except Exception as exc:
        _translate_error(exc)


@router.post(
    "/employee/{employee_id}/upload",
    response_model=DocumentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permission("documents.employee", "manage", 70))],
)
def upload_employee_document(
    employee_id: int,
    request: Request,
    db: DbDep,
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    title: str = Form(...),
    visibility: str = Form("hr_confidential"),
    description: str | None = Form(None),
    issue_date: date | None = Form(None),
    expiry_date: date | None = Form(None),
    replaces_document_id: str | None = Form(None),
    user=Depends(get_hr_manager_user),
):
    try:
        return services.upload_document(
            db,
            user=user,
            data=_create_payload(
                scope="employee",
                employee_id=employee_id,
                doc_type=doc_type,
                visibility=visibility,
                title=title,
                description=description,
                issue_date=issue_date,
                expiry_date=expiry_date,
                replaces_document_id=replaces_document_id,
            ),
            file_stream=file.file,
            original_filename=file.filename,
            declared_content_type=file.content_type,
            **_request_context(request),
        )
    except Exception as exc:
        _translate_error(exc)


@router.get(
    "/employee/{employee_id}",
    response_model=DocumentListRead,
    dependencies=[Depends(require_permission("documents.employee", "view", 70))],
)
def list_employee_documents(
    employee_id: int,
    request: Request,
    db: DbDep,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    user=Depends(get_hr_manager_user),
):
    try:
        return services.list_for_scope(
            db, user=user, scope="employee", employee_id=employee_id,
            page=page, size=size, **_request_context(request),
        )
    except Exception as exc:
        _translate_error(exc)


@router.get(
    "/employee/{employee_id}/deleted",
    response_model=DocumentListRead,
    dependencies=[Depends(require_permission("documents.employee", "manage", 70))],
)
def list_deleted_employee_documents(
    employee_id: int,
    request: Request,
    db: DbDep,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    user=Depends(get_hr_manager_user),
):
    try:
        return services.list_for_scope(
            db,
            user=user,
            scope="employee",
            employee_id=employee_id,
            page=page,
            size=size,
            only_deleted=True,
            **_request_context(request),
        )
    except Exception as exc:
        _translate_error(exc)


@router.get(
    "/employee/{employee_id}/{document_id}/download",
    dependencies=[Depends(require_permission("documents.employee", "view", 70))],
)
def download_employee_document(
    employee_id: int,
    document_id: str,
    request: Request,
    db: DbDep,
    user=Depends(get_hr_manager_user),
):
    try:
        return _download_response(services.download_document(
            db, user=user, public_id=document_id, expected_scope="employee",
            employee_id=employee_id, **_request_context(request),
        ))
    except Exception as exc:
        _translate_error(exc)


@router.patch(
    "/employee/{employee_id}/{document_id}",
    response_model=DocumentRead,
    dependencies=[Depends(require_permission("documents.employee", "manage", 70))],
)
def update_employee_document(
    employee_id: int,
    document_id: str,
    data: DocumentUpdate,
    request: Request,
    db: DbDep,
    user=Depends(get_hr_manager_user),
):
    try:
        return services.update_document(
            db, user=user, public_id=document_id, expected_scope="employee",
            employee_id=employee_id, data=data, **_request_context(request),
        )
    except Exception as exc:
        _translate_error(exc)


@router.delete(
    "/employee/{employee_id}/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permission("documents.employee", "manage", 70))],
)
def delete_employee_document(
    employee_id: int,
    document_id: str,
    request: Request,
    db: DbDep,
    user=Depends(get_hr_manager_user),
):
    try:
        services.soft_delete_document(
            db, user=user, public_id=document_id, expected_scope="employee",
            employee_id=employee_id, **_request_context(request),
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as exc:
        _translate_error(exc)


@router.post(
    "/employee/{employee_id}/{document_id}/restore",
    response_model=DocumentRead,
    dependencies=[Depends(require_permission("documents.employee", "manage", 70))],
)
def restore_employee_document(
    employee_id: int,
    document_id: str,
    request: Request,
    db: DbDep,
    user=Depends(get_hr_manager_user),
):
    try:
        return services.restore_document(
            db, user=user, public_id=document_id, expected_scope="employee",
            employee_id=employee_id, **_request_context(request),
        )
    except Exception as exc:
        _translate_error(exc)


@router.get("/me", response_model=DocumentListRead)
def list_my_documents(
    request: Request,
    db: DbDep,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=100),
    user=Depends(get_employee_user),
):
    try:
        return services.list_for_scope(
            db, user=user, scope="employee", page=page, size=size,
            self_service=True, **_request_context(request),
        )
    except Exception as exc:
        _translate_error(exc)


@router.get("/me/{document_id}/download")
def download_my_document(
    document_id: str,
    request: Request,
    db: DbDep,
    user=Depends(get_employee_user),
):
    try:
        return _download_response(services.download_document(
            db, user=user, public_id=document_id, expected_scope="employee",
            self_service=True, **_request_context(request),
        ))
    except Exception as exc:
        _translate_error(exc)
