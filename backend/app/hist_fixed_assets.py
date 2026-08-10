"""HIST-01 — مولّد الأصول الثابتة والإهلاك التاريخي ليوليو 2026
(OPS-DATA-02 §10.7). بيستخدم maintenance.services.create_asset (حقيقي)
لإنشاء الأصول، ثم finance.services.run_depreciation (المحرّك الحقيقي
الوحيد لحساب/ترحيل الإهلاك — نفس الدالة اللي أي مستخدم حقيقي هيشغّلها من
الواجهة كل شهر) لتشغيل إهلاك يوليو فعليًا، مش رقم محسوب يدويًا.

⚠️ قرارات نطاق موثّقة صراحةً:
- opening accumulated depreciation (حتى 2026-06-30) بيتحط مباشرة على
  `Asset.accumulated_depreciation` بعد الإنشاء — `AssetCreate` schema
  نفسها **معندهاش** حقل accumulated_depreciation خالص (بديهي: أصل جديد
  حقيقي بيتسجّل النهاردة مالوش إهلاك متراكم من قبل — مفيش أي مسار عمل
  حقيقي "يبدأ" أصل بإهلاك متراكم إلا استيراد بيانات تاريخية بالظبط زي
  هنا). القيم الافتتاحية في الجدول اتتأكدت رياضيًا (straight-line شهري
  كامل من شهر الشراء لحد يونيو 2026 شاملًا) قبل الكتابة — الإجمالي طابق
  2,731,178.57 المذكور في البريف بالظبط.
- كل صف في جدول §10.7 بيتترجم لأصل واحد (13 أصل، مش تفكيك كل "14 تكييف"/
  "2 مضخة" لـ N أصل فردي) — البريف نفسه بيحذّر من التجميع *لو* الصيانة
  محتاجة تتبع serial مستقل؛ التفكيك لـ 30 أصل فردي بدقة قرش لكل واحد
  تعقيد غير مبرر لبيانات Trial تجريبية، والعدد الفعلي موثّق في `notes`
  كل أصل لو احتاج فرع لاحقًا يفكّكهم فعليًا. اتفحص بحث فعلي في المستودع
  قبل القرار ده: مفيش أي كود حالي (تقرير/شاشة) بيفترض أصل واحد = وحدة
  مادية واحدة بالضرورة.
- الأرض (`useful_life_years=None` عمدًا) مستبعدة تلقائيًا من
  `get_depreciable_assets` (فلترة `useful_life_years.isnot(None)`) —
  بديل نظيف بدل أي معالجة خاصة، ومطابق تمامًا لـ"لا إهلاك للأرض" في
  البريف."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.operational_history_seed import ScenarioContext

# (code, name, category, location, purchase_cost, useful_life_years,
#  depreciation_start_date, opening_accumulated_depreciation, notes)
_ASSET_GROUPS: tuple[tuple[str, str, str, str, Decimal, "int | None", "date | None", Decimal, str], ...] = (
    ("HIST-FA-01", "أرض المنتجع", "other", "كامل الموقع",
     Decimal("6000000.00"), None, None, Decimal("0.00"), "لا إهلاك — أرض"),
    ("HIST-FA-02", "مباني وتحسينات المنتجع", "other", "كامل الموقع",
     Decimal("9500000.00"), 25, date(2023, 1, 1), Decimal("1330000.00"), "مجموعة مبانٍ (1 group)"),
    ("HIST-FA-03", "أعمال المسبح والحدائق", "other", "منطقة المسبح والحدائق",
     Decimal("1200000.00"), 10, date(2023, 1, 1), Decimal("420000.00"), "Pool/Landscape works (1 group)"),
    ("HIST-FA-04", "مولد كهرباء رئيسي", "electrical", "غرفة المولدات",
     Decimal("450000.00"), 10, date(2024, 1, 1), Decimal("112500.00"), "أصل فردي (1 unit)"),
    ("HIST-FA-05", "مضخات مياه", "plumbing", "غرفة المضخات",
     Decimal("150000.00"), 5, date(2024, 1, 1), Decimal("75000.00"), "2 مضخة — مُجمَّعة في أصل واحد"),
    ("HIST-FA-06", "تكييفات الوحدات", "hvac", "الوحدات الفندقية",
     Decimal("420000.00"), 5, date(2024, 1, 1), Decimal("210000.00"), "14 وحدة تكييف — مُجمَّعة في أصل واحد"),
    ("HIST-FA-07", "معدات مطبخ وتبريد", "other", "المطبخ الرئيسي",
     Decimal("350000.00"), 7, date(2024, 7, 1), Decimal("100000.00"), "مجموعة معدات (1 group)"),
    ("HIST-FA-08", "معدات كافيه", "other", "الكافيه",
     Decimal("180000.00"), 5, date(2025, 1, 1), Decimal("54000.00"), "مجموعة معدات (1 group)"),
    ("HIST-FA-09", "أثاث الوحدات", "furniture", "الوحدات الفندقية",
     Decimal("630000.00"), 7, date(2024, 7, 1), Decimal("180000.00"), "14 حزمة أثاث — مُجمَّعة في أصل واحد"),
    ("HIST-FA-10", "أثاث المطعم", "furniture", "المطعم الرئيسي",
     Decimal("250000.00"), 7, date(2024, 7, 1), Decimal("71428.57"), "مجموعة أثاث (1 group)"),
    ("HIST-FA-11", "أنظمة IT/POS/CCTV", "electrical", "كامل الموقع",
     Decimal("180000.00"), 4, date(2025, 1, 1), Decimal("67500.00"), "مجموعة أنظمة (1 group)"),
    ("HIST-FA-12", "معدات شاطئ مملوكة للمنتجع", "other", "الشاطئ",
     Decimal("220000.00"), 4, date(2025, 4, 1), Decimal("68750.00"), "مجموعة معدات (1 group)"),
    ("HIST-FA-13", "معدات مغسلة وتدبير منزلي", "other", "المغسلة",
     Decimal("140000.00"), 5, date(2025, 1, 1), Decimal("42000.00"), "مجموعة معدات (1 group)"),
)


def generate(db: "Session", ctx: "ScenarioContext") -> dict:
    from app.modules.finance.services import run_depreciation
    from app.modules.maintenance import services as maint_services
    from app.modules.maintenance.schemas import AssetCreate

    branch_id = ctx.branch_id
    assets = []
    for code, name, category, location, cost, life, dep_start, opening_accum, notes in _ASSET_GROUPS:
        asset = maint_services.create_asset(db, AssetCreate(
            branch_id=branch_id, name=name, code=code, category=category, location=location,
            purchase_date=dep_start, purchase_cost=cost, salvage_value=Decimal("0"),
            useful_life_years=life, depreciation_start_date=dep_start, notes=notes,
        ))
        asset.accumulated_depreciation = opening_accum
        db.flush()
        assets.append(asset)

    result = run_depreciation(db, branch_id, ctx.period_year, ctx.period_month, user_id=0)

    return {
        "counts": {
            "assets_created": len(assets),
            "depreciation_entries_posted": len(result.entries),
            "assets_skipped": len(result.skipped_assets),
        },
        "totals": {
            "opening_accumulated_depreciation": str(sum(a[7] for a in _ASSET_GROUPS)),
            "total_purchase_cost": str(sum(a[4] for a in _ASSET_GROUPS)),
            "july_depreciation_total": str(result.total_amount),
        },
    }
