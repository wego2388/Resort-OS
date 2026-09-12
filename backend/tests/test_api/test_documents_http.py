"""HTTP and storage security coverage for the private document vault."""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

from fastapi.testclient import TestClient

from tests.conftest import _create_test_user, _make_token, assign_test_user_to_branch


VALID_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    b"trailer\n<< /Root 1 0 R >>\nstartxref\n0\n%%EOF\n"
)


def _branch(db, label: str):
    from app.modules.core.models import Branch

    branch = Branch(
        name=f"Documents {label}",
        name_ar=f"وثائق {label}",
        code=f"DOC-{uuid.uuid4().hex[:8].upper()}",
    )
    db.add(branch)
    db.commit()
    db.refresh(branch)
    return branch


def _headers_for(db, role: str, branch_id: int) -> tuple[int, dict[str, str]]:
    email = f"documents-{role}-{uuid.uuid4().hex[:8]}@test.local"
    user_id = _create_test_user(email, role, two_factor_enabled=(role == "owner"))
    assign_test_user_to_branch(db, user_id, branch_id)
    db.commit()
    return user_id, {
        "Authorization": f"Bearer {_make_token(email, branch_id=branch_id)}",
    }


def _upload_branch(
    client: TestClient,
    headers: dict[str, str],
    *,
    title: str = "السجل التجاري",
    visibility: str = "management",
    content: bytes = VALID_PDF,
    filename: str = "register.pdf",
    content_type: str = "application/pdf",
    expiry_date: date | None = None,
):
    data = {
        "doc_type": "commercial_register",
        "title": title,
        "visibility": visibility,
    }
    if expiry_date:
        data["expiry_date"] = expiry_date.isoformat()
    return client.post(
        "/api/v1/documents/branch/upload",
        data=data,
        files={"file": (filename, content, content_type)},
        headers=headers,
    )


def _employee(db, branch_id: int, *, user_id: int | None = None):
    from app.modules.hr.models import Employee

    employee = Employee(
        branch_id=branch_id,
        employee_code=f"EMP-{uuid.uuid4().hex[:8].upper()}",
        full_name="موظف وثائق اختباري",
        position="موظف",
        basic_salary=Decimal("5000.00"),
        hire_date=date.today(),
        status="active",
        user_id=user_id,
    )
    db.add(employee)
    db.commit()
    db.refresh(employee)
    return employee


