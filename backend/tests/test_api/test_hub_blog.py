"""tests/test_api/test_hub_blog.py"""
from __future__ import annotations
from tests.test_api.test_pms import make_branch


class TestBlogPost:

    def test_create_blog_post(self, db):
        from app.modules.hub.models import BlogPost
        from datetime import datetime
        branch = make_branch(db)
        post = BlogPost(
            branch_id=branch.id,
            title="استمتع بتجربة فريدة في البحر الأحمر",
            slug="enjoy-red-sea-experience",
            body="محتوى المقال التفصيلي...",
            status="published",
            author_id=1,
            published_at=datetime.now(),
        )
        db.add(post)
        db.commit()
        assert post.id is not None
        assert post.status == "published"

    def test_draft_vs_published(self, db):
        from app.modules.hub.models import BlogPost
        branch = make_branch(db)
        db.add(BlogPost(
            branch_id=branch.id, title="مسودة", slug="draft-1",
            body="...", status="draft", author_id=1,
        ))
        db.add(BlogPost(
            branch_id=branch.id, title="منشور", slug="published-1",
            body="...", status="published", author_id=1,
        ))
        db.commit()
        published = db.query(BlogPost).filter(
            BlogPost.branch_id == branch.id, BlogPost.status == "published"
        ).all()
        assert len(published) >= 1
        assert all(p.status == "published" for p in published)


class TestContactForm:

    def test_contact_creates_lead(self, db):
        from app.modules.hub.models import ContactForm
        from app.modules.crm.crud import create_lead

        branch = make_branch(db)
        form = ContactForm(
            branch_id=branch.id,
            full_name="زائر الموقع",
            phone="01055443322",
            email="visitor@test.com",
            subject="استفسار عن التايم شير",
            message="أريد معرفة المزيد...",
            source_page="/timeshare",
        )
        db.add(form)
        db.flush()

        lead = create_lead(db, {
            "branch_id": branch.id,
            "full_name": form.full_name,
            "phone": form.phone,
            "interest": "timeshare",
            "stage": "new",
            "notes": form.message,
        })
        form.lead_id = lead.id
        form.status = "converted"
        db.commit()

        assert form.lead_id == lead.id
        assert form.status == "converted"
