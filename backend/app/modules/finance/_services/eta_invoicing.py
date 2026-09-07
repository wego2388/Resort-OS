"""
app/modules/finance/_services/eta_invoicing.py
Extracted from app/modules/finance/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Session
from app.modules.finance import crud
from app.resort_os.timezone_utils import local_today
from app.modules.finance.models import ETAInvoice


# ── ETA E-Invoice ────────────────────────────────────────────────────

async def submit_eta_invoice(db: Session, settings, data) -> ETAInvoice:
    """يبني مستند ETA ويرسله، ويسجّل النتيجة دايماً (نجاح أو فشل) في
    eta_invoices للتدقيق وإعادة المحاولة لاحقاً."""
    from app.modules.finance.eta_service import ETAConfigError, ETAService, ETASubmissionError

    if not settings.ETA_ENABLED:
        raise ValueError("ETA e-invoicing غير مفعّل — ETA_ENABLED=false في .env")

    # ⚠️ internal_id فريد globally على مستوى الداتابيز كلها (ETAInvoice.internal_id
    # unique=True بدون branch_id) — لأن ETA_TAXPAYER_RIN/ETA_TAXPAYER_NAME إعداد
    # واحد للمنتجع كله (كيان ضريبي واحد)، مش لكل فرع. العدّاد هنا لازم يبقى
    # عالمي (كل الفروع) مش مقصور على data.branch_id، وإلا فرعين مختلفين
    # بيبعتوا أول فاتورة ETA في نفس اليوم كانوا هيتصادموا على نفس internal_id
    # ويطيحوا بـ IntegrityError (باج حقيقي اتكشف بالتستات — راجع تاريخ الالتزام).
    today = local_today(settings.TIMEZONE)
    count = db.query(ETAInvoice).filter(
        ETAInvoice.internal_id.like(f"ETA-{today:%Y%m%d}-%"),
    ).count()
    internal_id = f"ETA-{today:%Y%m%d}-{count + 1:04d}"

    from app.modules.core.services import get_effective_vat_percentage  # noqa: PLC0415

    try:
        eta = ETAService(settings)
        document = eta.build_invoice_document(
            internal_id=internal_id,
            issued_at_iso=datetime.utcnow().isoformat() + "Z",
            receiver_name=data.receiver_name,
            receiver_rin=data.receiver_rin,
            default_vat_rate=get_effective_vat_percentage(db, data.branch_id),
            line_items=[item.model_dump() for item in data.line_items],
        )
    except ETAConfigError as exc:
        raise ValueError(str(exc))

    import json as _json
    invoice = crud.create_eta_invoice(
        db, data.branch_id, data.folio_id, internal_id, _json.dumps(document, ensure_ascii=False),
    )

    try:
        result = await eta.submit_invoice(document)
        accepted = result.get("acceptedDocuments") or []
        rejected = result.get("rejectedDocuments") or []
        if accepted:
            crud.mark_eta_invoice_submitted(
                db, invoice, status="submitted",
                submission_uuid=accepted[0].get("uuid"),
                long_id=accepted[0].get("longId"),
                response_json=_json.dumps(result, ensure_ascii=False),
            )
        else:
            crud.mark_eta_invoice_submitted(
                db, invoice, status="invalid",
                response_json=_json.dumps(result, ensure_ascii=False),
                error_message=str(rejected[:1] or result),
            )
    except ETASubmissionError as exc:
        crud.mark_eta_invoice_submitted(db, invoice, status="failed", error_message=str(exc))

    db.refresh(invoice)
    return invoice