class TestBranchDocumentFlow:
    def test_upload_is_encrypted_and_download_is_verified(
        self, client: TestClient, db, monkeypatch, tmp_path,
    ):
        from app.core.config import settings
        from app.modules.core.models import AuditLog
        from app.modules.documents.models import Document

        monkeypatch.setattr(settings, "DOCUMENT_STORAGE_ROOT", str(tmp_path))
        branch = _branch(db, "secure")
        user_id, headers = _headers_for(db, "manager", branch.id)

        upload = _upload_branch(client, headers)
        assert upload.status_code == 201, upload.text
        payload = upload.json()
        assert payload["id"]
        assert payload["sha256"]
        assert "storage_key" not in payload
        assert "branch_id" not in payload

        row = db.query(Document).filter(Document.public_id == payload["id"]).one()
        stored_path = tmp_path / row.storage_key
        encrypted = stored_path.read_bytes()
        assert encrypted.startswith(b"ROSDOC1")
        assert VALID_PDF not in encrypted
        assert not (tmp_path / ".." / "uploads" / row.storage_key).exists()

        download = client.get(
            f"/api/v1/documents/branch/{payload['id']}/download",
            headers=headers,
        )
        assert download.status_code == 200, download.text
        assert download.content == VALID_PDF
        assert download.headers["cache-control"].startswith("no-store")
        assert download.headers["x-content-type-options"] == "nosniff"
        assert "attachment" in download.headers["content-disposition"]

        audit = db.query(AuditLog).filter(
            AuditLog.user_id == user_id,
            AuditLog.action == "document_downloaded",
            AuditLog.entity_id == row.id,
        ).one()
        assert "register.pdf" not in (audit.new_data or "")
        assert "السجل التجاري" not in (audit.new_data or "")

    def test_soft_delete_and_restore_keep_the_encrypted_file(
        self, client: TestClient, db, monkeypatch, tmp_path,
    ):
        from app.core.config import settings
        from app.modules.documents.models import Document

        monkeypatch.setattr(settings, "DOCUMENT_STORAGE_ROOT", str(tmp_path))
        branch = _branch(db, "restore")
        _, headers = _headers_for(db, "manager", branch.id)
        public_id = _upload_branch(client, headers).json()["id"]
        row = db.query(Document).filter(Document.public_id == public_id).one()
        stored_path = tmp_path / row.storage_key

        deleted = client.delete(
            f"/api/v1/documents/branch/{public_id}", headers=headers,
        )
        assert deleted.status_code == 204, deleted.text
        assert stored_path.is_file()
        assert client.get(
            f"/api/v1/documents/branch/{public_id}", headers=headers,
        ).status_code == 404
        deleted_list = client.get(
            "/api/v1/documents/branch/deleted", headers=headers,
        )
        assert deleted_list.status_code == 200, deleted_list.text
        assert deleted_list.json()["total"] == 1
        assert deleted_list.json()["items"][0]["is_deleted"] is True

        restored = client.post(
            f"/api/v1/documents/branch/{public_id}/restore", headers=headers,
        )
        assert restored.status_code == 200, restored.text
        assert restored.json()["is_deleted"] is False
        assert client.get(
            f"/api/v1/documents/branch/{public_id}/download", headers=headers,
        ).content == VALID_PDF

    def test_rejects_mime_spoof_and_oversized_upload(
        self, client: TestClient, db, monkeypatch, tmp_path,
    ):
        from app.core.config import settings

        monkeypatch.setattr(settings, "DOCUMENT_STORAGE_ROOT", str(tmp_path))
        branch = _branch(db, "validation")
        _, headers = _headers_for(db, "manager", branch.id)

        spoof = _upload_branch(
            client,
            headers,
            filename="identity.jpg",
            content_type="image/jpeg",
        )
        assert spoof.status_code == 400, spoof.text

        monkeypatch.setattr(settings, "DOCUMENT_MAX_FILE_SIZE_MB", 1)
        oversized = _upload_branch(
            client,
            headers,
            content=VALID_PDF + b"x" * (1024 * 1024),
        )
        assert oversized.status_code == 400, oversized.text
        assert list(tmp_path.rglob("*.rosdoc")) == []

    def test_invalid_multipart_metadata_returns_validation_error(
        self, client: TestClient, db, monkeypatch, tmp_path,
    ):
        from app.core.config import settings

        monkeypatch.setattr(settings, "DOCUMENT_STORAGE_ROOT", str(tmp_path))
        branch = _branch(db, "metadata-validation")
        _, headers = _headers_for(db, "manager", branch.id)

        response = client.post(
            "/api/v1/documents/branch/upload",
            data={
                "doc_type": "commercial_register",
                "title": "ترخيص بتواريخ غير صحيحة",
                "visibility": "employee_visible",
                "issue_date": "2026-12-31",
                "expiry_date": "2026-01-01",
            },
            files={"file": ("register.pdf", VALID_PDF, "application/pdf")},
            headers=headers,
        )
        assert response.status_code == 422, response.text
        assert list(tmp_path.rglob("*.rosdoc")) == []

    def test_cashier_cannot_upload_or_list(
        self, client: TestClient, db, monkeypatch, tmp_path,
    ):
        from app.core.config import settings

        monkeypatch.setattr(settings, "DOCUMENT_STORAGE_ROOT", str(tmp_path))
        branch = _branch(db, "permissions")
        _, headers = _headers_for(db, "cashier", branch.id)
        assert _upload_branch(client, headers).status_code == 403
        assert client.get("/api/v1/documents/branch", headers=headers).status_code == 403

    def test_document_id_does_not_cross_branch_boundary(
        self, client: TestClient, db, monkeypatch, tmp_path,
    ):
        from app.core.config import settings

        monkeypatch.setattr(settings, "DOCUMENT_STORAGE_ROOT", str(tmp_path))
        branch_a = _branch(db, "A")
        branch_b = _branch(db, "B")
        _, headers_a = _headers_for(db, "manager", branch_a.id)
        _, headers_b = _headers_for(db, "manager", branch_b.id)
        public_id = _upload_branch(client, headers_a).json()["id"]

        listing = client.get("/api/v1/documents/branch", headers=headers_b)
        assert listing.status_code == 200, listing.text
        assert listing.json()["total"] == 0
        assert client.get(
            f"/api/v1/documents/branch/{public_id}", headers=headers_b,
        ).status_code == 404
        assert client.get(
            f"/api/v1/documents/branch/{public_id}/download", headers=headers_b,
        ).status_code == 404

    def test_tampered_ciphertext_fails_before_download_audit(
        self, client: TestClient, db, monkeypatch, tmp_path,
    ):
        from app.core.config import settings
        from app.modules.core.models import AuditLog
        from app.modules.documents.models import Document

        monkeypatch.setattr(settings, "DOCUMENT_STORAGE_ROOT", str(tmp_path))
        branch = _branch(db, "tamper")
        user_id, headers = _headers_for(db, "manager", branch.id)
        public_id = _upload_branch(client, headers).json()["id"]
        row = db.query(Document).filter(Document.public_id == public_id).one()
        path = tmp_path / row.storage_key
        ciphertext = bytearray(path.read_bytes())
        ciphertext[-17] ^= 0x01
        path.write_bytes(ciphertext)

        response = client.get(
            f"/api/v1/documents/branch/{public_id}/download", headers=headers,
        )
        assert response.status_code == 500, response.text
        assert db.query(AuditLog).filter(
            AuditLog.user_id == user_id,
            AuditLog.action == "document_downloaded",
            AuditLog.entity_id == row.id,
        ).count() == 0


