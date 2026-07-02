# Resort OS — Makefile
# الاستخدام: make <command>

.PHONY: help up down dev migrate seed shell test lint

BACKEND_DIR = backend
# ⚠️ بدون $(BACKEND_DIR)/ بادئة — كل استخدام بييجي بعد "cd $(BACKEND_DIR) &&"،
# فلو الـ path هنا فيه backend/ كمان بيبقى المسار الفعلي backend/backend/...
PYTHON      = .venv/bin/python
UVICORN     = .venv/bin/uvicorn
ALEMBIC     = .venv/bin/alembic
PYTEST      = .venv/bin/pytest

help:  ## عرض كل الأوامر
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

# ── Infrastructure ────────────────────────────────────────────────────────────

up:  ## تشغيل Docker (DB + Redis)
	docker compose up -d
	@echo "⏳ Waiting for DB..."
	@sleep 3
	@echo "✅ Infrastructure ready"

down:  ## إيقاف Docker
	docker compose down

# ── Development ───────────────────────────────────────────────────────────────

install:  ## تثبيت dependencies في venv
	cd $(BACKEND_DIR) && python3 -m venv .venv
	cd $(BACKEND_DIR) && .venv/bin/pip install -q --upgrade pip
	cd $(BACKEND_DIR) && .venv/bin/pip install -r requirements.txt
	@echo "✅ Dependencies installed"

dev:  ## تشغيل backend في development
	cd $(BACKEND_DIR) && $(UVICORN) app.main:app --host 0.0.0.0 --port 8005 --reload

worker:  ## تشغيل Celery worker
	cd $(BACKEND_DIR) && .venv/bin/celery -A app.celery_app worker --loglevel=info --concurrency=4

beat:  ## تشغيل Celery beat (scheduled tasks)
	cd $(BACKEND_DIR) && .venv/bin/celery -A app.celery_app beat --loglevel=info

# ── Database ──────────────────────────────────────────────────────────────────

migrate:  ## تطبيق كل الـ migrations
	cd $(BACKEND_DIR) && $(ALEMBIC) upgrade head

migration:  ## إنشاء migration جديد — NAME="وصف"
	cd $(BACKEND_DIR) && $(ALEMBIC) revision --autogenerate -m "$(NAME)"

downgrade:  ## rollback خطوة واحدة
	cd $(BACKEND_DIR) && $(ALEMBIC) downgrade -1

seed:  ## إدخال البيانات الأولية
	cd $(BACKEND_DIR) && $(PYTHON) -m app.seed

seed-reset:  ## مسح وإعادة seed (dev فقط)
	cd $(BACKEND_DIR) && $(PYTHON) -m app.seed --reset

# ── Testing ───────────────────────────────────────────────────────────────────

test:  ## تشغيل كل الاختبارات
	cd $(BACKEND_DIR) && $(PYTEST) tests/ --tb=short -q

test-engines:  ## Engine tests فقط (سريع — بدون DB)
	cd $(BACKEND_DIR) && $(PYTEST) tests/test_engines/ -v

test-cov:  ## اختبارات مع coverage report
	cd $(BACKEND_DIR) && $(PYTEST) tests/ --cov=app --cov-report=term-missing -q

# ── Utilities ─────────────────────────────────────────────────────────────────

shell:  ## Python shell مع app context
	cd $(BACKEND_DIR) && $(PYTHON) -c "from app.core.database import SessionLocal; db = SessionLocal(); print('DB ready. Use: db')" -i

health:  ## تحقق من صحة الـ API
	@curl -s http://localhost:8005/health | python3 -m json.tool

lint:  ## فحص الكود
	cd $(BACKEND_DIR) && .venv/bin/ruff check app/ tests/

format:  ## تنسيق الكود
	cd $(BACKEND_DIR) && .venv/bin/ruff format app/ tests/

# ── Production ────────────────────────────────────────────────────────────────

prod-migrate:  ## migrations في production
	cd $(BACKEND_DIR) && $(ALEMBIC) upgrade head && echo "✅ Migrations applied"

prod-start:  ## تشغيل في production بـ gunicorn
	cd $(BACKEND_DIR) && .venv/bin/gunicorn app.main:app \
		-w 4 -k uvicorn.workers.UvicornWorker \
		--bind 0.0.0.0:8005 \
		--access-logfile - \
		--error-logfile -
