"""Pydantic contracts for the private document vault."""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


DocumentScope = Literal["branch", "employee"]
DocumentVisibility = Literal[
    "management",
    "owner_visible",
    "hr_confidential",
    "employee_visible",
]

BRANCH_DOCUMENT_TYPES = frozenset({
    "commercial_register",
    "tourism_license",
    "fire_permit",
    "health_certificate",
    "building_permit",
    "liquor_license",
    "insurance_property",
    "supplier_contract",
    "lease_agreement",
    "bank_account_docs",
    "other_branch",
})

EMPLOYEE_DOCUMENT_TYPES = frozenset({
    "employment_contract",
    "national_id_copy",
    "passport_copy",
    "social_insurance_form",
    "medical_clearance",
    "experience_cert",
    "academic_cert",
    "resignation_letter",
    "warning_letter",
    "other_employee",
})


class DocumentCreate(BaseModel):
    scope: DocumentScope
    employee_id: int | None = Field(default=None, ge=1)
    doc_type: str = Field(min_length=1, max_length=50)
    visibility: DocumentVisibility
    title: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    issue_date: date | None = None
    expiry_date: date | None = None
    replaces_document_id: str | None = Field(default=None, min_length=36, max_length=36)

    @model_validator(mode="after")
    def validate_subject_and_dates(self):
        self.title = self.title.strip()
        if not self.title:
            raise ValueError("عنوان الوثيقة مطلوب")
        if self.description is not None:
            self.description = self.description.strip() or None
        if self.scope == "employee" and self.employee_id is None:
            raise ValueError("employee_id مطلوب لوثائق الموظف")
        if self.scope == "branch" and self.employee_id is not None:
            raise ValueError("employee_id غير مسموح لوثائق المنشأة")
        if self.expiry_date and self.issue_date and self.expiry_date < self.issue_date:
            raise ValueError("تاريخ الانتهاء يجب ألا يسبق تاريخ الإصدار")
        return self


class DocumentUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    issue_date: date | None = None
    expiry_date: date | None = None
    visibility: DocumentVisibility | None = None

    @model_validator(mode="after")
    def normalize_text(self):
        if self.title is not None:
            self.title = self.title.strip()
            if not self.title:
                raise ValueError("عنوان الوثيقة مطلوب")
        if self.description is not None:
            self.description = self.description.strip() or None
        return self


class DocumentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    scope: DocumentScope
    employee_id: int | None
    doc_type: str
    visibility: DocumentVisibility
    title: str
    description: str | None
    issue_date: date | None
    expiry_date: date | None
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    version_number: int
    uploaded_by: int | None
    created_at: datetime
    updated_at: datetime
    days_until_expiry: int | None
    is_deleted: bool
    is_superseded: bool


class DocumentListRead(BaseModel):
    items: list[DocumentRead]
    total: int
    page: int
    size: int


class ExpiringDocumentRead(BaseModel):
    id: str
    scope: DocumentScope
    employee_id: int | None
    employee_name: str | None
    doc_type: str
    title: str
    expiry_date: date
    days_remaining: int
