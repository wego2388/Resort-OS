"""Persistence operations for documents; no HTTP or business policy."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.modules.documents.models import Document, DocumentExpiryNotification
from app.modules.documents.schemas import DocumentCreate, DocumentUpdate


def create_document(
    db: Session,
    *,
    public_id: str,
    branch_id: int,
    data: DocumentCreate,
    storage_key: str,
    original_filename: str,
    mime_type: str,
    size_bytes: int,
    sha256: str,
    uploaded_by: int,
    replaces_document_id: int | None,
    version_number: int,
) -> Document:
    document = Document(
        public_id=public_id,
        branch_id=branch_id,
        scope=data.scope,
        employee_id=data.employee_id,
        doc_type=data.doc_type,
        visibility=data.visibility,
        title=data.title,
        description=data.description,
        issue_date=data.issue_date,
        expiry_date=data.expiry_date,
        storage_key=storage_key,
        original_filename=original_filename,
        mime_type=mime_type,
        size_bytes=size_bytes,
        sha256=sha256,
        uploaded_by=uploaded_by,
        replaces_document_id=replaces_document_id,
        version_number=version_number,
    )
    db.add(document)
    db.flush()
    return document


def get_document(
    db: Session,
    public_id: str,
    *,
    include_deleted: bool = False,
) -> Document | None:
    query = db.query(Document).filter(Document.public_id == public_id)
    if not include_deleted:
        query = query.filter(Document.deleted_at.is_(None))
    return query.first()


def lock_document(db: Session, public_id: str) -> Document | None:
    return (
        db.query(Document)
        .filter(Document.public_id == public_id, Document.deleted_at.is_(None))
        .with_for_update(nowait=True)
        .populate_existing()
        .first()
    )


def list_documents(
    db: Session,
    *,
    branch_id: int,
    scope: str,
    employee_id: int | None = None,
    doc_type: str | None = None,
    search: str | None = None,
    expiring_within_days: int | None = None,
    today: date,
    include_deleted: bool = False,
    only_deleted: bool = False,
    include_superseded: bool = False,
    visibility: str | None = None,
    skip: int = 0,
    limit: int = 50,
) -> tuple[list[Document], int]:
    query = db.query(Document).filter(
        Document.branch_id == branch_id,
        Document.scope == scope,
    )
    if employee_id is not None:
        query = query.filter(Document.employee_id == employee_id)
    if doc_type:
        query = query.filter(Document.doc_type == doc_type)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(Document.title.ilike(term), Document.description.ilike(term)))
    if expiring_within_days is not None:
        query = query.filter(
            Document.expiry_date.is_not(None),
            Document.expiry_date <= today + timedelta(days=expiring_within_days),
        )
    if visibility:
        query = query.filter(Document.visibility == visibility)
    if only_deleted:
        query = query.filter(Document.deleted_at.is_not(None))
    elif not include_deleted:
        query = query.filter(Document.deleted_at.is_(None))
    if not include_superseded:
        query = query.filter(Document.superseded_at.is_(None))
    total = query.count()
    rows = (
        query.order_by(Document.expiry_date.asc().nullslast(), Document.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return rows, total


def update_document(db: Session, document: Document, data: DocumentUpdate) -> Document:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(document, field, value)
    db.flush()
    return document


def notification_exists(
    db: Session,
    document_id: int,
    expiry_date: date,
    threshold_days: int,
) -> bool:
    return db.query(DocumentExpiryNotification.id).filter(
        DocumentExpiryNotification.document_id == document_id,
        DocumentExpiryNotification.expiry_date == expiry_date,
        DocumentExpiryNotification.threshold_days == threshold_days,
    ).first() is not None


def create_expiry_notification(
    db: Session,
    document_id: int,
    expiry_date: date,
    threshold_days: int,
) -> DocumentExpiryNotification:
    row = DocumentExpiryNotification(
        document_id=document_id,
        expiry_date=expiry_date,
        threshold_days=threshold_days,
    )
    db.add(row)
    db.flush()
    return row


def list_documents_due_for_expiry_scan(db: Session, *, today: date) -> list[Document]:
    return db.query(Document).filter(
        Document.deleted_at.is_(None),
        Document.superseded_at.is_(None),
        Document.expiry_date.is_not(None),
        Document.expiry_date <= today + timedelta(days=60),
    ).order_by(Document.expiry_date).all()
