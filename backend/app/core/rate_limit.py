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

import ipaddress

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.kernel.cache import rate_limit


def _client_ip(request: Request) -> str:
    """المفتاح الحقيقي اللي rate_limit() بيتحدد بيه — لازم يبقى موثوق.

    **تصحيح أمني (Codex security review، 2026-07-17):** النسخة القديمة
    كانت بتثق في أول قيمة (leftmost) في X-Forwarded-For بلا أي تحقق —
    القيمة دي بتوصل زي ما هي من العميل نفسه من غير تعديل عبر edge nginx
    وfrontend nginx (الاتنين بيستخدموا $proxy_add_x_forwarded_for، اللي
    بيضيف على القيمة الجاية مش يستبدلها — راجع deploy/nginx/edge.conf
    وfrontend/nginx.spa.conf). يعني أي عميل كان يقدر يزوّر مفتاح الحد في
    Redis ويهرب من أي rate limit فعليًا.

    الحل: settings.RATE_LIMIT_TRUSTED_PROXY_HOPS (افتراضي 0 = تجاهل
    X-Forwarded-For كليًا، استخدم request.client.host مباشرة — آمن محليًا
    وبدون reverse proxy). لو N>0، ناخد القيمة رقم N من اليمين (آخر N قيمة
    اتضافت فعليًا من الـN من الـreverse proxies الموثوقين، مش أول قيمة
    من الشمال اللي العميل بيتحكم فيها بالكامل)، ونتحقق إنها IP صالح.
    سلسلة قصيرة/ناقصة أو IP مش صالح = fail-closed لـrequest.client.host،
    مش قبول أي حاجة."""
    direct_peer = request.client.host if request.client else "unknown"

    trusted_hops = settings.RATE_LIMIT_TRUSTED_PROXY_HOPS
    if trusted_hops <= 0:
        return direct_peer

    forwarded = request.headers.get("x-forwarded-for")
    if not forwarded:
        return direct_peer

    chain = [part.strip() for part in forwarded.split(",") if part.strip()]
    if len(chain) < trusted_hops:
        return direct_peer

    candidate = chain[-trusted_hops]
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return direct_peer

    return candidate


# (method, path) → (bucket_prefix, max_requests, window_seconds)
#
# ⚠️ باج حقيقي اتصلح (2026-07-07، اتكشف أثناء بناء guest alerts): المطابقة
# هنا exact string match على request.url.path — يعني أي endpoint فيه path
# parameter (زي .../orders/{order_id} أو .../reservations/{id}/public) مش
# ممكن يتحدد هنا خالص مهما ضفنا؛ محتاج تحديث تصميم الـ middleware نفسه
# (regex/prefix matching) لو عايزين نحميهم — خارج نطاق هذا الإصلاح البسيط.
#
# ⚠️ باج تاني اتصلح (2026-07-17، Gate 1 containment): الـ4 مسارات القديمة
# restaurant/cafe اتحذفت بالكامل من الكود يوم 2026-07-13 (dining cutover)
# بس فضلت مسجّلة هنا كخريطة ميتة، بينما مسارات dining/public/* الجديدة
# (اللي حلّت محلهم فعليًا) عمرها ما اتسجّلت هنا — يعني /dining/public/orders
# (اللي بيقدر ينشئ طلب حقيقي) كان بدون أي حد أقصى فعلي خالص من يوم الـcutover.
_LIMITED_ROUTES: dict[tuple[str, str], tuple[str, int, int]] = {
    ("POST", "/api/v1/auth/login"):    ("login", settings.LOGIN_RATE_LIMIT_MAX, settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS),
    ("POST", "/api/v1/auth/register"): ("login", settings.LOGIN_RATE_LIMIT_MAX, settings.LOGIN_RATE_LIMIT_WINDOW_SECONDS),
    ("POST", "/api/v1/hub/contact"):   ("public", 30, 60),
    ("GET",  "/api/v1/hub/blog/posts"): ("public", 30, 60),
    ("GET",  "/api/v1/pms/public/room-types"): ("public", 30, 60),
    ("GET",  "/api/v1/dining/public/outlets"): ("public", 30, 60),
    ("GET",  "/api/v1/dining/public/menu"): ("public", 30, 60),
    ("POST", "/api/v1/dining/public/orders"): ("public", 30, 60),
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
