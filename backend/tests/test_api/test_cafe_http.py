"""
tests/test_api/test_cafe_http.py
HTTP-level tests for the cafe module — TestClient through real routing,
permission dependencies and Pydantic validation (not direct service calls).

⚠️ cafe defaults to MODULE_REGISTRY.cafe.default_enabled=False — must be
enabled globally (branch_id=None). See
tests/conftest.py::enable_module_for_branch.
⚠️ Setup data created here must be `db.commit()`-ed, not `.flush()`-ed.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient

from tests.conftest import enable_module_for_branch


def make_branch_committed(db, fake_redis):
    from app.modules.core.models import Branch
    b = Branch(name="Cafe HTTP Branch", name_ar="فرع كافيه",
               code=f"CAF-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    enable_module_for_branch(db, fake_redis, "cafe", branch_id=None)
    return b


def make_item_committed(db, branch, available=True):
    from app.modules.cafe.models import CafeItem
    item = CafeItem(branch_id=branch.id, name="كابتشينو", price=Decimal("45.00"), is_available=available)
    db.add(item)
    db.commit()
    return item


class TestCafeOrderFlow:
    def test_create_order_via_http(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db, fake_redis)
        item = make_item_committed(db, branch)

        resp = client.post(
            "/api/v1/cafe/orders",
            json={
                "branch_id": branch.id, "order_type": "takeaway",
                "items": [{"item_id": item.id, "quantity": 2}],
            },
            headers=waiter_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "open"
        assert Decimal(str(body["subtotal"])) == Decimal("90.00")

    def test_order_status_progresses_to_paid(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db, fake_redis)
        item = make_item_committed(db, branch)
        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()

        resp = client.patch(
            f"/api/v1/cafe/orders/{order['id']}/status", json={"status": "paid"}, headers=waiter_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "paid"

    def test_create_order_rejects_unavailable_item(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db, fake_redis)
        item = make_item_committed(db, branch, available=False)
        resp = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        )
        assert resp.status_code == 400


class TestCafePermissions:
    def test_create_order_requires_waiter_level(self, client: TestClient, db, fake_redis):
        """customer-level token must not create cafe orders (waiter+ required)."""
        from tests.conftest import _create_test_user, _make_token
        branch = make_branch_committed(db, fake_redis)
        item = make_item_committed(db, branch)
        _create_test_user("cafe-customer@test.local", "customer")
        headers = {"Authorization": f"Bearer {_make_token('cafe-customer@test.local')}"}

        resp = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_create_item_requires_manager(self, client: TestClient, db, fake_redis, waiter_headers):
        """waiter (30) must not create cafe menu items (manager=60 required)."""
        branch = make_branch_committed(db, fake_redis)
        resp = client.post(
            "/api/v1/cafe/items",
            json={"branch_id": branch.id, "name": "شاي", "price": "20.00"},
            headers=waiter_headers,
        )
        assert resp.status_code == 403


class TestCafeValidation:
    def test_create_order_rejects_empty_items(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db, fake_redis)
        resp = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway", "items": []},
            headers=waiter_headers,
        )
        assert resp.status_code == 422

    def test_update_order_status_rejects_invalid_value(self, client: TestClient, db, fake_redis, waiter_headers):
        branch = make_branch_committed(db, fake_redis)
        item = make_item_committed(db, branch)
        order = client.post(
            "/api/v1/cafe/orders",
            json={"branch_id": branch.id, "order_type": "takeaway",
                  "items": [{"item_id": item.id, "quantity": 1}]},
            headers=waiter_headers,
        ).json()

        resp = client.patch(
            f"/api/v1/cafe/orders/{order['id']}/status", json={"status": "teleported"}, headers=waiter_headers,
        )
        assert resp.status_code == 422
