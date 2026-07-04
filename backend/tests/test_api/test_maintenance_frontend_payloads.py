"""
tests/test_api/test_maintenance_frontend_payloads.py
═══════════════════════════════════════════════════════════════════════
Payload-shape verification for the new el-kheima MaintenanceView.vue
(frontend/apps/el-kheima/src/views/admin/MaintenanceView.vue).

test_maintenance_http.py already covers role gates / 404s / pagination at
the HTTP layer. This file exists specifically to catch the most common bug
class found across this project during testing today: a frontend sending a
payload shape (field names, string-vs-number, omitted-vs-null) that doesn't
actually match the real Pydantic schema, silently producing a 422 the user
never sees a clear message for.

Every request body below is copied field-for-field from what the Vue
component's submit*() functions actually build (see MaintenanceView.vue),
including the exact quirks of plain (non `.number`) `v-model` bindings on
HTML <input type="number">/<input type="date"> — those are JS *strings*,
not JS numbers, unless the code explicitly wraps them in `Number(...)`.
`undefined` values are simply omitted from the dict here, mirroring what
`JSON.stringify` does to `undefined` object properties in the real browser
request.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient


def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(name="Maintenance Frontend Branch", name_ar="فرع الصيانة الواجهة",
               code=f"MNTF-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


class TestAssetCreateFormPayload:
    def test_create_asset_full_form_with_depreciation_fields(self, client: TestClient, db, manager_headers):
        """Mirrors MaintenanceView.vue::submitAsset() create branch, full form —
        including the newly-added depreciation fields (purchase_cost,
        salvage_value, useful_life_years, depreciation_start_date) which the
        old frontend never sent at all."""
        branch = make_branch(db)
        payload = {
            "branch_id": branch.id,
            "name": "مكيف الاستقبال",
            "code": f"AST-{uuid.uuid4().hex[:6]}",
            "category": "hvac",
            "location": "الاستقبال الرئيسي",
            "serial_number": "SN-12345",
            "purchase_date": str(date.today() - timedelta(days=100)),
            "warranty_until": str(date.today() + timedelta(days=600)),
            "notes": "تم تركيبه حديثاً",
            # depreciation basis — sent as *strings* exactly like a plain
            # v-model on <input type="number"> would produce (no .number modifier)
            "purchase_cost": "45000.00",
            "salvage_value": "5000.00",
            "useful_life_years": 10,  # explicitly Number()-wrapped in the component
            "depreciation_start_date": str(date.today()),
        }
        resp = client.post("/api/v1/maintenance/assets", json=payload, headers=manager_headers)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "مكيف الاستقبال"
        assert float(body["purchase_cost"]) == 45000.00
        assert float(body["salvage_value"]) == 5000.00
        assert body["useful_life_years"] == 10
        assert body["depreciation_start_date"] == str(date.today())
        assert float(body["accumulated_depreciation"]) == 0.0

    def test_create_asset_minimal_form_no_depreciation(self, client: TestClient, db, manager_headers):
        """Mirrors the create branch when the optional depreciation section is
        left empty — all the `|| undefined` fields must simply be absent from
        the wire payload (not sent as null/empty-string), matching how
        AssetCreate.salvage_value defaults to Decimal('0')."""
        branch = make_branch(db)
        payload = {
            "branch_id": branch.id,
            "name": "طاولة خشب",
            "code": f"AST-{uuid.uuid4().hex[:6]}",
            "category": "furniture",
            "salvage_value": "0",  # component always sends this (defaults to '0' string)
        }
        resp = client.post("/api/v1/maintenance/assets", json=payload, headers=manager_headers)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["purchase_cost"] is None
        assert body["useful_life_years"] is None

    def test_edit_asset_form_payload(self, client: TestClient, db, manager_headers):
        """Mirrors submitAsset() edit branch (PATCH), including status change."""
        branch = make_branch(db)
        created = client.post(
            "/api/v1/maintenance/assets",
            json={"branch_id": branch.id, "name": "مضخة مياه", "code": f"AST-{uuid.uuid4().hex[:6]}",
                  "category": "plumbing", "salvage_value": "0"},
            headers=manager_headers,
        ).json()

        edit_payload = {
            "name": "مضخة مياه رئيسية",
            "category": "plumbing",
            "location": "غرفة المكينة",
            "status": "under_maintenance",
            "purchase_cost": "12000.50",
            "salvage_value": "1000.00",
            "useful_life_years": 8,
            "depreciation_start_date": str(date.today()),
        }
        resp = client.patch(f"/api/v1/maintenance/assets/{created['id']}", json=edit_payload, headers=manager_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "under_maintenance"
        assert float(body["purchase_cost"]) == 12000.50


class TestWorkOrderFormPayload:
    def test_create_work_order_full_form(self, client: TestClient, db, waiter_headers, manager_headers):
        """Mirrors submitWorkOrder() create branch — reported by a non-manager
        user (any active user can report an issue per get_current_active_user
        on the real router — verified this is NOT manager-gated, matching what
        MaintenanceView.vue relies on to let any staff member report a fault)."""
        branch = make_branch(db)
        asset = client.post(
            "/api/v1/maintenance/assets",
            json={"branch_id": branch.id, "name": "مصعد", "code": f"AST-{uuid.uuid4().hex[:6]}",
                  "category": "other", "salvage_value": "0"},
            headers=manager_headers,
        ).json()

        payload = {
            "branch_id": branch.id,
            "asset_id": asset["id"],
            "title": "المصعد يصدر صوت غريب",
            "description": "صوت طقطقة عند الطابق الثالث",
            "order_type": "corrective",
            "priority": "high",
            "scheduled_date": str(date.today() + timedelta(days=1)),
            "notes": "تم الإبلاغ من الاستقبال",
        }
        resp = client.post("/api/v1/maintenance/work-orders", json=payload, headers=waiter_headers)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "open"
        assert body["priority"] == "high"
        assert body["asset_id"] == asset["id"]

    def test_edit_work_order_form_with_labour_fields(self, client: TestClient, db, waiter_headers):
        """Mirrors submitWorkOrder() edit branch — labour_hours/labour_cost sent
        as strings (plain v-model, no .number modifier)."""
        branch = make_branch(db)
        wo = client.post(
            "/api/v1/maintenance/work-orders",
            json={"branch_id": branch.id, "title": "عطل في التكييف المركزي"},
            headers=waiter_headers,
        ).json()

        edit_payload = {
            "title": "عطل في التكييف المركزي",
            "priority": "critical",
            "status": "in_progress",
            "scheduled_date": str(date.today()),
            "labour_hours": "3.5",
            "labour_cost": "250.00",
            "notes": "جاري العمل عليه",
        }
        resp = client.patch(f"/api/v1/maintenance/work-orders/{wo['id']}", json=edit_payload, headers=waiter_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "in_progress"
        assert float(body["labour_hours"]) == 3.5
        assert float(body["labour_cost"]) == 250.00

    def test_complete_then_add_part_flow(self, client: TestClient, db, waiter_headers, manager_headers):
        """Mirrors the openAddPart()/submitPart() sub-flow and the manager-only
        completeWorkOrder() action — both hit from the same expanded work-order
        card in MaintenanceView.vue."""
        branch = make_branch(db)
        wo = client.post(
            "/api/v1/maintenance/work-orders",
            json={"branch_id": branch.id, "title": "تغيير فلتر مكيف"},
            headers=waiter_headers,
        ).json()

        part_payload = {
            "part_name": "فلتر هواء صناعي",
            "part_number": "FLT-900",
            "quantity": "2",
            "unit_cost": "75.00",
        }
        part_resp = client.post(
            f"/api/v1/maintenance/work-orders/{wo['id']}/parts", json=part_payload, headers=waiter_headers,
        )
        assert part_resp.status_code == 201, part_resp.text
        assert float(part_resp.json()["parts_cost"]) == 150.00

        complete_resp = client.post(f"/api/v1/maintenance/work-orders/{wo['id']}/complete", headers=manager_headers)
        assert complete_resp.status_code == 200, complete_resp.text
        assert complete_resp.json()["status"] == "completed"


class TestPreventiveScheduleFormPayload:
    def test_create_schedule_form_payload(self, client: TestClient, db, manager_headers):
        """Mirrors submitSchedule() create branch — asset_id/frequency_days sent
        as numbers (explicitly Number()-wrapped in the component)."""
        branch = make_branch(db)
        asset = client.post(
            "/api/v1/maintenance/assets",
            json={"branch_id": branch.id, "name": "غلاية مياه", "code": f"AST-{uuid.uuid4().hex[:6]}",
                  "category": "plumbing", "salvage_value": "0"},
            headers=manager_headers,
        ).json()

        payload = {
            "branch_id": branch.id,
            "asset_id": asset["id"],
            "title": "فحص الغلاية الشهري",
            "frequency_days": 30,
            "next_due": str(date.today() + timedelta(days=30)),
            "checklist": "فحص الصمام، فحص الترمومتر",
        }
        resp = client.post("/api/v1/maintenance/preventive-schedules", json=payload, headers=manager_headers)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["frequency_days"] == 30
        assert body["is_active"] is True

    def test_edit_schedule_form_payload(self, client: TestClient, db, manager_headers):
        """Mirrors submitSchedule() edit branch including toggling is_active off."""
        branch = make_branch(db)
        asset = client.post(
            "/api/v1/maintenance/assets",
            json={"branch_id": branch.id, "name": "مولد كهرباء", "code": f"AST-{uuid.uuid4().hex[:6]}",
                  "category": "electrical", "salvage_value": "0"},
            headers=manager_headers,
        ).json()
        schedule = client.post(
            "/api/v1/maintenance/preventive-schedules",
            json={"branch_id": branch.id, "asset_id": asset["id"], "title": "صيانة المولد",
                  "frequency_days": 90, "next_due": str(date.today() + timedelta(days=90))},
            headers=manager_headers,
        ).json()

        edit_payload = {
            "title": "صيانة المولد الدورية",
            "frequency_days": 60,
            "next_due": str(date.today() + timedelta(days=60)),
            "checklist": "فحص الزيت والبطارية",
            "is_active": False,
        }
        resp = client.patch(
            f"/api/v1/maintenance/preventive-schedules/{schedule['id']}", json=edit_payload, headers=manager_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["frequency_days"] == 60
        assert body["is_active"] is False
