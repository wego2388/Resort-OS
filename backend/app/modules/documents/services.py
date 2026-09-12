"""Business rules for confidential branch and employee documents."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import PurePath
from typing import BinaryIO
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.core import services as core_services
from app.modules.core.crud import create_audit_log
from app.modules.core.schemas import AuditLogCreate
from app.modules.documents import crud, storage
from app.modules.documents.models import Document
from app.modules.documents.schemas import (
    BRANCH_DOCUMENT_TYPES,
    EMPLOYEE_DOCUMENT_TYPES,
    DocumentCreate,
    DocumentListRead,
    DocumentRead,
    DocumentUpdate,
    ExpiringDocumentRead,
)
from app.resort_os.timezone_utils import local_today


class DocumentError(ValueError):
    """Base business error translated only by the HTTP router."""


class DocumentNotFoundError(DocumentError):
    pass


class DocumentBranchRequiredError(DocumentError):
    pass


class DocumentSubjectError(DocumentError):
    pass


class DocumentConflictError(DocumentError):
    pass


@dataclass(frozen=True)
class DocumentDownload:
    document: DocumentRead
    file: BinaryIO


def _active_branch_id(db: Session, user) -> int:
    branch_id = core_services.get_user_branch_id(db, user)
    if branch_id is None:
        raise DocumentBranchRequiredError("اختر فرعًا نشطًا قبل استخدام خزنة الوثائق")
    try:
        core_services.assert_branch_access(db, user, branch_id, "استخدام خزنة الوثائق")
    except PermissionError as exc:
        raise DocumentBranchRequiredError(str(exc)) from exc
    return branch_id


def _employee_in_branch(db: Session, employee_id: int, branch_id: int):
    from app.modules.hr.crud import get_employee  # noqa: PLC0415

    employee = get_employee(db, employee_id)
    if employee is None or employee.branch_id != branch_id:
        raise DocumentSubjectError("الموظف غير موجود في الفرع الحالي")
    return employee


def _employee_for_user(db: Session, user):
    from app.modules.hr.crud import get_employee_by_user_id  # noqa: PLC0415

    employee = get_employee_by_user_id(db, user.id)
    if employee is None:
        raise DocumentSubjectError("حسابك غير مرتبط بسجل موظف")
    return employee


def _validate_classification(data: DocumentCreate) -> None:
    if data.scope == "branch":
        if data.doc_type not in BRANCH_DOCUMENT_TYPES:
            raise DocumentSubjectError("نوع وثيقة المنشأة غير معتمد")
        if data.visibility not in {"management", "owner_visible"}:
            raise DocumentSubjectError("تصنيف العرض غير صالح لوثيقة منشأة")
    else:
        if data.doc_type not in EMPLOYEE_DOCUMENT_TYPES:
            raise DocumentSubjectError("نوع وثيقة الموظف غير معتمد")
        if data.visibility not in {"hr_confidential", "employee_visible"}:
            raise DocumentSubjectError("تصنيف العرض غير صالح لوثيقة موظف")


def _safe_original_filename(value: str | None) -> str:
    # PurePath on Linux does not treat a backslash as a separator, so normalize
    # both browser/platform forms before keeping only the basename.
    name = PurePath((value or "").replace("\\", "/")).name
    name = "".join(character for character in name if character.isprintable()).strip()
    if not name:
        raise storage.InvalidDocumentFileError("اسم الملف غير صالح")
    if len(name) > 255:
        raise storage.InvalidDocumentFileError("اسم الملف أطول من الحد المسموح")
    return name


def _audit(
    db: Session,
    *,
    user,
    branch_id: int,
    action: str,
    document: Document | None = None,
    scope: str | None = None,
    employee_id: int | None = None,
    extra: dict | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    payload = {
        "public_id": document.public_id if document else None,
        "scope": document.scope if document else scope,
        "employee_id": document.employee_id if document else employee_id,
    }
    if extra:
        payload.update(extra)
    # Titles, descriptions, filenames and decrypted contents are deliberately
    # excluded from the append-only audit trail.
    create_audit_log(db, AuditLogCreate(
        user_id=user.id,
        branch_id=branch_id,
        action=action,
        entity_type="document",
        entity_id=document.id if document else None,
        new_data=json.dumps(payload, ensure_ascii=False, default=str),
        ip_address=ip_address,
        user_agent=(user_agent or "")[:500] or None,
    ))


def to_read(document: Document) -> DocumentRead:
    today = local_today(settings.TIMEZONE)
    return DocumentRead(
        id=document.public_id,
        scope=document.scope,
        employee_id=document.employee_id,
        doc_type=document.doc_type,
        visibility=document.visibility,
        title=document.title,
        description=document.description,
        issue_date=document.issue_date,
        expiry_date=document.expiry_date,
        original_filename=document.original_filename,
        mime_type=document.mime_type,
        size_bytes=document.size_bytes,
        sha256=document.sha256,
        version_number=document.version_number,
        uploaded_by=document.uploaded_by,
        created_at=document.created_at,
        updated_at=document.updated_at,
        days_until_expiry=(document.expiry_date - today).days if document.expiry_date else None,
        is_deleted=document.deleted_at is not None,
        is_superseded=document.superseded_at is not None,
    )


def upload_document(
    db: Session,
    *,
    user,
    data: DocumentCreate,
    file_stream: BinaryIO,
    original_filename: str | None,
    declared_content_type: str | None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> DocumentRead:
    branch_id = _active_branch_id(db, user)
    _validate_classification(data)
    if data.employee_id is not None:
        _employee_in_branch(db, data.employee_id, branch_id)

    replacement = None
    version_number = 1
    if data.replaces_document_id:
        replacement = crud.lock_document(db, data.replaces_document_id)
        if (
            replacement is None
            or replacement.branch_id != branch_id
            or replacement.scope != data.scope
            or replacement.employee_id != data.employee_id
        ):
            raise DocumentConflictError("الوثيقة المستبدلة غير موجودة في نفس النطاق")
        if replacement.superseded_at is not None:
            raise DocumentConflictError("الوثيقة المستبدلة لها نسخة أحدث بالفعل")
        version_number = replacement.version_number + 1

    public_id = str(uuid4())
    storage_key = f"{branch_id}/{public_id}.rosdoc"
    safe_filename = _safe_original_filename(original_filename)
    stored: storage.StoredDocument | None = None
    try:
        if not settings.FIELD_ENCRYPTION_KEY:
            raise storage.DocumentStorageError("مفتاح تشفير الوثائق غير مُعد")
        stored = storage.store_encrypted(
            file_stream,
            storage_root=settings.DOCUMENT_STORAGE_ROOT,
            storage_key=storage_key,
            public_id=public_id,
            original_filename=safe_filename,
            declared_content_type=declared_content_type,
            field_encryption_key=settings.FIELD_ENCRYPTION_KEY,
            max_size_bytes=settings.DOCUMENT_MAX_FILE_SIZE_MB * 1024 * 1024,
        )
        document = crud.create_document(
            db,
            public_id=public_id,
            branch_id=branch_id,
            data=data,
            storage_key=stored.storage_key,
            original_filename=safe_filename,
            mime_type=stored.mime_type,
            size_bytes=stored.size_bytes,
            sha256=stored.sha256,
            uploaded_by=user.id,
            replaces_document_id=replacement.id if replacement else None,
            version_number=version_number,
        )
        if replacement is not None:
            replacement.superseded_at = datetime.now(timezone.utc)
        _audit(
            db,
            user=user,
            branch_id=branch_id,
            action="document_uploaded",
            document=document,
            extra={
                "doc_type": document.doc_type,
                "visibility": document.visibility,
                "version_number": document.version_number,
                "sha256": document.sha256,
            },
            ip_address=ip_address,
            user_agent=user_agent,
        )
        db.commit()
        db.refresh(document)
        return to_read(document)
    except Exception:
        db.rollback()
        if stored is not None:
            storage.delete_stored_file(
                storage_root=settings.DOCUMENT_STORAGE_ROOT,
                storage_key=stored.storage_key,
            )
        raise


def list_for_scope(
    db: Session,
    *,
    user,
    scope: str,
    employee_id: int | None = None,
    doc_type: str | None = None,
    search: str | None = None,
    expiring_within_days: int | None = None,
    page: int = 1,
    size: int = 50,
    self_service: bool = False,
    only_deleted: bool = False,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> DocumentListRead:
    branch_id = _active_branch_id(db, user)
    visibility = None
    if scope == "employee":
        if self_service:
            employee = _employee_for_user(db, user)
            if employee.branch_id != branch_id:
                raise DocumentSubjectError("سجل الموظف خارج الفرع الحالي")
            employee_id = employee.id
            visibility = "employee_visible"
        elif employee_id is not None:
            _employee_in_branch(db, employee_id, branch_id)

    rows, total = crud.list_documents(
        db,
        branch_id=branch_id,
        scope=scope,
        employee_id=employee_id,
        doc_type=doc_type,
        search=search,
        expiring_within_days=expiring_within_days,
        today=local_today(settings.TIMEZONE),
        visibility=visibility,
        only_deleted=only_deleted,
        skip=(page - 1) * size,
        limit=size,
    )
    result = DocumentListRead(
        items=[to_read(row) for row in rows],
        total=total,
        page=page,
        size=size,
    )
    _audit(
        db,
        user=user,
        branch_id=branch_id,
        action="documents_listed",
        scope=scope,
        employee_id=employee_id,
        extra={
            "self_service": self_service,
            "only_deleted": only_deleted,
            "result_count": len(rows),
        },
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.commit()
    return result


def list_owner_visible_documents(
    db: Session,
    *,
    branch_id: int,
    doc_type: str | None = None,
    search: str | None = None,
    page: int = 1,
    size: int = 50,
) -> DocumentListRead:
    """Read-only owner projection: branch documents explicitly shared by management.

    This deliberately accepts the already-authorized server-side branch id,
    not a user or client-provided scope, and can never traverse employee rows.
    """
    rows, total = crud.list_documents(
        db,
        branch_id=branch_id,
        scope="branch",
        doc_type=doc_type,
        search=search,
        today=local_today(settings.TIMEZONE),
        visibility="owner_visible",
        skip=(page - 1) * size,
        limit=size,
    )
    return DocumentListRead(
        items=[to_read(row) for row in rows],
        total=total,
        page=page,
        size=size,
    )


def download_owner_visible_document(
    db: Session,
    *,
    branch_id: int,
    public_id: str,
) -> DocumentDownload:
    """Verify and decrypt one explicitly owner-visible branch document."""
    document = crud.get_document(db, public_id)
    if (
        document is None
        or document.branch_id != branch_id
        or document.scope != "branch"
        or document.visibility != "owner_visible"
        or document.superseded_at is not None
    ):
        raise DocumentNotFoundError("الوثيقة غير موجودة")
    if not settings.FIELD_ENCRYPTION_KEY:
        raise storage.DocumentStorageError("مفتاح تشفير الوثائق غير مُعد")
    verified_file = storage.decrypt_verified_to_spooled_file(
        storage_root=settings.DOCUMENT_STORAGE_ROOT,
        storage_key=document.storage_key,
        public_id=document.public_id,
        expected_size=document.size_bytes,
        expected_sha256=document.sha256,
        field_encryption_key=settings.FIELD_ENCRYPTION_KEY,
    )
    return DocumentDownload(document=to_read(document), file=verified_file)


def _resolve_document(
    db: Session,
    *,
    user,
    public_id: str,
    expected_scope: str,
    employee_id: int | None = None,
    self_service: bool = False,
    include_deleted: bool = False,
) -> tuple[Document, int]:
    branch_id = _active_branch_id(db, user)
    document = crud.get_document(db, public_id, include_deleted=include_deleted)
    if document is None or document.branch_id != branch_id or document.scope != expected_scope:
        raise DocumentNotFoundError("الوثيقة غير موجودة")
    if expected_scope == "employee":
        if self_service:
            employee = _employee_for_user(db, user)
            if (
                employee.branch_id != branch_id
                or document.employee_id != employee.id
                or document.visibility != "employee_visible"
            ):
                raise DocumentNotFoundError("الوثيقة غير موجودة")
        elif employee_id is not None:
            _employee_in_branch(db, employee_id, branch_id)
            if document.employee_id != employee_id:
                raise DocumentNotFoundError("الوثيقة غير موجودة")
    return document, branch_id


def get_document_read(
    db: Session,
    *,
    user,
    public_id: str,
    expected_scope: str,
    employee_id: int | None = None,
    self_service: bool = False,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> DocumentRead:
    document, branch_id = _resolve_document(
        db,
        user=user,
        public_id=public_id,
        expected_scope=expected_scope,
        employee_id=employee_id,
        self_service=self_service,
    )
    result = to_read(document)
    _audit(
        db, user=user, branch_id=branch_id, action="document_viewed",
        document=document, ip_address=ip_address, user_agent=user_agent,
    )
    db.commit()
    return result


def download_document(
    db: Session,
    *,
    user,
    public_id: str,
    expected_scope: str,
    employee_id: int | None = None,
    self_service: bool = False,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> DocumentDownload:
    document, branch_id = _resolve_document(
        db,
        user=user,
        public_id=public_id,
        expected_scope=expected_scope,
        employee_id=employee_id,
        self_service=self_service,
    )
    if not settings.FIELD_ENCRYPTION_KEY:
        raise storage.DocumentStorageError("مفتاح تشفير الوثائق غير مُعد")
    verified_file = storage.decrypt_verified_to_spooled_file(
        storage_root=settings.DOCUMENT_STORAGE_ROOT,
        storage_key=document.storage_key,
        public_id=document.public_id,
        expected_size=document.size_bytes,
        expected_sha256=document.sha256,
        field_encryption_key=settings.FIELD_ENCRYPTION_KEY,
    )
    try:
        result = DocumentDownload(document=to_read(document), file=verified_file)
        _audit(
            db, user=user, branch_id=branch_id, action="document_downloaded",
            document=document, ip_address=ip_address, user_agent=user_agent,
        )
        db.commit()
        return result
    except Exception:
        verified_file.close()
        db.rollback()
        raise


def update_document(
    db: Session,
    *,
    user,
    public_id: str,
    expected_scope: str,
    data: DocumentUpdate,
    employee_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> DocumentRead:
    document, branch_id = _resolve_document(
        db,
        user=user,
        public_id=public_id,
        expected_scope=expected_scope,
        employee_id=employee_id,
    )
    merged_issue_date = data.issue_date if "issue_date" in data.model_fields_set else document.issue_date
    merged_expiry_date = data.expiry_date if "expiry_date" in data.model_fields_set else document.expiry_date
    if merged_issue_date and merged_expiry_date and merged_expiry_date < merged_issue_date:
        raise DocumentSubjectError("تاريخ الانتهاء يجب ألا يسبق تاريخ الإصدار")
    if data.visibility is not None:
        candidate = DocumentCreate(
            scope=document.scope,
            employee_id=document.employee_id,
            doc_type=document.doc_type,
            visibility=data.visibility,
            title=data.title or document.title,
            description=document.description,
            issue_date=merged_issue_date,
            expiry_date=merged_expiry_date,
        )
        _validate_classification(candidate)
    changed_fields = sorted(data.model_fields_set)
    crud.update_document(db, document, data)
    _audit(
        db, user=user, branch_id=branch_id, action="document_updated",
        document=document, extra={"changed_fields": changed_fields},
        ip_address=ip_address, user_agent=user_agent,
    )
    db.commit()
    db.refresh(document)
    return to_read(document)


def soft_delete_document(
    db: Session,
    *,
    user,
    public_id: str,
    expected_scope: str,
    employee_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> None:
    document, branch_id = _resolve_document(
        db,
        user=user,
        public_id=public_id,
        expected_scope=expected_scope,
        employee_id=employee_id,
    )
    document.deleted_at = datetime.now(timezone.utc)
    document.deleted_by = user.id
    _audit(
        db, user=user, branch_id=branch_id, action="document_deleted",
        document=document, ip_address=ip_address, user_agent=user_agent,
    )
    db.commit()


def restore_document(
    db: Session,
    *,
    user,
    public_id: str,
    expected_scope: str,
    employee_id: int | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> DocumentRead:
    document, branch_id = _resolve_document(
        db,
        user=user,
        public_id=public_id,
        expected_scope=expected_scope,
        employee_id=employee_id,
        include_deleted=True,
    )
    if document.deleted_at is None:
        raise DocumentConflictError("الوثيقة غير محذوفة")
    if not settings.FIELD_ENCRYPTION_KEY:
        raise storage.DocumentStorageError("مفتاح تشفير الوثائق غير مُعد")
    verified = storage.decrypt_verified_to_spooled_file(
        storage_root=settings.DOCUMENT_STORAGE_ROOT,
        storage_key=document.storage_key,
        public_id=document.public_id,
        expected_size=document.size_bytes,
        expected_sha256=document.sha256,
        field_encryption_key=settings.FIELD_ENCRYPTION_KEY,
    )
    verified.close()
    document.deleted_at = None
    document.deleted_by = None
    _audit(
        db, user=user, branch_id=branch_id, action="document_restored",
        document=document, ip_address=ip_address, user_agent=user_agent,
    )
    db.commit()
    db.refresh(document)
    return to_read(document)


def list_expiring_documents(
    db: Session,
    *,
    user,
    within_days: int,
    include_employee: bool,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> list[ExpiringDocumentRead]:
    branch_id = _active_branch_id(db, user)
    today = local_today(settings.TIMEZONE)
    rows, _ = crud.list_documents(
        db,
        branch_id=branch_id,
        scope="branch",
        expiring_within_days=within_days,
        today=today,
        limit=1000,
    )
    employee_rows = []
    if include_employee:
        employee_rows, _ = crud.list_documents(
            db,
            branch_id=branch_id,
            scope="employee",
            expiring_within_days=within_days,
            today=today,
            limit=1000,
        )
    employee_ids = {row.employee_id for row in employee_rows if row.employee_id is not None}
    if employee_ids:
        from app.modules.hr.models import Employee  # noqa: PLC0415
        employee_names = dict(db.query(Employee.id, Employee.full_name).filter(Employee.id.in_(employee_ids)).all())
    else:
        employee_names = {}
    result = [
        ExpiringDocumentRead(
            id=row.public_id,
            scope=row.scope,
            employee_id=row.employee_id,
            employee_name=employee_names.get(row.employee_id),
            doc_type=row.doc_type,
            title=row.title,
            expiry_date=row.expiry_date,
            days_remaining=(row.expiry_date - today).days,
        )
        for row in [*rows, *employee_rows]
        if row.expiry_date is not None
    ]
    result.sort(key=lambda item: (item.days_remaining, item.title))
    _audit(
        db, user=user, branch_id=branch_id, action="document_expiry_listed",
        scope="all" if include_employee else "branch",
        extra={"within_days": within_days, "result_count": len(result)},
        ip_address=ip_address, user_agent=user_agent,
    )
    db.commit()
    return result


def scan_expiry_notifications(db: Session) -> int:
    """Create one durable marker per document and severity band."""
    today = local_today(settings.TIMEZONE)
    created = 0
    for document in crud.list_documents_due_for_expiry_scan(db, today=today):
        days = (document.expiry_date - today).days
        threshold = -1 if days < 0 else 7 if days <= 7 else 30 if days <= 30 else 60
        if crud.notification_exists(db, document.id, document.expiry_date, threshold):
            continue
        crud.create_expiry_notification(db, document.id, document.expiry_date, threshold)
        created += 1
    db.commit()
    return created