class TestEmployeeDocumentPrivacy:
    def test_employee_sees_only_employee_visible_documents(
        self, client: TestClient, db, monkeypatch, tmp_path,
    ):
        from app.core.config import settings

        monkeypatch.setattr(settings, "DOCUMENT_STORAGE_ROOT", str(tmp_path))
        branch = _branch(db, "employee-self")
        _, hr_headers = _headers_for(db, "hr_manager", branch.id)
        employee_user_id, employee_headers = _headers_for(db, "employee", branch.id)
        employee = _employee(db, branch.id, user_id=employee_user_id)

        for visibility, title in (
            ("employee_visible", "عقد الموظف"),
            ("hr_confidential", "إنذار سري"),
        ):
            response = client.post(
                f"/api/v1/documents/employee/{employee.id}/upload",
                data={
                    "doc_type": "employment_contract" if visibility == "employee_visible" else "warning_letter",
                    "title": title,
                    "visibility": visibility,
                },
                files={"file": ("employee.pdf", VALID_PDF, "application/pdf")},
                headers=hr_headers,
            )
            assert response.status_code == 201, response.text

        mine = client.get("/api/v1/documents/me", headers=employee_headers)
        assert mine.status_code == 200, mine.text
        assert mine.json()["total"] == 1
        assert mine.json()["items"][0]["title"] == "عقد الموظف"

        confidential = client.get(
            f"/api/v1/documents/employee/{employee.id}", headers=hr_headers,
        ).json()["items"]
        confidential_id = next(item["id"] for item in confidential if item["visibility"] == "hr_confidential")
        assert client.get(
            f"/api/v1/documents/me/{confidential_id}/download",
            headers=employee_headers,
        ).status_code == 404

    def test_general_manager_cannot_read_employee_documents(
        self, client: TestClient, db, monkeypatch, tmp_path,
    ):
        from app.core.config import settings

        monkeypatch.setattr(settings, "DOCUMENT_STORAGE_ROOT", str(tmp_path))
        branch = _branch(db, "employee-role")
        employee = _employee(db, branch.id)
        _, manager_headers = _headers_for(db, "manager", branch.id)
        assert client.get(
            f"/api/v1/documents/employee/{employee.id}", headers=manager_headers,
        ).status_code == 403


class TestOwnerDocumentProjection:
    def test_owner_sees_only_explicitly_shared_branch_documents(
        self, client: TestClient, db, monkeypatch, tmp_path,
    ):
        from app.core.config import settings

        monkeypatch.setattr(settings, "DOCUMENT_STORAGE_ROOT", str(tmp_path))
        branch = _branch(db, "owner-projection")
        _, manager_headers = _headers_for(db, "manager", branch.id)
        _, owner_headers = _headers_for(db, "owner", branch.id)

        private_upload = _upload_branch(
            client, manager_headers, title="داخلي للإدارة", visibility="management",
        )
        shared_upload = _upload_branch(
            client, manager_headers, title="متاح للمالك", visibility="owner_visible",
        )
        assert private_upload.status_code == 201, private_upload.text
        assert shared_upload.status_code == 201, shared_upload.text

        listing = client.get("/api/v1/owner/documents", headers=owner_headers)
        assert listing.status_code == 200, listing.text
        assert listing.headers["cache-control"].startswith("no-store")
        assert listing.json()["total"] == 1
        assert listing.json()["items"][0]["title"] == "متاح للمالك"

        shared_id = shared_upload.json()["id"]
        download = client.get(
            f"/api/v1/owner/documents/{shared_id}/download", headers=owner_headers,
        )
        assert download.status_code == 200, download.text
        assert download.content == VALID_PDF
        assert download.headers["cache-control"].startswith("no-store")

        private_id = private_upload.json()["id"]
        assert client.get(
            f"/api/v1/owner/documents/{private_id}/download", headers=owner_headers,
        ).status_code == 404


class TestDocumentExpiryScanner:
    def test_daily_scan_is_idempotent_per_severity_band(
        self, client: TestClient, db, monkeypatch, tmp_path,
    ):
        from app.core.config import settings
        from app.modules.documents.models import DocumentExpiryNotification
        from app.modules.documents.services import scan_expiry_notifications

        monkeypatch.setattr(settings, "DOCUMENT_STORAGE_ROOT", str(tmp_path))
        branch = _branch(db, "expiry")
        _, headers = _headers_for(db, "manager", branch.id)
        response = _upload_branch(
            client,
            headers,
            expiry_date=date.today() + timedelta(days=5),
        )
        assert response.status_code == 201, response.text

        assert scan_expiry_notifications(db) == 1
        assert scan_expiry_notifications(db) == 0
        row = db.query(DocumentExpiryNotification).one()
        assert row.threshold_days == 7
