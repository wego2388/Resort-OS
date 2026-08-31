"""
tests/test_kernel_whatsapp.py
مراجعة Codex 2026-08-31 (SEC-13): send_whatsapp_message كانت بترجع True
حتى لو Twilio مش مُعدّة خالص — أي caller (فحص احتيال، فشل مهمة، تنبيه تأخر
سداد) كان بيصدّق إن التنبيه اتبعت فعليًا، بينما هو راح للفراغ بصمت. الفحص
هنا يثبت السلوك الجديد: True بس في بيئات التطوير/الاختبار (نفس القديم
عمدًا)، False + ERROR واضح في أي بيئة تانية (الإنتاج تحديدًا).
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.core.kernel import whatsapp


class TestSendWhatsappMessageEnvironmentAwareness:
    def test_production_unconfigured_returns_false_not_true(self, monkeypatch):
        fake_settings = MagicMock()
        fake_settings.ENVIRONMENT = "production"
        monkeypatch.setattr("app.core.config.settings", fake_settings)
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
        # كل تست بيعمل reset لكاش الـTwilio client (متغيرات module-level).
        monkeypatch.setattr(whatsapp, "_twilio_client", None)
        monkeypatch.setattr(whatsapp, "_twilio_init_attempted", False)

        result = whatsapp.send_whatsapp_message("+201000000000", "تنبيه احتيال حقيقي")
        assert result is False

    def test_development_unconfigured_still_returns_true(self, monkeypatch):
        """السلوك القديم يفضل زي ما هو محليًا — مفيش داعي لإعداد Twilio
        حقيقي للتطوير."""
        fake_settings = MagicMock()
        fake_settings.ENVIRONMENT = "development"
        monkeypatch.setattr("app.core.config.settings", fake_settings)
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
        monkeypatch.setattr(whatsapp, "_twilio_client", None)
        monkeypatch.setattr(whatsapp, "_twilio_init_attempted", False)

        result = whatsapp.send_whatsapp_message("+201000000000", "رسالة تجريبية")
        assert result is True

    def test_test_environment_unconfigured_still_returns_true(self, monkeypatch):
        fake_settings = MagicMock()
        fake_settings.ENVIRONMENT = "test"
        monkeypatch.setattr("app.core.config.settings", fake_settings)
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
        monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
        monkeypatch.setattr(whatsapp, "_twilio_client", None)
        monkeypatch.setattr(whatsapp, "_twilio_init_attempted", False)

        result = whatsapp.send_whatsapp_message("+201000000000", "رسالة تجريبية")
        assert result is True
