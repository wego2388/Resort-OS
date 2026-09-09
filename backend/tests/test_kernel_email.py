"""
tests/test_kernel_email.py
نفس نمط test_kernel_whatsapp.py بالظبط (SEC-13 fail-closed policy) —
send_email لازم يرجع False + ERROR واضح في أي بيئة غير dev/test لو
SMTP_HOST/SMTP_USER/SMTP_PASSWORD مش مُعدّين، بدل ما يصدّق caller (تنبيه
حجز/استفسار جديد) إن الإيميل اتبعت فعليًا وهو راح للفراغ بصمت.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.core.kernel import email as email_module


class TestSendEmailEnvironmentAwareness:
    def test_production_unconfigured_returns_false_not_true(self, monkeypatch):
        fake_settings = MagicMock()
        fake_settings.ENVIRONMENT = "production"
        monkeypatch.setattr("app.core.config.settings", fake_settings)
        monkeypatch.delenv("SMTP_HOST", raising=False)
        monkeypatch.delenv("SMTP_USER", raising=False)
        monkeypatch.delenv("SMTP_PASSWORD", raising=False)

        result = email_module.send_email("reservation@elkheima.com", "subject", "body")
        assert result is False

    def test_development_unconfigured_still_returns_true(self, monkeypatch):
        fake_settings = MagicMock()
        fake_settings.ENVIRONMENT = "development"
        monkeypatch.setattr("app.core.config.settings", fake_settings)
        monkeypatch.delenv("SMTP_HOST", raising=False)
        monkeypatch.delenv("SMTP_USER", raising=False)
        monkeypatch.delenv("SMTP_PASSWORD", raising=False)

        result = email_module.send_email("reservation@elkheima.com", "subject", "body")
        assert result is True

    def test_test_environment_unconfigured_still_returns_true(self, monkeypatch):
        fake_settings = MagicMock()
        fake_settings.ENVIRONMENT = "test"
        monkeypatch.setattr("app.core.config.settings", fake_settings)
        monkeypatch.delenv("SMTP_HOST", raising=False)
        monkeypatch.delenv("SMTP_USER", raising=False)
        monkeypatch.delenv("SMTP_PASSWORD", raising=False)

        result = email_module.send_email("reservation@elkheima.com", "subject", "body")
        assert result is True

    def test_configured_smtp_ssl_calls_login_and_send(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "mail.example.com")
        monkeypatch.setenv("SMTP_PORT", "465")
        monkeypatch.setenv("SMTP_USER", "reservation@elkheima.com")
        monkeypatch.setenv("SMTP_PASSWORD", "secret")

        fake_server = MagicMock()
        fake_smtp_ssl = MagicMock()
        fake_smtp_ssl.return_value.__enter__.return_value = fake_server
        monkeypatch.setattr(email_module.smtplib, "SMTP_SSL", fake_smtp_ssl)

        result = email_module.send_email("guest@example.com", "subject", "body")

        assert result is True
        fake_server.login.assert_called_once_with("reservation@elkheima.com", "secret")
        fake_server.send_message.assert_called_once()

    def test_smtp_exception_returns_false(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "mail.example.com")
        monkeypatch.setenv("SMTP_PORT", "465")
        monkeypatch.setenv("SMTP_USER", "reservation@elkheima.com")
        monkeypatch.setenv("SMTP_PASSWORD", "secret")

        def _raise(*args, **kwargs):
            raise ConnectionError("boom")

        monkeypatch.setattr(email_module.smtplib, "SMTP_SSL", _raise)

        result = email_module.send_email("guest@example.com", "subject", "body")
        assert result is False
