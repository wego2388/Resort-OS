"""
app/modules/finance/_services/posting.py
Extracted from app/modules/finance/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from app.modules.finance import crud
from app.modules.finance.models import JournalEntry
from app.modules.finance.schemas import (
    JournalEntryCreate,
    JournalLineCreate,
)
from app.modules.finance._services._exceptions import (
    FinancialConfigurationError,
)
from app.modules.finance._services.exchange_rates import (
    convert_to_egp,
)
from app.modules.finance._services.cost_centers import (
    ensure_default_cost_centers,
)
import logging
logger = logging.getLogger(__name__)


def validate_period_open(db: Session, branch_id: int, entry_date: date) -> None:
    """يرفع ValueError لو الفترة المحاسبية دي مقفولة (closed/locked)."""
    period = crud.get_period_status(db, branch_id, entry_date.year, entry_date.month)
    if period and period.status in ("closed", "locked"):
        raise ValueError(f"الفترة المحاسبية {entry_date.year}-{entry_date.month:02d} مقفولة")


def post_journal_entry(db: Session, data: JournalEntryCreate, user_id: int) -> JournalEntry:
    """ينشئ قيد يومية متوازن (Debit = Credit)."""
    validate_period_open(db, data.branch_id, data.entry_date)
    total_debit = sum((ln.debit for ln in data.lines), Decimal("0"))
    total_credit = sum((ln.credit for ln in data.lines), Decimal("0"))
    if abs(total_debit - total_credit) > Decimal("0.01"):
        raise ValueError(f"القيد غير متوازن: مدين={total_debit}, دائن={total_credit}")
    # ⚠️ باج حقيقي كان هنا (مراجعة Codex المستقلة قبل الإطلاق، 2026-08-30،
    # C-01): مفيش أي تحقق إن account_id/cost_center_id في كل سطر فعلاً
    # بيتبعوا نفس فرع القيد — قيد على فرع A كان يقدر يستخدم حساب أو مركز
    # تكلفة فرع B، فيلوّث أرصدة الفرعين مع بعض. هذه الدالة هي المسار الوحيد
    # اللي بيقبل account_id من المستخدم مباشرة (post_simple_revenue_journal
    # بتبني حساباتها هي بنفسها بـget_account_by_code(branch_id, code) —
    # آمنة بالبناء، مش محتاجة نفس التحقق).
    for line in data.lines:
        account = crud.get_account(db, line.account_id)
        if not account or account.branch_id != data.branch_id:
            raise ValueError(f"الحساب {line.account_id} غير موجود في فرع القيد")
        if line.cost_center_id is not None:
            cost_center = crud.get_cost_center(db, line.cost_center_id)
            if not cost_center or cost_center.branch_id != data.branch_id:
                raise ValueError(f"مركز التكلفة {line.cost_center_id} غير موجود في فرع القيد")
    entry = crud.create_journal_entry(db, data, user_id)
    db.commit()
    db.refresh(entry)
    return entry


def post_simple_revenue_journal(
    db: Session,
    branch_id: int,
    entry_date: date,
    debit_account_code: str,
    credit_account_code: str,
    amount: Decimal,
    reference: str,
    description: str,
    source: str,
    source_id: Optional[int],
    created_by: int = 0,
    currency: str = "EGP",
    cost_center_code: Optional[str] = None,
    *,
    commit_cost_centers: bool = True,
    strict: bool = False,
) -> Optional[JournalEntry]:
    """يرحّل قيد بسيط بسطرين (Dr. حساب / Cr. حساب) — النمط المتكرر اللي كان
    منسوخ في 6 موديولات (مطعم/كافيه/شاطئ/PMS/ملكية جزئية/إيجارات) كل واحد بنسخته
    الخاصة. بيبتلع أي خطأ عمدًا (حساب مش معرّف للفرع، مبلغ صفري...) وبيرجّع
    None بدل ما يرفع — عشان فشل الترحيل المحاسبي ميمنعش إتمام العملية
    التشغيلية الحقيقية (بيع/حجز/عقد) اللي استدعته. لاحظ إنه بينادي
    crud.create_journal_entry مباشرة مش post_journal_entry — يعني من غير
    التحقق من قفل الفترة المحاسبية، بنفس السلوك القديم قبل التوحيد.

    لو currency مش EGP: amount هي القيمة بالعملة الأصلية، وبتتحوّل هنا لـ EGP
    بسعر الصرف وقت entry_date (نفس آلية convert_to_egp المستخدمة للفواتير) —
    السطور (debit/credit) دايمًا EGP-equivalent عشان التقارير المجمّعة تفضل
    صح، وbعملة/سعر الصرف الأصليين بيتسجّلوا على القيد نفسه للمراجعة.

    cost_center_code (Batch 3): كود مركز التكلفة (ROOM/REST/CAFE/BEACH/TS —
    راجع DEFAULT_COST_CENTERS) — لو متحدد، بيتوسم على السطرين الاتنين (مش
    الحساب الإيرادي/المصروفي بس، السطر المقابل كمان — تبسيط متعمد، والتقرير
    بيفلتر بالفعل حسب account_type فمش بيتأثر). لو مركز التكلفة مش موجود
    بعد لفرع ده (أول قيد يترحّل قبل أي نداء لـ ensure_default_cost_centers)،
    بيتزرع هنا تلقائيًا (idempotent) بدل ما التوسيم يفشل بصمت.

    commit_cost_centers/strict (Gate 1B): لكل الاستدعاءات الحالية، السلوك
    الافتراضي (commit_cost_centers=True, strict=False) **زي ما هو بالظبط
    قبل الجولة دي** — أي فشل بيتبلع ويرجع None. الاستدعاء الجديد الوحيد
    strict=True (دفع طلب دايننج) بيمرّر commit_cost_centers=False عشان
    ensure_default_cost_centers يعمل flush بس مش commit مستقل جوه معاملة
    الدفع، وبيخلي أي فشل تجهيز حساب/مركز تكلفة/تحويل عملة يرفع
    FinancialConfigurationError بدل ما يرجع None بصمت — عشان معاملة الدفع
    تقدر تفشل بوضوح (503) بدل ما تكمل من غير قيد محاسبي حقيقي."""
    try:
        if amount <= 0:
            if strict:
                raise FinancialConfigurationError("مبلغ القيد المحاسبي غير صالح (صفر أو سالب)")
            return None
        # كل حركة مالية حقيقية بتمرر source/source_id/reference ثابتين. إعادة
        # المحاولة (timeout عند العميل، Celery retry، أو reconciliation command
        # اتشغلت مرتين) لازم ترجع نفس القيد بدل ما تسجّل إيراد/تسوية مرتين.
        # reference جزء من المفتاح عمدًا لأن بعض الموديولات تستخدم نفس source
        # وsource_id لأحداث مختلفة على نفس الكيان (مثال عقد + دفعاته).
        if source and source_id is not None:
            existing = (
                db.query(JournalEntry)
                .filter(
                    JournalEntry.branch_id == branch_id,
                    JournalEntry.source == source,
                    JournalEntry.source_id == source_id,
                    JournalEntry.reference == reference,
                )
                .first()
            )
            if existing:
                logger.info(
                    "post_simple_revenue_journal: entry already posted for source=%s "
                    "source_id=%s reference=%s — returning entry %s",
                    source, source_id, reference, existing.id,
                )
                return existing

        debit_acc = crud.get_account_by_code(db, branch_id, debit_account_code)
        credit_acc = crud.get_account_by_code(db, branch_id, credit_account_code)
        if not debit_acc or not credit_acc:
            missing = debit_account_code if not debit_acc else credit_account_code
            if strict:
                raise FinancialConfigurationError(f"حساب محاسبي غير معرّف للفرع: {missing}")
            logger.error(
                "post_simple_revenue_journal: missing account '%s' for branch=%s source=%s "
                "source_id=%s reference=%s — journal entry NOT posted",
                missing, branch_id, source, source_id, reference,
            )
            return None

        cost_center_id = None
        if cost_center_code:
            cc = crud.get_cost_center_by_code(db, branch_id, cost_center_code)
            if not cc:
                ensure_default_cost_centers(db, branch_id, commit=commit_cost_centers)
                cc = crud.get_cost_center_by_code(db, branch_id, cost_center_code)
            if not cc and strict:
                raise FinancialConfigurationError(f"تعذّر تجهيز مركز التكلفة: {cost_center_code}")
            cost_center_id = cc.id if cc else None

        currency = (currency or "EGP").upper()
        if currency == "EGP":
            egp_amount, fx_rate = amount, Decimal("1")
        else:
            egp_amount = convert_to_egp(db, amount, currency, entry_date)
            if egp_amount <= 0:
                if strict:
                    raise FinancialConfigurationError("فشل تحويل العملة لقيمة موجبة")
                logger.error(
                    "post_simple_revenue_journal: currency conversion failed (%s %s) for "
                    "branch=%s source=%s source_id=%s reference=%s — journal entry NOT posted",
                    amount, currency, branch_id, source, source_id, reference,
                )
                return None
            fx_rate = (egp_amount / amount).quantize(Decimal("0.000001"))

        entry_data = JournalEntryCreate(
            branch_id=branch_id,
            entry_date=entry_date,
            reference=reference,
            description=description,
            source=source,
            source_id=source_id,
            currency=currency,
            fx_rate=fx_rate,
            lines=[
                JournalLineCreate(account_id=debit_acc.id, debit=egp_amount, credit=Decimal("0"),
                                   cost_center_id=cost_center_id),
                JournalLineCreate(account_id=credit_acc.id, debit=Decimal("0"), credit=egp_amount,
                                   cost_center_id=cost_center_id),
            ],
        )
        return crud.create_journal_entry(db, entry_data, created_by)
    except FinancialConfigurationError:
        raise
    except Exception:
        if strict:
            raise
        logger.exception(
            "post_simple_revenue_journal: unexpected failure for branch=%s source=%s "
            "source_id=%s reference=%s — journal entry NOT posted",
            branch_id, source, source_id, reference,
        )
        return None


def _build_taxed_sale_entry(
    db: Session,
    branch_id: int,
    entry_date: date,
    *,
    debit_account_code: str,
    revenue_account_code: str,
    net_revenue_amount: Decimal,
    vat_amount: Decimal,
    service_charge_amount: Decimal,
    reference: str,
    description: str,
    source: str,
    source_id: Optional[int],
    created_by: int,
    cost_center_code: Optional[str],
    tax_profile_version: Optional[str],
    commit_cost_centers: bool,
    reverse: bool,
) -> JournalEntry:
    """المنطق المشترك بين post_taxed_sale_journal وreverse_taxed_sale_journal
    — نفس الحسابات والقيود بالظبط، الفرق الوحيد أي جانب (مدين/دائن) ياخد كل
    سطر. راجع docstring الدالتين العامتين فوق للعقد الكامل."""
    validate_period_open(db, branch_id, entry_date)

    gross_amount = (net_revenue_amount + vat_amount + service_charge_amount).quantize(Decimal("0.01"))
    if gross_amount <= 0:
        raise ValueError("إجمالي القيد المحاسبي غير صالح (صفر أو سالب)")
    if net_revenue_amount < 0 or vat_amount < 0 or service_charge_amount < 0:
        raise ValueError("مكوّنات القيد (الإيراد/الضريبة/الخدمة) لا يجوز أن تكون سالبة")

    existing = (
        db.query(JournalEntry)
        .filter(
            JournalEntry.branch_id == branch_id,
            JournalEntry.source == source,
            JournalEntry.source_id == source_id,
            JournalEntry.reference == reference,
        )
        .first()
    )
    if existing:
        logger.info(
            "_build_taxed_sale_entry: entry already posted for source=%s source_id=%s "
            "reference=%s — returning existing entry %s (idempotent no-op)",
            source, source_id, reference, existing.id,
        )
        return existing

    debit_acc = crud.get_account_by_code(db, branch_id, debit_account_code)
    revenue_acc = crud.get_account_by_code(db, branch_id, revenue_account_code)
    if not debit_acc:
        raise FinancialConfigurationError(f"حساب محاسبي غير معرّف للفرع: {debit_account_code}")
    if not revenue_acc:
        raise FinancialConfigurationError(f"حساب محاسبي غير معرّف للفرع: {revenue_account_code}")

    vat_acc = None
    if vat_amount > 0:
        vat_acc = crud.get_account_by_code(db, branch_id, "2160")
        if not vat_acc:
            raise FinancialConfigurationError("حساب محاسبي غير معرّف للفرع: 2160")

    service_acc = None
    if service_charge_amount > 0:
        service_acc = crud.get_account_by_code(db, branch_id, "2165")
        if not service_acc:
            raise FinancialConfigurationError("حساب محاسبي غير معرّف للفرع: 2165")

    cost_center_id = None
    if cost_center_code:
        cc = crud.get_cost_center_by_code(db, branch_id, cost_center_code)
        if not cc:
            ensure_default_cost_centers(db, branch_id, commit=commit_cost_centers)
            cc = crud.get_cost_center_by_code(db, branch_id, cost_center_code)
        if not cc:
            raise FinancialConfigurationError(f"تعذّر تجهيز مركز التكلفة: {cost_center_code}")
        cost_center_id = cc.id

    full_description = description
    if tax_profile_version:
        full_description = f"{description} [tax_profile={tax_profile_version}]"

    zero = Decimal("0")

    def _line(account_id: int, amount: Decimal) -> JournalLineCreate:
        # reverse=False (بيع عادي): المدين = debit_account، الدائن = الباقي.
        # reverse=True (إلغاء/مرتجع): نفس السطور بالظبط بس معكوسة — الإيراد/
        # الضريبة/الخدمة بيبقوا مدين (بيقللوا رصيدهم) وdebit_account بيبقى
        # دائن (بيرجع الكاش/يقلل الذمة) — مش قيد جديد بإجمالي gross كأنه
        # إيراد جديد، ده بالظبط الباج اللي §11.2 بتطلب تجنبه.
        is_debit_side = (account_id == debit_acc.id) != reverse
        return JournalLineCreate(
            account_id=account_id,
            debit=amount if is_debit_side else zero,
            credit=zero if is_debit_side else amount,
            cost_center_id=cost_center_id,
        )

    lines = [
        _line(debit_acc.id, gross_amount),
        _line(revenue_acc.id, net_revenue_amount),
    ]
    if vat_amount > 0:
        lines.append(_line(vat_acc.id, vat_amount))
    if service_charge_amount > 0:
        lines.append(_line(service_acc.id, service_charge_amount))

    total_debit = sum((ln.debit for ln in lines), zero)
    total_credit = sum((ln.credit for ln in lines), zero)
    if abs(total_debit - total_credit) > Decimal("0.01"):
        raise ValueError(f"القيد غير متوازن: مدين={total_debit}, دائن={total_credit}")

    entry_data = JournalEntryCreate(
        branch_id=branch_id, entry_date=entry_date, reference=reference,
        description=full_description, source=source, source_id=source_id,
        lines=lines,
    )
    return crud.create_journal_entry(db, entry_data, created_by)


def post_taxed_sale_journal(
    db: Session,
    branch_id: int,
    entry_date: date,
    *,
    debit_account_code: str,
    revenue_account_code: str,
    net_revenue_amount: Decimal,
    vat_amount: Decimal = Decimal("0"),
    service_charge_amount: Decimal = Decimal("0"),
    reference: str,
    description: str,
    source: str,
    source_id: Optional[int],
    created_by: int = 0,
    cost_center_code: Optional[str] = None,
    tax_profile_version: Optional[str] = None,
    commit_cost_centers: bool = True,
) -> JournalEntry:
    """OPS-DATA-02 §11.2 (FIN-TAX-01) — يرحّل بيع خاضع للضريبة/الخدمة بفصل
    حقيقي عن الإيراد، بدل ما dining/beach.services يرحّلوا الإجمالي كله
    (أساسي + VAT + خدمة) على حساب الإيراد زي ما كانوا بيعملوا (باج حقيقي:
    الربح وVAT payable كانوا غلط لأي بيع فيه ضريبة/رسم خدمة).

    ```
    Dr <debit_account_code>              = net_revenue_amount + vat + service
        Cr <revenue_account_code>            = net_revenue_amount   (بعد الخصم)
        Cr 2160 ضريبة القيمة المضافة مستحقة  = vat_amount    (لو > 0)
        Cr 2165 رسم خدمة مستحق                = service_charge_amount (لو > 0)
    ```

    على عكس post_simple_revenue_journal القديمة: **دايمًا strict** — لا
    ابتلاع صامت لأي فشل (حساب غير معرّف، فترة مقفولة، مبلغ غير صالح)، كلها
    بترفع استثناء حقيقي يوقف العملية المالية اللي استدعتها. لازم يحترم قفل
    الفترة المحاسبية (post_simple_revenue_journal القديمة كانت بتتخطى الفحص
    ده عمدًا — هنا لأ). مفيش commit داخلي — المسؤولية على المستدعي، زي
    الأصل.

    idempotency: لو قيد بنفس (branch_id, source, source_id, reference)
    موجود بالفعل، بيرجّعه من غير ما ينشئ نسخة تانية (إعادة محاولة آمنة بعد
    فشل شبكة/timeout، مش خطأ). مفيش unique constraint على مستوى الداتابيز
    لسه على الحقول دي (يشمل كل نقاط الترحيل القديمة، تغيير أوسع من نطاق
    هذه الدفعة) — الفحص هنا شبكة أمان تطبيقية إضافية فوق الحماية التشغيلية
    الموجودة بالفعل في كل مسار استدعاء (حالة الطلب/الدفعة نفسها بتمنع
    استدعاء التسوية مرتين أصلاً)، مش الخط الدفاعي الوحيد.

    tax_profile_version: يتحفظ كنص داخل description للتدقيق (مفيش عمود
    مخصص على JournalEntry — إضافة عمود جديد قرار migration أوسع من نطاق
    هذه الدفعة). يدعم splits حسب outlet/cost-center عن طريق استدعاء الدالة
    دي مرة لكل outlet (زي ما dining.services بتعمل بالفعل مع
    post_simple_revenue_journal اليوم) — كل استدعاء قيد متوازن مستقل بحد
    ذاته، لا حاجة لتعقيد إضافي هنا.
    """
    return _build_taxed_sale_entry(
        db, branch_id, entry_date,
        debit_account_code=debit_account_code, revenue_account_code=revenue_account_code,
        net_revenue_amount=net_revenue_amount, vat_amount=vat_amount,
        service_charge_amount=service_charge_amount, reference=reference,
        description=description, source=source, source_id=source_id,
        created_by=created_by, cost_center_code=cost_center_code,
        tax_profile_version=tax_profile_version, commit_cost_centers=commit_cost_centers,
        reverse=False,
    )


def reverse_taxed_sale_journal(
    db: Session,
    branch_id: int,
    entry_date: date,
    *,
    debit_account_code: str,
    revenue_account_code: str,
    net_revenue_amount: Decimal,
    vat_amount: Decimal = Decimal("0"),
    service_charge_amount: Decimal = Decimal("0"),
    reference: str,
    description: str,
    source: str,
    source_id: Optional[int],
    created_by: int = 0,
    cost_center_code: Optional[str] = None,
    tax_profile_version: Optional[str] = None,
    commit_cost_centers: bool = True,
) -> JournalEntry:
    """عكس post_taxed_sale_journal بالضبط — لvoid/refund. نفس الحجج بالظبط
    (net_revenue_amount/vat_amount/service_charge_amount هي نفس قيم القيد
    الأصلي اللي بيتعكس، مش قيمة سالبة)، لكن كل سطر بياخد الجانب المعاكس:

    ```
        Dr <revenue_account_code>            = net_revenue_amount
        Dr 2160 ضريبة القيمة المضافة مستحقة  = vat_amount    (لو > 0)
        Dr 2165 رسم خدمة مستحق                = service_charge_amount (لو > 0)
    Cr <debit_account_code>              = net_revenue_amount + vat + service
    ```

    ده بالظبط الفرق اللي §11.2 بتطلبه: الإلغاء/المرتجع يعكس نفس سطور
    القيد الأصلي ونسبتها، مش قيد جديد بـ Dr Revenue بإجمالي gross كأنه
    "مصروف عكسي" غير مفصّل — VAT/service payable لازم يترد بالضبط زي ما
    اتسجّل، وإلا فضل رصيدهم فيه أثر بيع اتلغى فعليًا."""
    return _build_taxed_sale_entry(
        db, branch_id, entry_date,
        debit_account_code=debit_account_code, revenue_account_code=revenue_account_code,
        net_revenue_amount=net_revenue_amount, vat_amount=vat_amount,
        service_charge_amount=service_charge_amount, reference=reference,
        description=description, source=source, source_id=source_id,
        created_by=created_by, cost_center_code=cost_center_code,
        tax_profile_version=tax_profile_version, commit_cost_centers=commit_cost_centers,
        reverse=True,
    )
