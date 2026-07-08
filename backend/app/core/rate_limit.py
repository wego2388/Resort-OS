"""
app/core/rate_limit.py
IP-keyed rate limiting middleware for unauthenticated / abuse-prone routes.

Per 08-SECURITY.md:
    login:{ip}        settings.LOGIN_RATE_LIMIT_MAX / LOGIN_RATE_LIMIT_WINDOW_SECONDS
                       (5/300s production default — راجع app.core.config.Settings)
    public:{ip}       30  / 60s

⚠️ login threshold بقى قابل للتعديل عبر .env (LOGIN_RATE_LIMIT_MAX/
LOGIN_RATE_LIMIT_WINDOW_SECONDS) — القيمة الافتراضية (5/300) هي المعتمدة
أمنيًا وما اتغيّرش، بس بيئة تطوير محلية ممكن ترفعها لراحة اختبار حسابات
تجريبية كتير بسرعة من غير ما تتقفل. لا تغيّر الافتراضي نفسه، غيّر .env بس.

Resource-keyed limits (otp:{user_id}, payment:{user_id}, eta:{branch_id}) are
applied as FastAPI dependencies at their own endpoints instead, since they
need a value rate_limit can only get from the authenticated user / request
body — not from the connection alone. See app.core.deps.rate_limit_dep().
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.kernel.cache import rate_limit


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# (method, path) → (bucket_prefix, max_requests, window_seconds)
#
# ⚠️ باج حقيقي اتصلح (2026-07-07، اتكشف أثناء بناء guest alerts): المطابقة
# هنا exact string match على request.url.path — يعني أي endpoint فيه path
# parameter (زي .../orders/{order_id} أو .../reservations/{id}/public) مش
# ممكن يتحدد هنا خالص مهما ضفنا؛ محتاج تحديث تصميم الـ middleware نفسه
# (regex/prefix matching) لو عايزين نحميهم — خارج نطاق هذا الإصلاح البسيط.
# اللي اتصلح دلوقتي: 3 endpoints بدون path parameters كانت موثّقة في
# تعليقات الكود على إنها "rate limited بالـ middleware" بس عمرها ما كانت
# مسجّلة هنا فعليًا — يعني طلب/قائمة المطعم والكافيه كانت غير محمية تمامًا
# من الإسبام (لا حد أقصى للطلبات من نفس الـ IP خالص).
_LIMITED_ROUTES: dict[tuple[str, str], tuple[str, int, int]] = {
    ("POST", "/api/v1/auth/login"):    ("login", settings.LOGIN_RATE_LIMIT_MAX, settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS),
    ("POST", "/api/v1/auth/register"): ("login", settings.LOGIN_RATE_LIMIT_MAX, settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS),
    ("POST", "/api/v1/hub/contact"):   ("public", 30, 60),
    ("GET",  "/api/v1/hub/blog/posts"): ("public", 30, 60),
    ("GET",  "/api/v1/pms/public/room-types"): ("public", 30, 60),
    ("GET",  "/api/v1/cafe/public/menu"): ("public", 30, 60),
    ("GET",  "/api/v1/restaurant/public/menu"): ("public", 30, 60),
    ("POST", "/api/v1/restaurant/public/orders"): ("public", 30, 60),
    ("POST", "/api/v1/cafe/public/orders"): ("public", 30, 60),
    # Guest alerts (نادِ الجرسون / هات الفاتورة) — أضيق شوية من التصفح العادي
    # (20 مش 30) لأنه فعل تنبيه فوري لطاقم الخدمة، مش قراءة قائمة.
    ("POST", "/api/v1/public/alerts"): ("public", 20, 60),
}


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        route_key = (request.method, request.url.path)
        limit = _LIMITED_ROUTES.get(route_key)
        if limit:
            prefix, max_requests, window = limit
            ip = _client_ip(request)
            if not rate_limit(f"{prefix}:{ip}", max_requests=max_requests, window_seconds=window):
                return JSONResponse(
                    status_code=429,
                    content={
                        "code": "rate_limit_exceeded",
                        "message": "محاولات كثيرة جداً — حاول لاحقاً",
                    },
                )
        return await call_next(request)
