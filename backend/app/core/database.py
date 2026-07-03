"""
app/core/database.py
SQLAlchemy engine + session + Base — يستخدم app.core.kernel.database مباشرة

⚠️ get_db هنا هو app.core.kernel.database.get_db نفسه (نفس الـ callable) —
مش نسخة تانية. build_auth_router() (auth/2FA/logout) بيستخدم get_db بتاع
kernel داخلياً لأي AuthService session؛ لو عرّفنا get_db مستقل هنا، FastAPI
هيـ cache كل واحد في session منفصلة لنفس الـ request، فأي تعديل عالـ user
object (زي two_factor_secret في /2fa/setup) هيتعمله commit على session
مالهاش علاقة بالـ object، ويضيع بصمت. استخدم نفس الـ get_db في كل مكان.
"""
from app.core.kernel.database import Base, get_db, get_engine, init_db  # noqa: F401 — re-export
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

# تهيئة engine عند import
init_db(settings.DATABASE_URL)

# لاستخدام scripts/seed.py خارج الـ request cycle فقط — الـ FastAPI dependency
# الفعلي دايماً get_db المستورد فوق.
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=get_engine(),
)
