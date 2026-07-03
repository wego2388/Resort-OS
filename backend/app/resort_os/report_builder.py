"""Singleton ReportBuilder per resort-os."""
from __future__ import annotations

from app.core.kernel.reports import ReportBuilder

builder = ReportBuilder(
    app_name="الخيمة بيتش ريزورت",
    primary_color="#1A1A2E",
    accent_color="#C9A84C",
)
