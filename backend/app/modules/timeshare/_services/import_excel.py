"""app/modules/timeshare/_services/import_excel.py — bulk contract import
from an Excel workbook (legacy paper-contract digitization).

الصف الأول = أسماء الأعمدة (مطابقة لحقول TimeshareContractCreate)،
الأعمدة الإلزامية: customer_name, room_type, total_value, down_payment,
installments, start_date, first_installment_date. الباقي اختياري.
Idempotent: لو form_number موجود بالفعل لنفس الفرع، الصف يتجاهَل (مش يتكرر)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.modules.timeshare import crud
from app.modules.timeshare.schemas import TimeshareContractCreate

from .contracts import create_contract

_REQUIRED_COLUMNS = {
    "customer_name", "room_type", "total_value", "down_payment",
    "installments", "start_date", "first_installment_date",
}

_DATE_FIELDS = {"start_date", "end_date", "first_installment_date", "contract_date"}
_DECIMAL_FIELDS = {
    "total_value", "down_payment", "partner_share_pct", "purchase_price",
    "contract_deposit", "maintenance_fee", "maintenance_increase",
    "contract_value", "net_contract_value", "over_under_price",
}
_INT_FIELDS = {"week_number", "nights_per_year", "installments", "installment_period", "batch_number", "years_count"}
_BOOL_FIELDS = {"rci_included"}


def _coerce_cell(field: str, value):
    if value is None or value == "":
        return None
    if field in _DATE_FIELDS:
        from datetime import date as _date, datetime as _datetime  # noqa: PLC0415
        if isinstance(value, _datetime):
            return value.date()
        if isinstance(value, _date):
            return value
        return _datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    if field in _DECIMAL_FIELDS:
        from decimal import Decimal as _Decimal  # noqa: PLC0415
        return _Decimal(str(value))
    if field in _INT_FIELDS:
        return int(value)
    if field in _BOOL_FIELDS:
        return str(value).strip().lower() in ("1", "true", "yes", "y", "نعم")
    return str(value).strip()


def import_contracts_excel(
    db: Session, branch_id: int, file_content: bytes, signed_by: int,
) -> dict:
    import openpyxl  # noqa: PLC0415
    import io as _io  # noqa: PLC0415

    # حد أقصى 5 MB قبل load_workbook — zip bomb protection
    _EXCEL_MAX_BYTES = 5 * 1024 * 1024
    if len(file_content) > _EXCEL_MAX_BYTES:
        raise ValueError("حجم الملف أكبر من 5 ميجابايت")

    wb = openpyxl.load_workbook(_io.BytesIO(file_content), data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise ValueError("الملف فاضي")

    headers = [str(h).strip() if h else "" for h in rows[0]]
    valid_fields = set(TimeshareContractCreate.model_fields.keys())
    missing = _REQUIRED_COLUMNS - set(headers)
    if missing:
        raise ValueError(f"أعمدة إلزامية ناقصة: {', '.join(sorted(missing))}")

    imported, skipped, errors = 0, 0, []
    unknown_capacity_rows: list[int] = []

    for i, row in enumerate(rows[1:], start=2):
        row_dict = {h: v for h, v in zip(headers, row) if h}
        if not row_dict.get("customer_name"):
            continue
        try:
            payload = {"branch_id": branch_id}
            for field, raw_value in row_dict.items():
                if field in valid_fields:
                    payload[field] = _coerce_cell(field, raw_value)

            # OPS-DATA-02 §8 نقطة 2: unit_capacity مش عمود متوقَّع في ملفات
            # Excel القديمة. Studio يُستنتَج بأمان 100% (مفيش أي التباس).
            # Chalet كان قديمًا 4R أو 6R — الفرق ضاع فعليًا وقت توحيدهم في
            # migration سابقة، فمفيش استنتاج آمن؛ يفضل None ويتسجّل الصف في
            # unknown_capacity_rows بدل تخمين 4 أو 6 عشوائيًا.
            if payload.get("unit_capacity") is None:
                if payload.get("room_type") == "Studio":
                    payload["unit_capacity"] = 2
                else:
                    unknown_capacity_rows.append(i)

            form_number = payload.get("form_number")
            if form_number and crud.get_contract_by_form_number(db, branch_id, str(form_number)):
                skipped += 1
                continue

            data = TimeshareContractCreate(**{k: v for k, v in payload.items() if v is not None or k == "branch_id"})

            # ⚠️ باج حقيقي كان هنا: form_number فاضي (شائع في الملفات
            # القديمة) كان بيتخطى فحص التكرار بالكامل — رفع نفس الملف مرتين
            # كان بيضاعف كل عقوده اللي من غير رقم فورمة. راجع
            # crud.get_contract_by_natural_key لتفاصيل المفتاح البديل.
            if not form_number and crud.get_contract_by_natural_key(
                db, branch_id, data.customer_name, data.unit_id, data.start_date, data.total_value,
            ):
                skipped += 1
                continue

            create_contract(db, data, signed_by)
            imported += 1
        except Exception as exc:
            errors.append(f"صف {i}: {str(exc)[:120]}")

    return {
        "imported": imported, "skipped": skipped, "errors": errors[:20],
        "unknown_capacity_rows": unknown_capacity_rows,
    }
