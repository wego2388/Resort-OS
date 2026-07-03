"""
tests/test_kernel_errors.py
Regression test for a real production bug found 2026-07-03: SecureErrorMiddleware
crashed on genuine, unhandled SQLAlchemy errors whose string representation
contains literal curly braces — which is the normal case for SQLAlchemy's
own `[SQL: ...] [parameters: {...}]` error formatting. The middleware used
`logger.error(f"...: {exc}", exc_info=True)` — loguru applies `.format()` to
the final message using `exc_info` as a kwarg, and any literal `{...}` left
over in the (already f-string-interpolated) text gets re-parsed as a format
field, raising a KeyError from inside the error handler itself. This meant
*every* unhandled DB error produced a raw, unhandled crash instead of the
intended clean JSON 500 response — discovered when a real NOT NULL
violation on POST /hub/contact returned a bare "Internal Server Error"
instead of the expected `{"success": false, "error_code": "database_error", ...}`
body.

Fix: use loguru's own template + positional-args form (`logger.opt(exception=True)
.error("... {} ...", request.url.path, exc)`) so `.format()` only touches the
literal template's own placeholders, never the dynamic exception text.
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.core.kernel.errors import SecureErrorMiddleware, setup_error_handlers


def _make_test_app(exc: Exception) -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecureErrorMiddleware)

    @app.get("/boom")
    def boom():
        raise exc

    return app


class TestSecureErrorMiddlewareBraceSafety:
    def test_sqlalchemy_error_with_braces_in_message_returns_clean_500(self):
        """Mirrors a real SQLAlchemy error's actual shape: `[parameters: {...}]`
        dict-repr embedded in the exception's own string representation."""
        exc = SQLAlchemyError(
            "(psycopg.errors.NotNullViolation) null value in column \"created_at\" "
            "violates not-null constraint\n"
            "[parameters: {'branch_id': 1, 'full_name': 'ضيف اختبار', 'status': 'new'}]"
        )
        app = _make_test_app(exc)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/boom")
        assert resp.status_code == 500
        body = resp.json()
        assert body["success"] is False
        assert body["error_code"] == "database_error"

    def test_generic_exception_with_braces_in_message_returns_clean_500(self):
        """Same class of bug, generic-Exception branch (logger.critical path)."""
        exc = RuntimeError("something failed with a dict-like message: {'foo': 'bar', 'nested': {'x': 1}}")
        app = _make_test_app(exc)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/boom")
        assert resp.status_code == 500
        body = resp.json()
        assert body["success"] is False
        assert body["error_code"] == "internal_error"
        assert "ref" in body["message"]

    def test_sqlalchemy_error_without_braces_still_returns_clean_500(self):
        """Sanity check — the common/simple case must keep working too."""
        exc = SQLAlchemyError("connection refused")
        app = _make_test_app(exc)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/boom")
        assert resp.status_code == 500
        assert resp.json()["error_code"] == "database_error"


class TestNotFoundHandlerPreservesRealMessages:
    """Regression test for a real production bug found 2026-07-03 (QA pass):
    the global `@app.exception_handler(404)` in setup_error_handlers()
    unconditionally replaced *every* 404's message with a generic
    "Path not found: {path}" string — including ones deliberately raised by
    route code via `raise HTTPException(404, "some specific reason")`
    (e.g. "Employee not found", "Booking not found" across the whole
    project). Discovered live via GET /hr/me/profile for a user with no
    linked Employee row: instead of the real
    "لا يوجد ملف موظف مرتبط بحسابك" message, the client only ever saw
    "Path not found: /api/v1/hr/me/profile" — indistinguishable from a typo'd
    URL. Fix: only fall back to the generic message when Starlette's own
    unmatched-route exception is the source (`detail` defaults to the literal
    string "Not Found" in that case and only that case)."""

    def _make_app(self) -> FastAPI:
        app = FastAPI()
        setup_error_handlers(app)

        @app.get("/employees/{employee_id}")
        def get_employee(employee_id: int):
            raise HTTPException(404, "Employee not found")

        return app

    def test_explicit_http_exception_message_is_preserved(self):
        app = self._make_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/employees/999")
        assert resp.status_code == 404
        body = resp.json()
        assert body["message"] == "Employee not found"

    def test_unmatched_route_still_gets_generic_path_not_found(self):
        app = self._make_app()
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/this-route-does-not-exist-at-all")
        assert resp.status_code == 404
        body = resp.json()
        assert "Path not found" in body["message"]
        assert "/this-route-does-not-exist-at-all" in body["message"]
