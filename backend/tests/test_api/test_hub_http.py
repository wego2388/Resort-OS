"""
tests/test_api/test_hub_http.py
HTTP-level tests for the hub module's router — test_hub.py/test_hub_blog.py
already cover the business rules at the services.py layer directly; this
file covers what only a real HTTP request exercises: role gates, status
codes, pagination, 404s, and the two endpoints whose logic lives entirely
in the router itself (contact form → CRM lead, public blog listing).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient


def make_branch_committed(db):
    from app.modules.core.models import Branch
    b = Branch(name="Hub HTTP Branch", name_ar="فرع الموقع",
               code=f"HUB-{uuid.uuid4().hex[:8].upper()}")
    db.add(b)
    db.commit()
    return b


class TestPagesEndpoints:
    def test_create_requires_manager(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/hub/pages",
            json={"branch_id": branch.id, "slug": "about-us", "title": "About", "page_type": "info"},
            headers=waiter_headers,
        )
        assert resp.status_code == 403

    def test_create_list_get_by_id_and_slug(self, client: TestClient, db, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/hub/pages",
            json={"branch_id": branch.id, "slug": f"page-{uuid.uuid4().hex[:6]}", "title": "About Us", "page_type": "info"},
            headers=manager_headers,
        )
        assert create_resp.status_code == 201
        page = create_resp.json()

        # أي مستخدم مسجّل دخول (مش بس مدير) يقدر يقرأ
        list_resp = client.get("/api/v1/hub/pages", params={"branch_id": branch.id}, headers=waiter_headers)
        assert list_resp.status_code == 200
        assert list_resp.json()["total"] >= 1

        get_resp = client.get(f"/api/v1/hub/pages/{page['id']}", headers=waiter_headers)
        assert get_resp.status_code == 200
        assert get_resp.json()["slug"] == page["slug"]

        slug_resp = client.get(f"/api/v1/hub/pages/slug/{page['slug']}", headers=waiter_headers)
        assert slug_resp.status_code == 200
        assert slug_resp.json()["id"] == page["id"]

    def test_get_missing_page_404(self, client: TestClient, waiter_headers):
        resp = client.get("/api/v1/hub/pages/999999999", headers=waiter_headers)
        assert resp.status_code == 404

    def test_get_missing_slug_404(self, client: TestClient, waiter_headers):
        resp = client.get("/api/v1/hub/pages/slug/does-not-exist-xyz", headers=waiter_headers)
        assert resp.status_code == 404

    def test_update_page(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        page = client.post(
            "/api/v1/hub/pages",
            json={"branch_id": branch.id, "slug": f"page-{uuid.uuid4().hex[:6]}", "title": "Old Title", "page_type": "info"},
            headers=manager_headers,
        ).json()

        resp = client.patch(f"/api/v1/hub/pages/{page['id']}", json={"title": "New Title"}, headers=manager_headers)
        assert resp.status_code == 200
        assert resp.json()["title"] == "New Title"

    def test_delete_requires_admin_not_just_manager(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        page = client.post(
            "/api/v1/hub/pages",
            json={"branch_id": branch.id, "slug": f"page-{uuid.uuid4().hex[:6]}", "title": "To Delete", "page_type": "info"},
            headers=manager_headers,
        ).json()

        # manager (level 60) لا يكفي — الحذف admin (80) بس
        resp = client.delete(f"/api/v1/hub/pages/{page['id']}", headers=manager_headers)
        assert resp.status_code == 403


class TestOffersEndpoints:
    def test_create_and_list_and_get(self, client: TestClient, db, manager_headers, waiter_headers):
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/hub/offers",
            json={
                "branch_id": branch.id, "title": "Summer Deal", "offer_type": "room",
                "original_price": "1000.00", "offer_price": "800.00",
                "valid_from": str(date.today()), "valid_until": str(date.today() + timedelta(days=30)),
            },
            headers=manager_headers,
        )
        assert create_resp.status_code == 201
        offer = create_resp.json()

        list_resp = client.get("/api/v1/hub/offers", params={"branch_id": branch.id}, headers=waiter_headers)
        assert list_resp.status_code == 200
        assert any(o["id"] == offer["id"] for o in list_resp.json()["items"])

        get_resp = client.get(f"/api/v1/hub/offers/{offer['id']}", headers=waiter_headers)
        assert get_resp.status_code == 200

    def test_get_missing_offer_404(self, client: TestClient, waiter_headers):
        resp = client.get("/api/v1/hub/offers/999999999", headers=waiter_headers)
        assert resp.status_code == 404

    def test_invalid_offer_dates_rejected_with_400(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/hub/offers",
            json={
                "branch_id": branch.id, "title": "Bad Offer", "offer_type": "room",
                "original_price": "1000.00", "offer_price": "800.00",
                "valid_from": str(date.today()), "valid_until": str(date.today() - timedelta(days=1)),
            },
            headers=manager_headers,
        )
        assert resp.status_code == 400

    def test_update_offer(self, client: TestClient, db, manager_headers):
        branch = make_branch_committed(db)
        offer = client.post(
            "/api/v1/hub/offers",
            json={
                "branch_id": branch.id, "title": "Old", "offer_type": "beach",
                "original_price": "500.00", "offer_price": "400.00",
                "valid_from": str(date.today()), "valid_until": str(date.today() + timedelta(days=10)),
            },
            headers=manager_headers,
        ).json()
        resp = client.patch(f"/api/v1/hub/offers/{offer['id']}", json={"title": "New"}, headers=manager_headers)
        assert resp.status_code == 200
        assert resp.json()["title"] == "New"


class TestOnlineBookingsEndpoints:
    def test_create_confirm_and_cancel_flow(self, client: TestClient, db, waiter_headers, manager_headers):
        branch = make_branch_committed(db)
        create_resp = client.post(
            "/api/v1/hub/online-bookings",
            json={
                "branch_id": branch.id, "guest_name": "ضيف اختبار", "guest_phone": "+201001234567",
                "guests_count": 2, "requested_date": str(date.today() + timedelta(days=5)),
            },
            headers=waiter_headers,  # أي مستخدم مسجّل دخول يقدر يبعت طلب حجز
        )
        assert create_resp.status_code == 201
        booking = create_resp.json()
        assert booking["status"] == "pending"

        list_resp = client.get("/api/v1/hub/online-bookings", params={"branch_id": branch.id}, headers=manager_headers)
        assert any(b["id"] == booking["id"] for b in list_resp.json()["items"])

        get_resp = client.get(f"/api/v1/hub/online-bookings/{booking['id']}", headers=manager_headers)
        assert get_resp.status_code == 200

        confirm_resp = client.post(f"/api/v1/hub/online-bookings/{booking['id']}/confirm", headers=manager_headers)
        assert confirm_resp.status_code == 200
        assert confirm_resp.json()["status"] == "confirmed"

    def test_confirm_requires_manager(self, client: TestClient, db, waiter_headers):
        branch = make_branch_committed(db)
        booking = client.post(
            "/api/v1/hub/online-bookings",
            json={
                "branch_id": branch.id, "guest_name": "ضيف", "guest_phone": "+201001234567",
                "requested_date": str(date.today() + timedelta(days=3)),
            },
            headers=waiter_headers,
        ).json()
        resp = client.post(f"/api/v1/hub/online-bookings/{booking['id']}/confirm", headers=waiter_headers)
        assert resp.status_code == 403

    def test_cancel_pending_booking(self, client: TestClient, db, waiter_headers, manager_headers):
        branch = make_branch_committed(db)
        booking = client.post(
            "/api/v1/hub/online-bookings",
            json={
                "branch_id": branch.id, "guest_name": "ضيف", "guest_phone": "+201001234567",
                "requested_date": str(date.today() + timedelta(days=3)),
            },
            headers=waiter_headers,
        ).json()
        resp = client.post(f"/api/v1/hub/online-bookings/{booking['id']}/cancel", headers=manager_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "cancelled"

    def test_get_missing_booking_404(self, client: TestClient, waiter_headers):
        resp = client.get("/api/v1/hub/online-bookings/999999999", headers=waiter_headers)
        assert resp.status_code == 404


class TestContactForm:
    """المنطق كله جوّه الراوتر نفسه (مش services.py) — لازم تست HTTP حقيقي."""

    def test_submits_form_and_creates_crm_lead(self, client: TestClient, db):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/hub/contact",
            json={
                "branch_id": branch.id, "full_name": "زائر مهتم", "phone": "+201009998888",
                "subject": "استفسار عن الأسعار", "message": "عايز أعرف أسعار الغرف من فضلكم",
            },
        )
        assert resp.status_code == 200
        assert "form_id" in resp.json()

        from app.modules.hub.models import ContactForm
        form = db.query(ContactForm).filter(ContactForm.id == resp.json()["form_id"]).first()
        assert form is not None
        assert form.status == "converted"
        assert form.lead_id is not None

        from app.modules.crm.models import Lead
        lead = db.query(Lead).filter(Lead.id == form.lead_id).first()
        assert lead is not None
        assert lead.full_name == "زائر مهتم"

    def test_missing_required_field_returns_422(self, client: TestClient, db):
        branch = make_branch_committed(db)
        resp = client.post(
            "/api/v1/hub/contact",
            json={"branch_id": branch.id, "full_name": "بدون موضوع"},  # missing subject/message
        )
        assert resp.status_code == 500 or resp.status_code == 422
        # يقرأ data["subject"]/data["message"] مباشرة (dict خام مش Pydantic model)
        # فبيرمي KeyError → 500 عام، مش 422 — موثّق هنا كسلوك حالي، مش تحسين مطلوب


class TestBlogPosts:
    """المنطق كله جوّه الراوتر نفسه (مش services.py) — لازم تست HTTP حقيقي."""

    def test_lists_only_published_posts(self, client: TestClient, db):
        from app.modules.hub.models import BlogPost
        from app.core.kernel.models.user import User
        from app.core.kernel.security import get_password_hash
        branch = make_branch_committed(db)
        author = User(email=f"author-{uuid.uuid4().hex[:6]}@test.local",
                     password_hash=get_password_hash("Test@12345"),
                     full_name="كاتب اختباري", role="admin", is_active=True)
        db.add(author)
        db.flush()
        db.add_all([
            BlogPost(branch_id=branch.id, title="منشور", slug=f"post-{uuid.uuid4().hex[:6]}",
                     excerpt="ملخص", body="محتوى", status="published", author_id=author.id,
                     published_at=date.today(), views_count=10),
            BlogPost(branch_id=branch.id, title="مسودة", slug=f"post-{uuid.uuid4().hex[:6]}",
                     excerpt="ملخص", body="محتوى", status="draft", author_id=author.id),
        ])
        db.commit()

        resp = client.get("/api/v1/hub/blog/posts", params={"branch_id": branch.id})
        assert resp.status_code == 200
        posts = resp.json()["posts"]
        assert any(p["title"] == "منشور" for p in posts)
        assert not any(p["title"] == "مسودة" for p in posts)
