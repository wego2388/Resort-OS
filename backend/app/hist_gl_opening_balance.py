"""HIST-01 — قيد الافتتاح الصناعي 2026-06-30 (OPS-DATA-02 §11.3). قيد يومية
واحد حقيقي عبر finance.services.post_journal_entry (الـprimitive الصارم
الوحيد — بيتحقق من توازن مدين/دائن ومن قفل الفترة، صفر SQL مباشر).

⚠️ هذا القيد **مصدر بيانات مستقل**، مش نتيجة محسوبة من مولّدات يوليو
التشغيلية التانية (leasing/timeshare/inventory/fixed_assets) — هو يمثّل
"نقطة البداية" اللي §11.4 بيحطها كخطوة 1 قبل عمليات يوليو، بالظبط زي ما
مكتوب في البريف. عشان كده مسجَّل **الأول** في SCENARIO_MODULES، قبل أي
مولّد تشغيلي تاني، وتاريخه (2026-06-30) صريح على كل سطر بغض النظر عن
scenario_clock الحالية.

⚠️ ملاحظة اتساق (مش تناقض): مبلغ المخزون هنا (420,000) و"إجمالي الأصول
الثابتة الإجمالي" (19,670,000) بيطابقوا نفس الأرقام اللي hist_inventory.py
وhist_fixed_assets.py بيبنوا عليها فعليًا — الأرقام دي معتمدة كافتراض
Trial واحد متسق عبر كل المولّدات، مش صدفة. تفصيل "Fixed assets gross
1500-1540" هنا لـ6 حسابات فرعية (مش سطر واحد زي الجدول الأصلي في
البريف) مبني على نفس تصنيف الأصول الـ13 في hist_fixed_assets.py بالظبط
(Land→1500, Buildings→1510, Pool/Landscape→1515, باقي المعدات→1520,
الأثاث→1530, IT→1540) — يحقق "خزّن source breakdown... لا يكفي وصف
Opening balance عام" (§11.3) بدل سطر واحد مبهم."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.operational_history_seed import ScenarioContext

_OPENING_DATE = date(2026, 6, 30)

# (account_code, debit, credit, description)
_LINES: tuple[tuple[str, Decimal, Decimal, str], ...] = (
    ("1100", Decimal("150000.00"), Decimal("0"), "رصيد كاش افتتاحي — الصندوق والأدراج"),
    ("1110", Decimal("950000.00"), Decimal("0"), "رصيد بنكي افتتاحي"),
    ("1150", Decimal("85000.00"), Decimal("0"), "ذمم فندقية مفتوحة (guest folios) حتى 2026-06-30"),
    ("1170", Decimal("320000.00"), Decimal("0"), "ذمم أقساط تايم شير مستحقة حتى 2026-06-30"),
    ("1200", Decimal("420000.00"), Decimal("0"), "تقييم مخزون افتتاحي (Food&Bev/Housekeeping/Maintenance/Beach)"),
    ("1210", Decimal("75000.00"), Decimal("0"), "مصروفات مدفوعة مقدمًا (تأمينات/تراخيص/اشتراكات)"),
    # ── الأصول الثابتة الإجمالية 19,670,000 — مفصّلة على 6 حسابات فرعية
    # بنفس تصنيف hist_fixed_assets.py's 13 مجموعة أصل بالظبط ──────────
    ("1500", Decimal("6000000.00"), Decimal("0"), "أرض المنتجع (HIST-FA-01)"),
    ("1510", Decimal("9500000.00"), Decimal("0"), "مباني وتحسينات المنتجع (HIST-FA-02)"),
    ("1515", Decimal("1200000.00"), Decimal("0"), "أعمال المسبح والحدائق (HIST-FA-03)"),
    ("1520", Decimal("1910000.00"), Decimal("0"),
     "معدات (مولد+مضخات+تكييفات+مطبخ+كافيه+شاطئ+مغسلة — HIST-FA-04/05/06/07/08/12/13)"),
    ("1530", Decimal("880000.00"), Decimal("0"), "أثاث الوحدات والمطعم (HIST-FA-09/10)"),
    ("1540", Decimal("180000.00"), Decimal("0"), "أنظمة IT/POS/CCTV (HIST-FA-11)"),
    ("1590", Decimal("0"), Decimal("2731178.57"), "مجمّع إهلاك افتتاحي (مطابق لإجمالي hist_fixed_assets.py)"),
    ("2200", Decimal("0"), Decimal("230000.00"), "ذمم موردين دائنة مستحقة حتى 2026-06-30"),
    ("2160", Decimal("0"), Decimal("95000.00"), "ضريبة قيمة مضافة مستحقة (VAT payable) حتى 2026-06-30"),
    ("2170", Decimal("0"), Decimal("140000.00"), "دفعات مقدمة من نزلاء (guest advances)"),
    ("2150", Decimal("0"), Decimal("276000.00"), "تأمينات مستأجرين محصّلة (tenant deposits — عقود الإيجار الخمسة)"),
    ("2310", Decimal("0"), Decimal("360000.00"), "التزام عقود/صيانة تايم شير (contract + maintenance liability)"),
    ("2180", Decimal("0"), Decimal("45000.00"), "مصروفات مرافق مستحقة (كهرباء/مياه/إنترنت) حتى 2026-06-30"),
    ("3100", Decimal("0"), Decimal("17500000.00"), "رأس المال"),
    ("3200", Decimal("0"), Decimal("292821.43"), "أرباح مرحّلة"),
)


def generate(db: "Session", ctx: "ScenarioContext") -> dict:
    from app.modules.finance.crud import get_account_by_code
    from app.modules.finance.schemas import JournalEntryCreate, JournalLineCreate
    from app.modules.finance.services import post_journal_entry

    branch_id = ctx.branch_id
    lines = []
    missing = []
    for code, debit, credit, description in _LINES:
        account = get_account_by_code(db, branch_id, code)
        if not account:
            missing.append(code)
            continue
        lines.append(JournalLineCreate(
            account_id=account.id, debit=debit, credit=credit, description=description,
        ))
    if missing:
        raise RuntimeError(f"hist_gl_opening_balance: حسابات مفقودة للفرع {branch_id}: {missing}")

    total_debit = sum(l.debit for l in lines)
    total_credit = sum(l.credit for l in lines)
    if total_debit != total_credit:
        raise RuntimeError(
            f"hist_gl_opening_balance: القيد الافتتاحي غير متوازن — مدين={total_debit} دائن={total_credit}"
        )

    entry = post_journal_entry(db, JournalEntryCreate(
        branch_id=branch_id, entry_date=_OPENING_DATE, reference="HIST-GL-OPENING-2026-06-30",
        description="قيد الافتتاح الصناعي 2026-06-30 (OPS-DATA-02 §11.3) — Trial synthetic, ليس تقييمًا حقيقيًا",
        source="opening_balance", lines=lines,
    ), user_id=0)

    return {
        "counts": {"journal_lines": len(lines)},
        "totals": {
            "total_debit": str(total_debit),
            "total_credit": str(total_credit),
            "journal_entry_id": entry.id,
        },
    }
