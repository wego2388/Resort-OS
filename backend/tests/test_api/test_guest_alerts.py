"""
tests/test_api/test_guest_alerts.py
HTTP-level tests for the guest-alerts feature — a guest-initiated,
unauthenticated staff-alert channel ("call waiter" / "request bill") with
live WebSocket delivery to staff. No auth needed for the create call
(mirrors tests/test_api/test_cafe_public_orders.py's public-endpoint
pattern); the staff list/resolve endpoints are role-gated (get_waiter_user).

راجع app/modules/core/models.py::GuestAlert للشرح الكامل عن التصميم (generic
context_type/context_id بدون FK، الفرق بين restaurant_table وcafe_table).
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.conftest import ws_url


def make_branch(db):
    from app.modules.core.models import Branch
    b = Branch(name="Guest Alert Branch", name_ar="فرع اختبار التنبيهات",
               code=f"ALERT-{uuid.uuid4().hex[:6].upper()}")
    db.add(b)
    db.commit()
    return b


class TestCreateGuestAlertPublic:
    def test_create_call_waiter_alert_no_auth(self, client: TestClient, db):
        branch = make_branch(db)
        resp = client.post("/api/v1/public/alerts", json={
            "branch_id": branch.id,
            "context_type": "restaurant_table",
            "context_id": 5,
            "alert_type": "call_waiter",
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["alert_id"] > 0
        assert data["status"] == "open"
        assert data["message"]

    def test_create_request_bill_alert_gets_bill_specific_message(self, client: TestClient, db):
        branch = make_branch(db)
        resp = client.post("/api/v1/public/alerts", json={
            "branch_id": branch.id,
            "context_type": "cafe_table",
            "context_id": 12,
            "alert_type": "request_bill",
            "message": "الحساب من فضلكم",
        })
        assert resp.status_code == 201, resp.text
        assert "الفاتورة" in resp.json()["message"]

    def test_create_alert_rejects_unknown_alert_type(self, client: TestClient, db):
        branch = make_branch(db)
        resp = client.post("/api/v1/public/alerts", json={
            "branch_id": branch.id,
            "context_type": "restaurant_table",
            "context_id": 1,
            "alert_type": "not_a_real_type",
        })
        assert resp.status_code == 422

    def test_create_alert_rejects_unknown_context_type(self, client: TestClient, db):
        branch = make_branch(db)
        resp = client.post("/api/v1/public/alerts", json={
            "branch_id": branch.id,
            "context_type": "spaceship",
            "context_id": 1,
            "alert_type": "call_waiter",
        })
        assert resp.status_code == 422

    def test_create_alert_rejects_missing_branch(self, client: TestClient, db):
        resp = client.post("/api/v1/public/alerts", json={
            "branch_id": 999999999,
            "context_type": "restaurant_table",
            "context_id": 1,
            "alert_type": "call_waiter",
        })
        assert resp.status_code == 400


class TestStaffAlertsFeed:
    def test_list_alerts_requires_auth(self, client: TestClient, db):
        branch = make_branch(db)
        resp = client.get("/api/v1/alerts", params={"branch_id": branch.id})
        assert resp.status_code == 401

    def test_list_alerts_returns_created_open_alert(self, client: TestClient, db, waiter_headers):
        branch = make_branch(db)
        client.post("/api/v1/public/alerts", json={
            "branch_id": branch.id,
            "context_type": "restaurant_table",
            "context_id": 3,
            "alert_type": "call_waiter",
        })

        resp = client.get("/api/v1/alerts", params={"branch_id": branch.id}, headers=waiter_headers)
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["status"] == "open"
        assert items[0]["context_type"] == "restaurant_table"
        assert items[0]["context_id"] == 3

    def test_resolve_alert_requires_auth(self, client: TestClient, db):
        branch = make_branch(db)
        create_resp = client.post("/api/v1/public/alerts", json={
            "branch_id": branch.id,
            "context_type": "cafe_table",
            "context_id": 2,
            "alert_type": "request_bill",
        })
        alert_id = create_resp.json()["alert_id"]

        resp = client.patch(f"/api/v1/alerts/{alert_id}/status", json={"status": "resolved"})
        assert resp.status_code == 401

    def test_acknowledge_then_resolve_alert(self, client: TestClient, db, waiter_headers):
        branch = make_branch(db)
        create_resp = client.post("/api/v1/public/alerts", json={
            "branch_id": branch.id,
            "context_type": "cafe_table",
            "context_id": 7,
            "alert_type": "call_waiter",
        })
        alert_id = create_resp.json()["alert_id"]

        ack_resp = client.patch(
            f"/api/v1/alerts/{alert_id}/status", json={"status": "acknowledged"}, headers=waiter_headers,
        )
        assert ack_resp.status_code == 200, ack_resp.text
        assert ack_resp.json()["status"] == "acknowledged"
        assert ack_resp.json()["resolved_at"] is None

        # لسه فاضل في الفيد (acknowledged مش resolved)
        list_resp = client.get("/api/v1/alerts", params={"branch_id": branch.id}, headers=waiter_headers)
        assert any(a["id"] == alert_id for a in list_resp.json()["items"])

        resolve_resp = client.patch(
            f"/api/v1/alerts/{alert_id}/status", json={"status": "resolved"}, headers=waiter_headers,
        )
        assert resolve_resp.status_code == 200, resolve_resp.text
        body = resolve_resp.json()
        assert body["status"] == "resolved"
        assert body["resolved_at"] is not None
        assert body["resolved_by"] is not None

        # اتشال من الفيد بعد ما اتقفل
        list_resp2 = client.get("/api/v1/alerts", params={"branch_id": branch.id}, headers=waiter_headers)
        assert not any(a["id"] == alert_id for a in list_resp2.json()["items"])

    def test_resolve_already_resolved_alert_rejected(self, client: TestClient, db, waiter_headers):
        branch = make_branch(db)
        create_resp = client.post("/api/v1/public/alerts", json={
            "branch_id": branch.id,
            "context_type": "restaurant_table",
            "context_id": 9,
            "alert_type": "other",
            "message": "محتاج كرسي إضافي",
        })
        alert_id = create_resp.json()["alert_id"]

        first = client.patch(f"/api/v1/alerts/{alert_id}/status", json={"status": "resolved"}, headers=waiter_headers)
        assert first.status_code == 200

        second = client.patch(f"/api/v1/alerts/{alert_id}/status", json={"status": "resolved"}, headers=waiter_headers)
        assert second.status_code == 400

    def test_resolve_missing_alert_404_equivalent_400(self, client: TestClient, db, waiter_headers):
        resp = client.patch("/api/v1/alerts/999999999/status", json={"status": "resolved"}, headers=waiter_headers)
        assert resp.status_code == 400


class TestGuestAlertsWebSocket:
    def test_websocket_client_receives_new_alert_broadcast(self, client: TestClient, db, waiter_headers):
        """يتأكد إن اتصال WebSocket حقيقي بيستلم فعليًا التنبيه الجديد لحظة
        إنشائه — نفس فكرة test_kds_websocket_client_actually_receives_broadcast_message
        في المطعم (مش بس mock للـ broadcast، اتصال حقيقي)."""
        branch = make_branch(db)

        with client.websocket_connect(ws_url(f"/api/v1/ws/alerts/{branch.id}", waiter_headers)) as ws:
            create_resp = client.post("/api/v1/public/alerts", json={
                "branch_id": branch.id,
                "context_type": "restaurant_table",
                "context_id": 4,
                "alert_type": "call_waiter",
            })
            assert create_resp.status_code == 201, create_resp.text

            message = ws.receive_json()
            assert message["type"] == "new_alert"
            assert message["alert"]["context_id"] == 4
            assert message["alert"]["alert_type"] == "call_waiter"
            assert message["alert"]["status"] == "open"

    def test_websocket_receives_status_change_broadcast(self, client: TestClient, db, waiter_headers):
        branch = make_branch(db)
        create_resp = client.post("/api/v1/public/alerts", json={
            "branch_id": branch.id,
            "context_type": "cafe_table",
            "context_id": 6,
            "alert_type": "request_bill",
        })
        alert_id = create_resp.json()["alert_id"]

        with client.websocket_connect(ws_url(f"/api/v1/ws/alerts/{branch.id}", waiter_headers)) as ws:
            resp = client.patch(
                f"/api/v1/alerts/{alert_id}/status", json={"status": "acknowledged"}, headers=waiter_headers,
            )
            assert resp.status_code == 200, resp.text

            message = ws.receive_json()
            assert message["type"] == "alert_status_changed"
            assert message["alert"]["id"] == alert_id
            assert message["alert"]["status"] == "acknowledged"

    def test_websocket_rejects_connection_without_token(self, client: TestClient, db):
        """wagdy.md A-01: كل WebSocket في المشروع كان بيتقبل من غير أي تحقق
        هوية خالص. get_websocket_user (app/core/deps.py) بيقفل الاتصال بـ
        code 4401 لو مفيش ?token= صالح — هنا بنتأكد إن ده بيحصل فعليًا على
        اتصال حقيقي، مش بس قراءة كود."""
        from starlette.websockets import WebSocketDisconnect
        branch = make_branch(db)

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/api/v1/ws/alerts/{branch.id}"):
                pass
        assert exc_info.value.code == 4401

    def test_websocket_rejects_invalid_token(self, client: TestClient, db):
        from starlette.websockets import WebSocketDisconnect
        branch = make_branch(db)

        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/api/v1/ws/alerts/{branch.id}?token=garbage-not-a-real-jwt"):
                pass
        assert exc_info.value.code == 4401
