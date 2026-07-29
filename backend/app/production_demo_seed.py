"""Controlled synthetic demo-data importer for the one El Kheima branch.

This is deliberately separate from :mod:`app.seed`.  The development seeder
creates public, fixed-password identities and live-looking financial activity,
so it must remain blocked in production.  This importer has a narrower
contract:

* one explicitly named active branch;
* one attributable active super-admin actor;
* no users, passwords, sessions, or permission changes;
* no posted journals, payments, payroll, receipts, sales, or live bookings;
* no pending reminder targets or publishable public content;
* synthetic rows are labelled and the whole import is audit-marked;
* one transaction, an advisory lock on PostgreSQL, dry-run by default.

Run from the backend container:

    python -m app.production_demo_seed --branch-code ELK-001
    python -m app.production_demo_seed --branch-code ELK-001 --apply \
      --confirm "APPLY EL KHEIMA SYNTHETIC DEMO V1"
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.resort_os.timezone_utils import business_today

DATASET_VERSION = "2026-07-30.1"
MARKER_ACTION = "synthetic_demo_dataset_seeded"
MARKER_ENTITY = "demo_dataset"
CONFIRMATION_PHRASE = "APPLY EL KHEIMA SYNTHETIC DEMO V1"
DEMO_NOTE = "بيانات عرض صناعية — ليست معاملة أو طرفًا حقيقيًا"
_ADVISORY_LOCK_KEY = 4_502_026_073_001


def _today():
    return business_today(settings.TIMEZONE)


@dataclass(frozen=True)
class DemoSeedResult:
    branch_code: str
    version: str
    already_applied: bool
    before: dict[str, int]
    after: dict[str, int]

    @property
    def added(self) -> dict[str, int]:
        return {
            key: self.after.get(key, 0) - self.before.get(key, 0)
            for key in sorted(self.after)
            if self.after.get(key, 0) - self.before.get(key, 0)
        }


def _count_models(db: Session) -> dict[str, int]:
    from app.core.kernel.models.user import User
    from app.modules.beach.models import (
        B2BContract,
        BeachLocation,
        BeachReservation,
        BeachTransaction,
    )
    from app.modules.core.models import GuestAlert, Notification
    from app.modules.crm.models import Campaign, Customer, Lead, Opportunity
    from app.modules.dining.models import (
        DiningCategory,
        DiningItem,
        DiningItemRecipeLine,
        DiningOrder,
        Outlet,
        VenueTable,
    )
    from app.modules.finance.models import JournalEntry, Payment
    from app.modules.hr.models import Department, Employee, PayrollRun
    from app.modules.hub.models import BlogPost, HubOffer, HubOnlineBooking, HubPage
    from app.modules.inventory.models import (
        Category,
        Product,
        PurchaseOrder,
        PurchaseRequest,
        StockMovement,
        Supplier,
        Warehouse,
    )
    from app.modules.leasing.models import LeaseContract, LeasePayment
    from app.modules.maintenance.models import Asset, WorkOrder
    from app.modules.pms.models import Booking, RatePlan, Room, RoomType
    from app.modules.timeshare.models import (
        TimeshareContract,
        TimeshareInstallment,
        TimeshareUnit,
    )

    models = {
        "assets": Asset,
        "b2b_contracts": B2BContract,
        "beach_locations": BeachLocation,
        "beach_reservations": BeachReservation,
        "beach_transactions": BeachTransaction,
        "blog_posts": BlogPost,
        "bookings": Booking,
        "campaigns": Campaign,
        "crm_customers": Customer,
        "departments": Department,
        "dining_categories": DiningCategory,
        "dining_items": DiningItem,
        "dining_orders": DiningOrder,
        "dining_recipe_lines": DiningItemRecipeLine,
        "dining_tables": VenueTable,
        "employees": Employee,
        "guest_alerts": GuestAlert,
        "hub_offers": HubOffer,
        "hub_online_bookings": HubOnlineBooking,
        "hub_pages": HubPage,
        "inventory_categories": Category,
        "journal_entries": JournalEntry,
        "lease_contracts": LeaseContract,
        "lease_payments": LeasePayment,
        "leads": Lead,
        "opportunities": Opportunity,
        "outlets": Outlet,
        "payments": Payment,
        "payroll_runs": PayrollRun,
        "products": Product,
        "purchase_orders": PurchaseOrder,
        "purchase_requests": PurchaseRequest,
        "rate_plans": RatePlan,
        "room_types": RoomType,
        "rooms": Room,
        "stock_movements": StockMovement,
        "suppliers": Supplier,
        "timeshare_contracts": TimeshareContract,
        "timeshare_installments": TimeshareInstallment,
        "timeshare_units": TimeshareUnit,
        "users": User,
        "warehouses": Warehouse,
        "work_orders": WorkOrder,
        "notifications": Notification,
    }
    return {
        key: int(db.query(func.count(model.id)).scalar() or 0)
        for key, model in models.items()
    }


def _acquire_lock(db: Session) -> None:
    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _ADVISORY_LOCK_KEY},
        )


def _resolve_scope(db: Session, expected_branch_code: str, actor_id: int | None):
    from app.core.kernel.models.user import User
    from app.modules.core.models import Branch

    branches = db.query(Branch).order_by(Branch.id).all()
    if len(branches) != 1:
        raise RuntimeError(
            f"Expected exactly one branch; found {len(branches)}. "
            "The production demo import is single-branch only."
        )
    branch = branches[0]
    if not branch.is_active or branch.code != expected_branch_code:
        raise RuntimeError(
            f"Branch mismatch: expected active {expected_branch_code!r}, "
            f"found {branch.code!r} (active={branch.is_active})."
        )

    query = db.query(User).filter(User.is_active.is_(True))
    if actor_id is not None:
        query = query.filter(User.id == actor_id)
    actors = [
        user
        for user in query.all()
        if getattr(user.role, "value", user.role) == "super_admin"
    ]
    if len(actors) != 1:
        raise RuntimeError(
            "Resolve exactly one active super_admin actor, or pass --actor-id."
        )
    return branch, actors[0]


def _existing_marker(db: Session, branch_id: int):
    from app.modules.core.models import AuditLog

    return (
        db.query(AuditLog)
        .filter(
            AuditLog.branch_id == branch_id,
            AuditLog.action == MARKER_ACTION,
            AuditLog.entity_type == MARKER_ENTITY,
        )
        .order_by(AuditLog.id.desc())
        .first()
    )


def _seed_inventory_categories(db: Session, branch_id: int) -> None:
    from app.modules.inventory.models import Category

    specs = [
        ("Food Items", "مواد غذائية"),
        ("Beverages", "مشروبات"),
        ("Cleaning Supplies", "مستلزمات النظافة"),
        ("Beach Supplies", "مستلزمات الشاطئ"),
        ("Spare Parts", "قطع الغيار"),
        ("Kitchen Supplies", "مستلزمات المطبخ"),
        ("Furniture", "الأثاث والمفروشات"),
        ("Raw Materials", "المواد الخام"),
        ("Guest Amenities", "مستلزمات النزلاء"),
        ("Linen", "المفروشات الفندقية"),
    ]
    existing = {
        row.name
        for row in db.query(Category).filter(Category.branch_id == branch_id).all()
    }
    for name, name_ar in specs:
        if name not in existing:
            db.add(Category(branch_id=branch_id, name=name, name_ar=name_ar))
    db.flush()


def _seed_warehouses(db: Session, branch_id: int):
    from app.modules.inventory.models import Warehouse

    specs = [
        ("WH-KITCHEN", "Main Kitchen Store", "مخزن المطبخ الرئيسي"),
        ("WH-BEVERAGE", "Beverage Store", "مخزن المشروبات"),
        ("WH-OPS", "Operations & Engineering Store", "مخزن التشغيل والصيانة"),
    ]
    existing = {
        row.code: row
        for row in db.query(Warehouse).filter(Warehouse.branch_id == branch_id).all()
    }
    for code, name, name_ar in specs:
        if code not in existing:
            row = Warehouse(
                branch_id=branch_id,
                code=code,
                name=name,
                name_ar=name_ar,
                notes=DEMO_NOTE,
                is_active=True,
            )
            db.add(row)
            db.flush()
            existing[code] = row
    return existing


def _seed_cross_department_products(
    db: Session,
    branch_id: int,
    warehouses: dict[str, Any],
    actor_id: int,
) -> None:
    from app.modules.inventory.models import Category, Product, StockMovement

    categories = {
        row.name: row.id
        for row in db.query(Category).filter(Category.branch_id == branch_id).all()
    }
    specs = [
        (
            "HK-DETERGENT",
            "Hotel Laundry Detergent",
            "مسحوق غسيل فندقي",
            "kg",
            "Cleaning Supplies",
            "WH-OPS",
            "65",
            "30",
            "8",
            "12",
        ),
        (
            "HK-DISINFECT",
            "Surface Disinfectant",
            "مطهر أسطح",
            "liter",
            "Cleaning Supplies",
            "WH-OPS",
            "55",
            "24",
            "6",
            "10",
        ),
        (
            "HK-BAG-L",
            "Heavy Duty Waste Bags",
            "أكياس قمامة كبيرة",
            "pack",
            "Cleaning Supplies",
            "WH-OPS",
            "90",
            "18",
            "5",
            "8",
        ),
        (
            "LIN-BATH",
            "Bath Towel 70x140",
            "فوطة حمام 70×140",
            "piece",
            "Linen",
            "WH-OPS",
            "180",
            "80",
            "20",
            "30",
        ),
        (
            "LIN-BED-Q",
            "Queen Bed Sheet",
            "ملاءة سرير مزدوج",
            "piece",
            "Linen",
            "WH-OPS",
            "320",
            "36",
            "10",
            "15",
        ),
        (
            "GST-AMENITY",
            "Guest Amenity Kit",
            "طقم مستلزمات نزيل",
            "pack",
            "Guest Amenities",
            "WH-OPS",
            "45",
            "60",
            "15",
            "25",
        ),
        (
            "BCH-TOWEL",
            "Beach Towel",
            "فوطة شاطئ",
            "piece",
            "Beach Supplies",
            "WH-OPS",
            "220",
            "120",
            "30",
            "45",
        ),
        (
            "BCH-BRACELET",
            "Day-use Wristband",
            "سوار دخول يومي",
            "piece",
            "Beach Supplies",
            "WH-OPS",
            "4",
            "300",
            "100",
            "150",
        ),
        (
            "MNT-AC-FILTER",
            "Split AC Filter",
            "فلتر تكييف سبليت",
            "piece",
            "Spare Parts",
            "WH-OPS",
            "280",
            "12",
            "4",
            "6",
        ),
        (
            "MNT-PUMP-SEAL",
            "Pool Pump Mechanical Seal",
            "سيل ميكانيكي لمضخة المسبح",
            "piece",
            "Spare Parts",
            "WH-OPS",
            "650",
            "5",
            "2",
            "3",
        ),
        (
            "MNT-LED-12W",
            "LED Bulb 12W",
            "لمبة ليد 12 وات",
            "piece",
            "Spare Parts",
            "WH-OPS",
            "75",
            "30",
            "8",
            "12",
        ),
        (
            "KIT-GLOVE",
            "Food-safe Disposable Gloves",
            "قفازات مطبخ",
            "box",
            "Kitchen Supplies",
            "WH-KITCHEN",
            "140",
            "16",
            "5",
            "8",
        ),
    ]
    existing = {
        row.sku
        for row in db.query(Product).filter(Product.branch_id == branch_id).all()
    }
    now = datetime.now(timezone.utc)
    for (
        sku,
        name,
        name_ar,
        unit,
        category,
        warehouse_code,
        cost,
        stock,
        minimum,
        reorder,
    ) in specs:
        if sku in existing:
            continue
        warehouse = warehouses[warehouse_code]
        product = Product(
            branch_id=branch_id,
            category_id=categories.get(category),
            warehouse_id=warehouse.id,
            name=name,
            name_ar=name_ar,
            sku=sku,
            unit=unit,
            cost_price=Decimal(cost),
            current_stock=Decimal(stock),
            min_stock=Decimal(minimum),
            reorder_point=Decimal(reorder),
            notes=DEMO_NOTE,
            is_active=True,
        )
        db.add(product)
        db.flush()
        db.add(
            StockMovement(
                branch_id=branch_id,
                product_id=product.id,
                warehouse_id=warehouse.id,
                movement_type="adjustment",
                quantity=Decimal(stock),
                unit_cost=Decimal(cost),
                reference_type="demo_seed",
                notes=f"{DEMO_NOTE} — رصيد افتتاحي",
                moved_by=actor_id,
                moved_at=now,
            )
        )
    db.flush()


def _seed_suppliers_and_draft_procurement(
    db: Session,
    branch_id: int,
    actor_id: int,
) -> None:
    from app.modules.inventory.models import (
        Product,
        PurchaseApproval,
        PurchaseOrder,
        PurchaseOrderItem,
        PurchaseRequest,
        PurchaseRequestItem,
        Supplier,
    )

    supplier_specs = [
        ("Red Sea Fresh Foods", "توريدات البحر الأحمر للأغذية", "food", 14, "75000"),
        ("South Sinai Beverages", "مشروبات جنوب سيناء", "beverage", 21, "50000"),
        ("Hotel Care Supplies", "هوتيل كير لمستلزمات النظافة", "cleaning", 30, "40000"),
        ("Hospitality Linen House", "بيت المفروشات الفندقية", "linen", 30, "60000"),
        (
            "Engineering Parts Egypt",
            "قطع غيار التجهيزات الفندقية",
            "maintenance",
            45,
            "90000",
        ),
        ("Beach Operations Supply", "توريدات تشغيل الشاطئ", "beach", 15, "35000"),
    ]
    suppliers = {
        row.name: row
        for row in db.query(Supplier).filter(Supplier.branch_id == branch_id).all()
    }
    for name, name_ar, category, terms, credit in supplier_specs:
        if name not in suppliers:
            row = Supplier(
                branch_id=branch_id,
                name=name,
                name_ar=name_ar,
                category=category,
                payment_terms_days=terms,
                credit_limit=Decimal(credit),
                notes=f"{DEMO_NOTE} — لا توجد بيانات اتصال لمنع أي إرسال خارجي",
                is_active=True,
            )
            db.add(row)
            db.flush()
            suppliers[name] = row

    if (
        not db.query(PurchaseOrder)
        .filter(
            PurchaseOrder.branch_id == branch_id,
            PurchaseOrder.order_number.like("DPO-%"),
        )
        .first()
    ):
        products = {
            row.sku: row
            for row in db.query(Product).filter(Product.branch_id == branch_id).all()
        }
        today = _today()
        po_specs = [
            (
                "DPO-FOOD-001",
                "Red Sea Fresh Foods",
                "draft",
                [("CHKN-BRS", "20"), ("RICE-RAW", "50")],
            ),
            (
                "DPO-BEV-001",
                "South Sinai Beverages",
                "sent",
                [("WATER-SM", "240"), ("COLA-C", "96")],
            ),
            (
                "DPO-HK-001",
                "Hotel Care Supplies",
                "draft",
                [("HK-DETERGENT", "25"), ("HK-DISINFECT", "30")],
            ),
            (
                "DPO-MNT-001",
                "Engineering Parts Egypt",
                "sent",
                [("MNT-AC-FILTER", "8"), ("MNT-LED-12W", "40")],
            ),
            (
                "DPO-BCH-001",
                "Beach Operations Supply",
                "cancelled",
                [("BCH-BRACELET", "500")],
            ),
        ]
        for index, (number, supplier_name, status, lines) in enumerate(po_specs):
            supplier = suppliers[supplier_name]
            po = PurchaseOrder(
                branch_id=branch_id,
                order_number=number,
                supplier_id=supplier.id,
                supplier_name=supplier.name,
                status=status,
                ordered_at=today - timedelta(days=index),
                expected_at=today + timedelta(days=7 + index),
                total_amount=Decimal(0),
                notes=DEMO_NOTE,
            )
            db.add(po)
            db.flush()
            total = Decimal(0)
            for sku, quantity_text in lines:
                product = products.get(sku)
                if not product:
                    continue
                quantity = Decimal(quantity_text)
                line_total = quantity * product.cost_price
                db.add(
                    PurchaseOrderItem(
                        purchase_order_id=po.id,
                        product_id=product.id,
                        ordered_qty=quantity,
                        received_qty=Decimal(0),
                        unit_cost=product.cost_price,
                        total_cost=line_total,
                    )
                )
                total += line_total
            po.total_amount = total

    if (
        not db.query(PurchaseRequest)
        .filter(
            PurchaseRequest.branch_id == branch_id,
            PurchaseRequest.notes.like(f"{DEMO_NOTE}%"),
        )
        .first()
    ):
        products = (
            db.query(Product)
            .filter(Product.branch_id == branch_id)
            .order_by(Product.id)
            .limit(6)
            .all()
        )
        statuses = ["draft", "dept_approved", "rejected"]
        departments = ["المطبخ", "التدبير الفندقي", "الصيانة"]
        for index, status in enumerate(statuses):
            selected = products[index * 2 : index * 2 + 2]
            total = sum(
                (product.cost_price * Decimal(5) for product in selected),
                Decimal(0),
            )
            request = PurchaseRequest(
                branch_id=branch_id,
                requester_id=actor_id,
                department=departments[index],
                status=status,
                notes=f"{DEMO_NOTE} — سيناريو {status}",
                rejected_reason="مثال عرض: الكمية تحتاج مراجعة"
                if status == "rejected"
                else None,
                total_estimated=total,
            )
            db.add(request)
            db.flush()
            for product in selected:
                db.add(
                    PurchaseRequestItem(
                        request_id=request.id,
                        product_id=product.id,
                        quantity_requested=Decimal(5),
                        unit=product.unit,
                        estimated_unit_cost=product.cost_price,
                    )
                )
            if status == "dept_approved":
                db.add(
                    PurchaseApproval(
                        request_id=request.id,
                        approver_id=actor_id,
                        level="dept",
                        status="approved",
                        notes=DEMO_NOTE,
                    )
                )
    db.flush()


def _seed_maintenance_catalog(db: Session, branch_id: int, actor_id: int) -> None:
    from app.modules.maintenance.models import Asset, WorkOrder, WorkOrderPart

    asset_specs = [
        ("DEMO-AST-001", "مكيف اللوبي الرئيسي", "hvac", "اللوبي"),
        ("DEMO-AST-002", "مضخة المسبح الرئيسية", "plumbing", "غرفة معدات المسبح"),
        ("DEMO-AST-003", "مولد الكهرباء الاحتياطي", "electrical", "غرفة المولد"),
        ("DEMO-AST-004", "ثلاجة المطبخ الكبيرة", "other", "المطبخ الرئيسي"),
        ("DEMO-AST-005", "عربة نقل النزلاء", "vehicle", "الجراج"),
        ("DEMO-AST-006", "جلسات الشاطئ الخشبية", "furniture", "الشاطئ"),
    ]
    assets = {
        row.code: row
        for row in db.query(Asset).filter(Asset.branch_id == branch_id).all()
    }
    for code, name, category, location in asset_specs:
        if code not in assets:
            row = Asset(
                branch_id=branch_id,
                code=code,
                name=name,
                category=category,
                location=location,
                status="operational",
                notes=DEMO_NOTE,
                purchase_cost=None,
            )
            db.add(row)
            db.flush()
            assets[code] = row

    if (
        not db.query(WorkOrder)
        .filter(
            WorkOrder.branch_id == branch_id,
            WorkOrder.order_number.like("DWO-%"),
        )
        .first()
    ):
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        specs = [
            (
                "DWO-001",
                "DEMO-AST-003",
                "اختبار تشغيل المولد الأسبوعي",
                "inspection",
                "completed",
            ),
            (
                "DWO-002",
                "DEMO-AST-001",
                "تنظيف فلاتر تكييف اللوبي",
                "preventive",
                "completed",
            ),
            (
                "DWO-003",
                "DEMO-AST-002",
                "فحص تسريب وصلة مضخة المسبح",
                "corrective",
                "cancelled",
            ),
        ]
        for index, (number, asset_code, title, order_type, status) in enumerate(specs):
            order = WorkOrder(
                branch_id=branch_id,
                asset_id=assets[asset_code].id,
                order_number=number,
                title=title,
                description=DEMO_NOTE,
                order_type=order_type,
                priority="medium",
                status=status,
                reported_by=actor_id,
                scheduled_date=_today() - timedelta(days=14 + index),
                completed_at=now - timedelta(days=10 + index)
                if status == "completed"
                else None,
                labour_hours=Decimal("1.5") if status == "completed" else Decimal(0),
                labour_cost=Decimal(0),
                parts_cost=Decimal(0),
                notes=DEMO_NOTE,
            )
            db.add(order)
            db.flush()
            if number == "DWO-002":
                db.add(
                    WorkOrderPart(
                        work_order_id=order.id,
                        part_name="فلتر هواء قابل للغسيل",
                        part_number="DEMO-FLT-AC",
                        quantity=Decimal(2),
                        unit_cost=Decimal(0),
                        total_cost=Decimal(0),
                    )
                )
    db.flush()


def _seed_crm_samples(db: Session, branch_id: int, actor_id: int) -> None:
    from app.modules.crm.models import (
        Activity,
        Campaign,
        Customer,
        CustomerGroup,
        Lead,
        LeadSource,
        Opportunity,
    )

    group = (
        db.query(CustomerGroup)
        .filter(
            CustomerGroup.branch_id == branch_id,
            CustomerGroup.name == "Demo Returning Guests",
        )
        .first()
    )
    if not group:
        group = CustomerGroup(
            branch_id=branch_id,
            name="Demo Returning Guests",
            name_ar="ضيوف عائدون — عرض",
            discount_percentage=Decimal(10),
            is_active=True,
        )
        db.add(group)
        db.flush()

    sources: dict[str, LeadSource] = {
        row.name: row
        for row in db.query(LeadSource).filter(LeadSource.branch_id == branch_id).all()
    }
    for name in ("website", "referral", "social_media", "walk_in", "event"):
        if name not in sources:
            row = LeadSource(branch_id=branch_id, name=name, is_active=True)
            db.add(row)
            db.flush()
            sources[name] = row

    if (
        not db.query(Customer)
        .filter(
            Customer.branch_id == branch_id,
            Customer.notes.like(f"{DEMO_NOTE}%"),
        )
        .first()
    ):
        customer_specs = [
            ("محمود عادل حلمي", "vip", "referral", "9", "45200"),
            ("سارة وليام", "regular", "online", "2", "3800"),
            ("شركة النور للسياحة — عرض", "travel_agent", "corporate", "14", "128500"),
            ("ياسمين طارق سعد", "corporate", "walk_in", "4", "9600"),
        ]
        customers: list[Customer] = []
        for index, (name, segment, source, visits, spent) in enumerate(customer_specs):
            customer = Customer(
                branch_id=branch_id,
                full_name=name,
                phone=None,
                email=None,
                nationality="مصري",
                segment=segment,
                source=source,
                customer_group_id=group.id if index == 0 else None,
                total_spent=Decimal(spent),
                visits_count=int(visits),
                last_visit=_today() - timedelta(days=7 + index * 12),
                birthday=None,
                notes=f"{DEMO_NOTE} — بيانات الاتصال محذوفة لمنع الإرسال",
                is_active=True,
            )
            db.add(customer)
            db.flush()
            customers.append(customer)

        opportunity_specs = [
            (
                customers[0],
                "عرض تجديد إقامة عائلية",
                "group_booking",
                "negotiation",
                "28000",
                60,
            ),
            (
                customers[2],
                "اتفاق مجموعات سياحية تجريبي",
                "group_booking",
                "proposal",
                "85000",
                40,
            ),
        ]
        for (
            customer,
            title,
            product_type,
            stage,
            value,
            probability,
        ) in opportunity_specs:
            db.add(
                Opportunity(
                    branch_id=branch_id,
                    customer_id=customer.id,
                    title=title,
                    product_type=product_type,
                    stage=stage,
                    expected_value=Decimal(value),
                    probability=probability,
                    assigned_to=actor_id,
                    expected_close=_today() + timedelta(days=30),
                    notes=DEMO_NOTE,
                )
            )
        db.add(
            Activity(
                branch_id=branch_id,
                customer_id=customers[0].id,
                activity_type="follow_up",
                title="متابعة عرض مكتملة — مثال",
                due_date=_today() - timedelta(days=10),
                assigned_to=None,
                status="done",
                done_at=datetime.now(timezone.utc).replace(tzinfo=None)
                - timedelta(days=9),
                notes=DEMO_NOTE,
            )
        )

    if (
        not db.query(Lead)
        .filter(
            Lead.branch_id == branch_id,
            Lead.notes.like(f"{DEMO_NOTE}%"),
        )
        .first()
    ):
        lead_specs = [
            ("عمر شريف نبيل", "timeshare", "new", "180000", "website"),
            ("منى حسني عبده", "membership", "contacted", "15000", "social_media"),
            ("طارق مجدي سيد", "booking", "qualified", "26000", "referral"),
            ("رانيا كمال شوقي", "leasing", "proposal", "95000", "event"),
        ]
        for name, interest, stage, value, source_name in lead_specs:
            db.add(
                Lead(
                    branch_id=branch_id,
                    full_name=name,
                    phone=None,
                    email=None,
                    nationality="مصري",
                    source_id=sources[source_name].id,
                    interest=interest,
                    stage=stage,
                    assigned_to=actor_id,
                    expected_value=Decimal(value),
                    notes=f"{DEMO_NOTE} — بلا موافقة تسويقية أو بيانات اتصال",
                    marketing_consent=False,
                )
            )

    if (
        not db.query(Campaign)
        .filter(
            Campaign.branch_id == branch_id,
            Campaign.notes.like(f"{DEMO_NOTE}%"),
        )
        .first()
    ):
        db.add(
            Campaign(
                branch_id=branch_id,
                name="حملة صيفية مكتملة — عرض",
                campaign_type="social_media",
                start_date=_today() - timedelta(days=60),
                end_date=_today() - timedelta(days=30),
                budget=Decimal(50000),
                revenue_attributed=Decimal(72000),
                leads_generated=18,
                status="completed",
                notes=DEMO_NOTE,
                created_by=actor_id,
            )
        )
    db.flush()


def _seed_contract_drafts(db: Session, branch_id: int) -> None:
    from app.modules.leasing.models import LeaseContract
    from app.modules.timeshare.models import TimeshareContract, TimeshareUnit

    units = (
        db.query(TimeshareUnit)
        .filter(TimeshareUnit.branch_id == branch_id)
        .order_by(TimeshareUnit.id)
        .all()
    )
    if (
        units
        and not db.query(TimeshareContract)
        .filter(
            TimeshareContract.branch_id == branch_id,
            TimeshareContract.contract_number.like("DTS-%"),
        )
        .first()
    ):
        specs = [
            ("DTS-001", "أحمد جمال منصور", "2R", "180000", "40000", 12),
            ("DTS-002", "منى عبد الرحمن", "4R", "320000", "80000", 28),
            ("DTS-003", "خالد سمير فؤاد", "6R", "500000", "120000", None),
        ]
        for index, (number, name, room_type, value, down, week) in enumerate(specs):
            matching = next(
                (unit for unit in units if unit.unit_type == room_type), None
            )
            db.add(
                TimeshareContract(
                    branch_id=branch_id,
                    contract_number=number,
                    customer_name=name,
                    customer_phone=None,
                    customer_email=None,
                    room_type=room_type,
                    unit_id=matching.id if matching else None,
                    week_number=week,
                    nights_per_year=7,
                    season="high",
                    total_value=Decimal(value),
                    down_payment=Decimal(down),
                    installments=12,
                    installment_period=1,
                    first_installment_date=_today() + timedelta(days=60 + index),
                    partner_share_pct=Decimal(0),
                    status="draft",
                    start_date=_today(),
                    maintenance_fee=Decimal(0),
                    notes=f"{DEMO_NOTE} — مسودة بلا أقساط أو إرسال",
                )
            )

    if (
        not db.query(LeaseContract)
        .filter(
            LeaseContract.branch_id == branch_id,
            LeaseContract.contract_number.like("DLC-%"),
        )
        .first()
    ):
        specs = [
            ("DLC-001", "كشك معدات الغطس — عرض", "كشك رقم D-05", "4500"),
            ("DLC-002", "بازار الهدايا — عرض", "محل رقم D-02", "6000"),
            ("DLC-003", "خدمة الشماسي — عرض", "قطاع الشاطئ D-B", "3200"),
        ]
        for number, tenant, unit, rent in specs:
            db.add(
                LeaseContract(
                    branch_id=branch_id,
                    contract_number=number,
                    tenant_name=tenant,
                    tenant_phone=None,
                    unit_description=unit,
                    start_date=_today() + timedelta(days=30),
                    end_date=_today() + timedelta(days=395),
                    base_rent=Decimal(rent),
                    increase_rate=Decimal(0),
                    billing_day=1,
                    grace_months=0,
                    payment_period="monthly",
                    security_deposit=Decimal(0),
                    status="draft",
                    notes=f"{DEMO_NOTE} — مسودة بلا جدول دفعات",
                )
            )
    db.flush()


def _seed_timeshare_units(db: Session, branch_id: int) -> None:
    from app.modules.timeshare.models import TimeshareUnit

    if db.query(TimeshareUnit).filter(TimeshareUnit.branch_id == branch_id).first():
        return
    for unit_type, prefix, count in (
        ("2R", "D-A", 6),
        ("4R", "D-B", 4),
        ("6R", "D-C", 2),
    ):
        for index in range(1, count + 1):
            db.add(
                TimeshareUnit(
                    branch_id=branch_id,
                    unit_number=f"{prefix}{100 + index}",
                    unit_type=unit_type,
                    status="available",
                    notes=DEMO_NOTE,
                )
            )
    db.flush()


def _seed_beach_reference_data(db: Session, branch_id: int) -> None:
    from app.modules.beach.models import B2BContract, BeachLocation

    existing_demo_locations = (
        db.query(BeachLocation)
        .filter(
            BeachLocation.branch_id == branch_id,
            BeachLocation.number.like("D-%"),
        )
        .count()
    )
    if not existing_demo_locations:
        for location_type, count in (("umbrella", 6), ("pergola", 2)):
            for index in range(1, count + 1):
                db.add(
                    BeachLocation(
                        branch_id=branch_id,
                        location_type=location_type,
                        number=f"D-{location_type[0].upper()}{index:02d}",
                        grid_row=1 if location_type == "umbrella" else 2,
                        grid_col=index,
                        status="available",
                    )
                )

    if (
        not db.query(B2BContract)
        .filter(
            B2BContract.branch_id == branch_id,
            B2BContract.hotel_name.like("Demo %"),
        )
        .first()
    ):
        for index, (name, name_ar, quota, price) in enumerate(
            [
                ("Demo Coral Partner Hotel", "فندق كورال الشريك — عرض", 40, "120"),
                ("Demo Palm Partner Hotel", "فندق بالم الشريك — عرض", 20, "100"),
            ]
        ):
            db.add(
                B2BContract(
                    branch_id=branch_id,
                    hotel_name=name,
                    hotel_name_ar=name_ar,
                    contact_phone=None,
                    daily_quota=quota,
                    entry_price=Decimal(price),
                    towel_price=Decimal(30),
                    valid_from=_today(),
                    valid_until=_today() + timedelta(days=365),
                    is_active=False,
                    credit_limit=None,
                    payment_terms_days=30,
                    is_overdue=False,
                    notes=f"{DEMO_NOTE} — غير نشط وبلا استخدام أو تحصيل",
                )
            )
    db.flush()


def _seed_hub_drafts(db: Session, branch_id: int, actor_id: int) -> None:
    from app.modules.hub.models import BlogPost, HubOffer, HubPage

    if (
        not db.query(HubPage)
        .filter(
            HubPage.branch_id == branch_id,
            HubPage.slug.like("demo-%"),
        )
        .first()
    ):
        pages = [
            (
                "demo-resort-services",
                "Resort Services Draft",
                "مسودة خدمات المنتجع",
                "info",
            ),
            ("demo-guest-guide", "Guest Guide Draft", "مسودة دليل الضيف", "info"),
            ("demo-events", "Events Draft", "مسودة الفعاليات", "news"),
        ]
        for index, (slug, title, title_ar, page_type) in enumerate(pages):
            db.add(
                HubPage(
                    branch_id=branch_id,
                    slug=slug,
                    title=title,
                    title_ar=title_ar,
                    content=DEMO_NOTE,
                    content_ar=DEMO_NOTE,
                    page_type=page_type,
                    is_published=False,
                    sort_order=900 + index,
                )
            )

    if (
        not db.query(HubOffer)
        .filter(
            HubOffer.branch_id == branch_id,
            HubOffer.title.like("Demo %"),
        )
        .first()
    ):
        db.add(
            HubOffer(
                branch_id=branch_id,
                title="Demo Family Day Package",
                title_ar="باقة اليوم العائلي — عرض تجريبي",
                description=DEMO_NOTE,
                description_ar=DEMO_NOTE,
                offer_type="package",
                original_price=Decimal(1000),
                offer_price=Decimal(850),
                valid_from=_today(),
                valid_until=_today() + timedelta(days=30),
                max_bookings=0,
                bookings_count=0,
                is_active=False,
            )
        )

    if (
        not db.query(BlogPost)
        .filter(
            BlogPost.branch_id == branch_id,
            BlogPost.slug.like("demo-%"),
        )
        .first()
    ):
        db.add(
            BlogPost(
                branch_id=branch_id,
                title="مسودة: دليل يوم هادئ على البحر",
                slug="demo-calm-day-by-the-sea",
                excerpt=DEMO_NOTE,
                body=DEMO_NOTE,
                status="draft",
                published_at=None,
                author_id=actor_id,
                views_count=0,
            )
        )
    db.flush()


def seed_production_demo_dataset(
    db: Session,
    *,
    expected_branch_code: str,
    actor_id: int | None = None,
) -> DemoSeedResult:
    """Stage the reviewed synthetic dataset in the caller's transaction."""
    normalized_environment = (settings.ENVIRONMENT or "").strip().lower()
    if normalized_environment not in {"production", "test", "testing"}:
        raise RuntimeError(
            "The controlled demo importer is restricted to production/test. "
            "Use app.seed for development."
        )

    _acquire_lock(db)
    branch, actor = _resolve_scope(db, expected_branch_code, actor_id)
    before = _count_models(db)
    if _existing_marker(db, branch.id):
        return DemoSeedResult(
            branch_code=branch.code,
            version=DATASET_VERSION,
            already_applied=True,
            before=before,
            after=before.copy(),
        )

    from app.modules.core.models import AuditLog
    from app.seed import (
        _seed_chart_of_accounts,
        _seed_dining_tables,
        _seed_hr_departments,
        _seed_menus,
        _seed_rate_plans,
        _seed_room_types,
        _seed_rooms,
    )
    from app.seed_food import (
        _seed_cafe_recipes,
        _seed_inventory_products_full,
        _seed_restaurant_recipes,
    )

    _seed_chart_of_accounts(db)
    _seed_room_types(db)
    _seed_rooms(db)
    _seed_rate_plans(db)
    _seed_timeshare_units(db, branch.id)
    _seed_menus(db)
    _seed_dining_tables(db, branch.id)
    _seed_hr_departments(db)

    _seed_inventory_categories(db, branch.id)
    warehouses = _seed_warehouses(db, branch.id)
    primary_warehouse = warehouses["WH-KITCHEN"]
    _seed_inventory_products_full(
        db,
        branch_id=branch.id,
        warehouse_id=primary_warehouse.id,
        moved_by=actor.id,
        movement_reference_type="demo_seed",
        movement_notes=f"{DEMO_NOTE} — رصيد افتتاحي",
    )
    _seed_cross_department_products(db, branch.id, warehouses, actor.id)
    _seed_restaurant_recipes(db)
    _seed_cafe_recipes(db)
    _seed_suppliers_and_draft_procurement(db, branch.id, actor.id)

    _seed_maintenance_catalog(db, branch.id, actor.id)
    _seed_crm_samples(db, branch.id, actor.id)
    _seed_contract_drafts(db, branch.id)
    _seed_beach_reference_data(db, branch.id)
    _seed_hub_drafts(db, branch.id, actor.id)
    db.flush()

    after = _count_models(db)
    financial_keys = (
        "beach_reservations",
        "beach_transactions",
        "bookings",
        "dining_orders",
        "guest_alerts",
        "hub_online_bookings",
        "journal_entries",
        "lease_payments",
        "notifications",
        "payments",
        "payroll_runs",
        "timeshare_installments",
        "users",
    )
    changed_financial = {
        key: after[key] - before[key]
        for key in financial_keys
        if after[key] != before[key]
    }
    if changed_financial:
        raise RuntimeError(
            f"Safety invariant failed; transactional tables changed: {changed_financial}"
        )

    db.add(
        AuditLog(
            user_id=actor.id,
            branch_id=branch.id,
            action=MARKER_ACTION,
            entity_type=MARKER_ENTITY,
            entity_id=branch.id,
            old_data=None,
            new_data=json.dumps(
                {
                    "version": DATASET_VERSION,
                    "synthetic": True,
                    "added": DemoSeedResult(
                        branch.code, DATASET_VERSION, False, before, after
                    ).added,
                    "safety": {
                        "created_users": False,
                        "posted_financial_transactions": False,
                        "created_pending_reminders": False,
                        "published_public_content": False,
                    },
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            ip_address="127.0.0.1",
            user_agent="app.production_demo_seed",
            approved_by=actor.id,
        )
    )
    db.flush()
    return DemoSeedResult(
        branch_code=branch.code,
        version=DATASET_VERSION,
        already_applied=False,
        before=before,
        after=after,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run or apply the controlled El Kheima synthetic dataset."
    )
    parser.add_argument("--branch-code", required=True)
    parser.add_argument("--actor-id", type=int)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.apply and args.confirm != CONFIRMATION_PHRASE:
        raise SystemExit(f"--apply requires --confirm {CONFIRMATION_PHRASE!r}")

    with SessionLocal() as db:
        try:
            result = seed_production_demo_dataset(
                db,
                expected_branch_code=args.branch_code,
                actor_id=args.actor_id,
            )
            payload = {
                "mode": "apply" if args.apply else "dry-run",
                "branch_code": result.branch_code,
                "version": result.version,
                "already_applied": result.already_applied,
                "added": result.added,
            }
            if args.apply:
                db.commit()
            else:
                db.rollback()
            print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
            return 0
        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    raise SystemExit(main())
