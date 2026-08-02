"""
tests/test_api/test_maintenance_http.py
HTTP-level tests for the maintenance router — test_maintenance.py already
covers services.py business rules directly; this file covers what only a
real HTTP request exercises: role gates, status codes, pagination, and 404s.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="Maintenance HTTP Branch", name_ar="فرع الصيانة",
               code=f"MNT-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    # Gate 4B: عمليات الصيانة بقت تفرض branch isolation server-side
    # (2026-07-28) — نفس نمط test_timeshare_http.py's make_branch_committed.
    _link_shared_users_to_branch(db, b.id)
    return b


def _link_shared_users_to_branch(db, branch_id: int) -> None:
    from app.core.kernel.models.user import User
    from tests.conftest import assign_test_user_to_branch

    for email in ("waiter@test.local", "manager@test.local"):
        user = db.query(User).filter(User.email == email).first()
        if user:
            assign_test_user_to_branch(db, user.id, branch_id)
    db.commit()


def make_employee_committed(db, branch, phone: str | None = None):
    from datetime import date as _date
    from decimal import Decimal
    from app.modules.hr.models import Employee
    emp = Employee(
        branch_id=branch.id, employee_code=f"EMP-{uuid.uuid4().hex[:6].upper()}",
        full_name="فني صيانة", position="Technician", basic_salary=Decimal("4000.00"),
        hire_date=_date.today(), phone=phone,
    )
    db.add(emp)
    db.commit()
    return emp


def create_asset(client: TestClient, branch_id: int, headers: dict) -> dict:
    resp = client.post(
        "/api/v1/maintenance/assets",
        json={"branch_id": branch_id, "name": "مكيف اللوبي", "code": f"AST-{uuid.uuid4().hex[:6]}", "category": "hvac"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestAssetsEndpoints:
    def test_create_requires_manager(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/maintenance/assets",
            json={"branch_id": branch.id, "name": "أصل", "code": "AST-1", "category": "hvac"},
            headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_create_list_and_get(self, client: TestClient, db, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        asset = create_asset(client, branch.id, manager_headers)

        list_resp = client.get("/api/v1/maintenance/assets", params={"branch_id": branch.id}, headers=waiter_headers)
        assert list_resp.status_code == 200
        assert any(a["id"] == asset["id"] for a in list_resp.json()["items"])

        get_resp = client.get(f"/api/v1/maintenance/assets/{asset['id']}", headers=waiter_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["code"] == asset["code"]

    def test_get_missing_asset_404(self, client: TestClient, waiter_headers):
        resp = client.get("/api/v1/maintenance/assets/999999999", headers=waiter_headers)
        assert resp.status_code == 404

    def test_update_asset(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        asset = create_asset(client, branch.id, manager_headers)
        resp = client.patch(
            f"/api/v1/maintenance/assets/{asset['id']}", json={"location": "الدور الثاني"}, headers=manager_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["location"] == "الدور الثاني"

    def test_dispose_requires_admin_not_just_manager(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        asset = create_asset(client, branch.id, manager_headers)
        resp = client.post(f"/api/v1/maintenance/assets/{asset['id']}/dispose", headers=manager_headers)
        assert resp.status_code == 403

    def test_dispose_as_admin_succeeds(self, client: TestClient, db, manager_headers):
        from tests.conftest import _create_test_user, _make_token, assign_test_user_to_branch
        branch = make_branch_committed(db)
        asset = create_asset(client, branch.id, manager_headers)
        email = f"maint-admin-{uuid.uuid4().hex[:6]}@test.local"
        user_id = _create_test_user(email, "admin")
        assign_test_user_to_branch(db, user_id, branch.id)
        db.commit()
        headers = {"Authorization": f"Bearer {_make_token(email)}"}

        resp = client.post(f"/api/v1/maintenance/assets/{asset['id']}/dispose", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "disposed"


class TestWorkOrdersEndpoints:
    def test_any_active_user_can_report_a_work_order(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/maintenance/work-orders",
            json={"branch_id": branch.id, "title": "تسريب مياه في الحمام", "priority": "high"},
            headers=waiter_headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["status"] == "open"

    def test_list_get_and_update(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        wo = client.post(
            "/api/v1/maintenance/work-orders",
            json={"branch_id": branch.id, "title": "عطل كهربائي", "priority": "critical"},
            headers=waiter_headers,
        ).json()

        list_resp = client.get("/api/v1/maintenance/work-orders", params={"branch_id": branch.id}, headers=waiter_headers)
        assert any(w["id"] == wo["id"] for w in list_resp.json()["items"])

        get_resp = client.get(f"/api/v1/maintenance/work-orders/{wo['id']}", headers=waiter_headers)
        assert get_resp.status_code == 200

        update_resp = client.patch(
            f"/api/v1/maintenance/work-orders/{wo['id']}", json={"status": "in_progress"}, headers=waiter_headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["status"] == "in_progress"

    def test_get_missing_work_order_404(self, client: TestClient, waiter_headers):
        resp = client.get("/api/v1/maintenance/work-orders/999999999", headers=waiter_headers)
        assert resp.status_code == 404

    def test_critical_work_order_creation_queues_notification_task(
        self, client: TestClient, db, waiter_headers,
    ):
        """wagdy.md #7: priority=critical لازم يطلق notify_critical_work_order
        عبر .delay() من غير ما يعطّل رد الـ API. الـ task نفسه (بحثه عن الـ WO
        عبر SessionLocal منفصلة + استدعاء send_whatsapp_message الفعلي) مُختبَر
        بشكل مباشر ومعزول في test_tasks/test_maintenance_tasks.py — هنا بس
        بنتأكد إن إنشاء أمر عاجل بينجح ومبيتأخرش (الإرسال async مش sync)."""
        from unittest.mock import patch
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch, phone="01098765432")

        with patch("app.tasks.maintenance_tasks.notify_critical_work_order.delay") as mock_delay:
            resp = client.post(
                "/api/v1/maintenance/work-orders",
                json={
                    "branch_id": branch.id, "title": "تسريب غاز مطبخ",
                    "priority": "critical", "assigned_to": emp.id,
                },
                headers=waiter_headers,
            )
        assert resp.status_code == 201, resp.text
        mock_delay.assert_called_once_with(resp.json()["id"])

    def test_non_critical_work_order_does_not_queue_notification(self, client: TestClient, db, waiter_headers):
        from unittest.mock import patch
        branch = make_branch_committed(db)
        emp = make_employee_committed(db, branch, phone="01098765432")

        with patch("app.tasks.maintenance_tasks.notify_critical_work_order.delay") as mock_delay:
            resp = client.post(
                "/api/v1/maintenance/work-orders",
                json={
                    "branch_id": branch.id, "title": "لمبة محروقة",
                    "priority": "low", "assigned_to": emp.id,
                },
                headers=waiter_headers,
            )
        assert resp.status_code == 201, resp.text
        mock_delay.assert_not_called()

    def test_update_and_add_part_reject_customer_role(self, client: TestClient, db, waiter_headers):
        """Regression: PATCH .../work-orders/{id} and POST .../parts used to
        accept *any* authenticated user (get_current_active_user, level 0) —
        including a self-registered "customer" account — with no ownership
        check, letting them reassign/reprioritize/cost real maintenance work
        orders. Both now require get_employee_user (level >= 20)."""
        from tests.conftest import _create_test_user, _make_token
        branch = make_branch_committed(db)
        wo = client.post(
            "/api/v1/maintenance/work-orders",
            json={"branch_id": branch.id, "title": "تسريب مياه"},
            headers=waiter_headers,
        ).json()

        email = f"maint-customer-{uuid.uuid4().hex[:6]}@test.local"
        _create_test_user(email, "customer")
        customer_headers = {"Authorization": f"Bearer {_make_token(email)}"}

        update_resp = client.patch(
            f"/api/v1/maintenance/work-orders/{wo['id']}",
            json={"status": "in_progress"},
            headers=customer_headers,
        )
        assert update_resp.status_code == 403

        part_resp = client.post(
            f"/api/v1/maintenance/work-orders/{wo['id']}/parts",
            json={"part_name": "مضخة", "quantity": 1, "unit_cost": 500},
            headers=customer_headers,
        )
        assert part_resp.status_code == 403

    def test_complete_requires_manager(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        wo = client.post(
            "/api/v1/maintenance/work-orders",
            json={"branch_id": branch.id, "title": "صيانة مصعد"},
            headers=waiter_headers,
        ).json()
        resp = client.post(f"/api/v1/maintenance/work-orders/{wo['id']}/complete", headers=waiter_headers)
        assert resp.status_code == 403

    def test_complete_as_manager_succeeds(self, client: TestClient, db, waiter_headers, manager_headers):
        branch = make_branch_committed(db)
        wo = client.post(
            "/api/v1/maintenance/work-orders",
            json={"branch_id": branch.id, "title": "صيانة مصعد"},
            headers=waiter_headers,
        ).json()
        resp = client.post(f"/api/v1/maintenance/work-orders/{wo['id']}/complete", headers=manager_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "completed"

    def test_generic_patch_cannot_bypass_complete_endpoint(
        self, client: TestClient, db, waiter_headers, manager_headers,
    ):
        """باج حقيقي اتصلح (2026-08-02): PATCH /work-orders/{id} العادي كان
        بيقبل status="completed" مباشرة (get_employee_user، مستوى 20) —
        بينما POST .../complete المخصص محتاج مدير+ (مستوى 60، راجع
        test_complete_requires_manager فوق). أي waiter كان يقدر يستخدم
        PATCH العادي يتخطى فحص الصلاحية تمامًا، وكمان يتخطى كل الأثر
        الجانبي الحقيقي (تحرير الأصل من under_maintenance، تقديم next_due
        لجدول الصيانة الوقائية، تسجيل completed_at) — الأمر كان يفضل
        "مكتمل" شكليًا بس من غير أي من الآثار دي أبدًا."""
        branch = make_branch_committed(db)
        asset = create_asset(client, branch.id, manager_headers)
        wo = client.post(
            "/api/v1/maintenance/work-orders",
            json={
                "branch_id": branch.id, "title": "صيانة حرجة",
                "asset_id": asset["id"], "priority": "critical",
            },
            headers=waiter_headers,
        ).json()
        # priority=critical بيحوّل الأصل لـ under_maintenance وقت الإنشاء
        asset_after_create = client.get(f"/api/v1/maintenance/assets/{asset['id']}", headers=waiter_headers).json()
        assert asset_after_create["status"] == "under_maintenance"

        resp = client.patch(
            f"/api/v1/maintenance/work-orders/{wo['id']}",
            json={"status": "completed"},
            headers=waiter_headers,
        )
        assert resp.status_code == 400, (
            f"PATCH العادي لازم يرفض status=completed كليًا (رسالة توجّه لـ /complete) "
            f"بغض النظر عن هوية المستخدم — الموجود: {resp.status_code} {resp.text}"
        )

        # حتى مدير (اللي أصلاً مؤهّل لـ/complete) لازم يوجّه لنفس المسار المخصص،
        # مش يكمل الأمر عبر PATCH العادي مباشرة — طريقة واحدة بس للإنهاء
        resp2 = client.patch(
            f"/api/v1/maintenance/work-orders/{wo['id']}",
            json={"status": "completed"},
            headers=manager_headers,
        )
        assert resp2.status_code == 400

        # وأمر الصيانة لسه مفتوح فعليًا — التعديل المرفوض ماغيّرش أي حاجة
        wo_after = client.get(f"/api/v1/maintenance/work-orders/{wo['id']}", headers=waiter_headers).json()
        assert wo_after["status"] != "completed"
        assert wo_after["completed_at"] is None

    def test_cancelling_last_open_order_releases_asset(
        self, client: TestClient, db, waiter_headers, manager_headers,
    ):
        """باج حقيقي اتصلح (2026-08-02): تحرير الأصل من under_maintenance
        كان مربوط بـcomplete_work_order() بس — أمر صيانة critical لو
        اتلغى (cancelled) عبر PATCH العادي بدل ما يتقفل (completed)، الأصل
        كان يفضل under_maintenance للأبد من غير أي مسار تاني يعيد الفحص."""
        branch = make_branch_committed(db)
        asset = create_asset(client, branch.id, manager_headers)
        wo = client.post(
            "/api/v1/maintenance/work-orders",
            json={
                "branch_id": branch.id, "title": "صيانة حرجة اتلغت",
                "asset_id": asset["id"], "priority": "critical",
            },
            headers=waiter_headers,
        ).json()
        asset_after_create = client.get(f"/api/v1/maintenance/assets/{asset['id']}", headers=waiter_headers).json()
        assert asset_after_create["status"] == "under_maintenance"

        resp = client.patch(
            f"/api/v1/maintenance/work-orders/{wo['id']}",
            json={"status": "cancelled"},
            headers=waiter_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "cancelled"

        asset_after_cancel = client.get(f"/api/v1/maintenance/assets/{asset['id']}", headers=waiter_headers).json()
        assert asset_after_cancel["status"] == "operational", (
            "لغاء آخر أمر صيانة مفتوح لازم يحرّر الأصل زي إكماله بالظبط"
        )

    def test_assign_to_nonexistent_employee_rejected_cleanly(self, client: TestClient, db, waiter_headers):
        """Regression: assigned_to had zero validation against the employees
        table — assigning a work order to a made-up employee id used to
        return 200 OK with no warning at all. Now a clean 400."""
        branch = make_branch_committed(db)
        wo = client.post(
            "/api/v1/maintenance/work-orders",
            json={"branch_id": branch.id, "title": "عطل كهربائي"},
            headers=waiter_headers,
        ).json()
        resp = client.patch(
            f"/api/v1/maintenance/work-orders/{wo['id']}",
            json={"assigned_to": 999999},
            headers=waiter_headers,
        )
        assert resp.status_code == 400
        assert "غير موجود" in resp.json()["detail"]

    def test_add_part_increases_cost(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        wo = client.post(
            "/api/v1/maintenance/work-orders",
            json={"branch_id": branch.id, "title": "تغيير فلتر"},
            headers=waiter_headers,
        ).json()
        resp = client.post(
            f"/api/v1/maintenance/work-orders/{wo['id']}/parts",
            json={"part_name": "فلتر هواء", "quantity": "2", "unit_cost": "50.00"},
            headers=waiter_headers,
        )
        assert resp.status_code == 201, resp.text

    def test_add_inventory_linked_part_deducts_stock(self, client: TestClient, db, waiter_headers):
        """باج حقيقي اتصلح (2026-07-28): إضافة قطعة غيار مرتبطة بصنف مخزون
        حقيقي (product_id) كانت بترجع 400 دايمًا — product.unit_cost مش
        عمود موجود أصلاً (الاسم الصح cost_price)، وStockMovementCreate كانت
        بتتبنى بحقول ناقصة/غلط. اتصلحت باستخدام inventory.consume_stock
        (نفس دالة استهلاك وصفات dining بالظبط)."""
        from decimal import Decimal
        from app.modules.inventory.models import Product, Warehouse

        branch = make_branch_committed(db)
        warehouse = Warehouse(branch_id=branch.id, name="مخزن الصيانة", code=f"WH-{uuid.uuid4().hex[:6].upper()}")
        db.add(warehouse)
        db.commit()
        product = Product(
            branch_id=branch.id, warehouse_id=warehouse.id,
            name="فلتر زيت", sku=f"SKU-{uuid.uuid4().hex[:8].upper()}",
            unit="piece", cost_price=Decimal("75.00"), current_stock=Decimal("20"),
        )
        db.add(product)
        db.commit()

        wo = client.post(
            "/api/v1/maintenance/work-orders",
            json={"branch_id": branch.id, "title": "تغيير فلتر الزيت"},
            headers=waiter_headers,
        ).json()

        resp = client.post(
            f"/api/v1/maintenance/work-orders/{wo['id']}/parts",
            json={"product_id": product.id, "part_name": "فلتر زيت", "quantity": "3"},
            headers=waiter_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert any(p["product_id"] == product.id and float(p["unit_cost"]) == 75.0 for p in body["parts"])

        db.refresh(product)
        assert product.current_stock == Decimal("17")  # 20 - 3


class TestPreventiveSchedulesEndpoints:
    def test_create_list_and_update(self, client: TestClient, db, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        asset = create_asset(client, branch.id, manager_headers)

        create_resp = client.post(
            "/api/v1/maintenance/preventive-schedules",
            json={
                "branch_id": branch.id, "asset_id": asset["id"], "title": "صيانة دورية شهرية",
                "frequency_days": 30, "next_due": str(date.today() + timedelta(days=30)),
            },
            headers=manager_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        schedule = create_resp.json()

        list_resp = client.get(
            "/api/v1/maintenance/preventive-schedules", params={"branch_id": branch.id}, headers=waiter_headers,
        )
        assert any(s["id"] == schedule["id"] for s in list_resp.json()["items"])

        update_resp = client.patch(
            f"/api/v1/maintenance/preventive-schedules/{schedule['id']}",
            json={"frequency_days": 60}, headers=manager_headers,
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["frequency_days"] == 60

    def test_create_with_nonexistent_employee_rejected_cleanly(self, client: TestClient, db, manager_headers):
        """Regression: PreventiveSchedule.assigned_to has a real DB-level FK to
        employees, but nothing validated it beforehand — assigning a schedule
        to a made-up employee id used to bubble up as a raw 500
        ("Database operation failed") instead of a clear 400."""
        branch = make_branch_committed(db)
        asset = create_asset(client, branch.id, manager_headers)
        resp = client.post(
            "/api/v1/maintenance/preventive-schedules",
            json={
                "branch_id": branch.id, "asset_id": asset["id"], "title": "صيانة دورية",
                "frequency_days": 30, "next_due": str(date.today() + timedelta(days=30)),
                "assigned_to": 999999,
            },
            headers=manager_headers,
        )
        assert resp.status_code == 400
        assert "غير موجود" in resp.json()["detail"]

    def test_create_by_waiter_rejected(self, client: TestClient, db, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        asset = create_asset(client, branch.id, manager_headers)
        resp = client.post(
            "/api/v1/maintenance/preventive-schedules",
            json={
                "branch_id": branch.id, "asset_id": asset["id"], "title": "صيانة",
                "frequency_days": 30, "next_due": str(date.today() + timedelta(days=30)),
            },
            headers=waiter_headers,
        )
        assert resp.status_code == 403
