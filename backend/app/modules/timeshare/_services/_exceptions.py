"""app/modules/timeshare/_services/_exceptions.py — shared conflict/error
types used across multiple timeshare service submodules (row-locking on
installments/maintenance dues, unit allocation on visits)."""
from __future__ import annotations


class VisitConflictError(Exception):
    """وحدة ملكية جزئية مقفولة فعلاً أو ماسكاها transaction تانية الآن — 409، مش 400."""


class PaymentConflictError(Exception):
    """قسط/مستحق صيانة مقفول بعملية تحصيل تانية شغالة عليه دلوقتي — 409، مش 400."""
