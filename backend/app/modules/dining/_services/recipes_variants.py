"""
app/modules/dining/_services/recipes_variants.py
Extracted from app/modules/dining/services.py (oversized-file split,
2026-09-07) — services.py re-exports everything below unchanged, so
every existing caller/test keeps working via `services.<name>`.
"""
from __future__ import annotations

from decimal import Decimal
from sqlalchemy.orm import Session
from app.modules.dining import crud
from app.modules.dining.models import DiningItemVariant, DiningItemVariantRecipeLine, DiningItemRecipeLine
from app.modules.dining.schemas import (
    DiningItemRecipeLineCreate,
    DiningItemRecipeLineUpdate,
    DiningItemVariantCreate,
    DiningItemVariantRecipeLineCreate,
    DiningItemVariantRecipeLineUpdate,
    DiningItemVariantUpdate,
)


def build_recipe_line_read(line: DiningItemRecipeLine) -> dict:
    unit_cost = (line.product.cost_price if line.product else None) or Decimal("0")
    return {
        "id": line.id,
        "item_id": line.item_id,
        "product_id": line.product_id,
        "product_name": line.product.name if line.product else "",
        "product_unit": line.product.unit if line.product else "",
        "quantity_per_unit": line.quantity_per_unit,
        "unit_cost": unit_cost,
        "line_cost": (line.quantity_per_unit * unit_cost).quantize(Decimal("0.01")),
        "notes": line.notes,
    }


def add_recipe_line(db: Session, item_id: int, data: DiningItemRecipeLineCreate) -> DiningItemRecipeLine:
    from app.modules.inventory import crud as inventory_crud  # noqa: PLC0415

    item = crud.get_item(db, item_id)
    if not item:
        raise ValueError(f"الصنف {item_id} غير موجود")
    product = inventory_crud.get_product(db, data.product_id)
    if not product:
        raise ValueError(f"المنتج {data.product_id} غير موجود في المخزون")
    if product.branch_id != item.branch_id:
        raise ValueError("المنتج المخزني لازم يكون من نفس فرع الصنف")
    if any(line.product_id == data.product_id for line in item.recipe_lines):
        raise ValueError(f"المنتج '{product.name}' مضاف بالفعل لوصفة هذا الصنف")

    line = crud.create_recipe_line(db, item_id, data)
    db.commit()
    db.refresh(line)
    return line


def update_recipe_line(db: Session, line_id: int, data: DiningItemRecipeLineUpdate) -> DiningItemRecipeLine:
    line = crud.get_recipe_line(db, line_id)
    if not line:
        raise ValueError(f"سطر الوصفة {line_id} غير موجود")
    line = crud.update_recipe_line(db, line, data)
    db.commit()
    db.refresh(line)
    return line


def remove_recipe_line(db: Session, line_id: int) -> None:
    if not crud.delete_recipe_line(db, line_id):
        raise ValueError(f"سطر الوصفة {line_id} غير موجود")
    db.commit()


# ─────────────────────── Variants ──────────────────────────────────────

def compute_variant_cost(variant: DiningItemVariant) -> Decimal:
    total = Decimal("0")
    for line in variant.recipe_lines:
        unit_cost = (line.product.cost_price if line.product else None) or Decimal("0")
        total += line.quantity_per_unit * unit_cost
    return total.quantize(Decimal("0.01"))


def build_variant_recipe_line_read(line: DiningItemVariantRecipeLine) -> dict:
    unit_cost = (line.product.cost_price if line.product else None) or Decimal("0")
    return {
        "id": line.id,
        "variant_id": line.variant_id,
        "product_id": line.product_id,
        "product_name": line.product.name if line.product else "",
        "product_unit": line.product.unit if line.product else "",
        "quantity_per_unit": line.quantity_per_unit,
        "unit_cost": unit_cost,
        "line_cost": (line.quantity_per_unit * unit_cost).quantize(Decimal("0.01")),
        "notes": line.notes,
    }


def build_variant_read(variant: DiningItemVariant) -> dict:
    return {
        "id": variant.id,
        "item_id": variant.item_id,
        "name": variant.name,
        "name_ar": variant.name_ar,
        "price": variant.price,
        "is_available": variant.is_available,
        "sort_order": variant.sort_order,
        "recipe_lines": [build_variant_recipe_line_read(line) for line in variant.recipe_lines],
        "computed_cost": compute_variant_cost(variant),
    }


def add_variant(db: Session, item_id: int, data: DiningItemVariantCreate) -> DiningItemVariant:
    item = crud.get_item(db, item_id)
    if not item:
        raise ValueError(f"الصنف {item_id} غير موجود")
    if any(v.name == data.name for v in item.variants):
        raise ValueError(f"يوجد بالفعل متغيّر بالاسم '{data.name}' لهذا الصنف")

    variant = crud.create_variant(db, item_id, data)
    db.commit()
    db.refresh(variant)
    return variant


def update_variant(db: Session, variant_id: int, data: DiningItemVariantUpdate) -> DiningItemVariant:
    variant = crud.get_variant(db, variant_id)
    if not variant:
        raise ValueError(f"المتغيّر {variant_id} غير موجود")
    variant = crud.update_variant(db, variant, data)
    db.commit()
    db.refresh(variant)
    return variant


def remove_variant(db: Session, variant_id: int) -> None:
    if not crud.delete_variant(db, variant_id):
        raise ValueError(f"المتغيّر {variant_id} غير موجود")
    db.commit()


def add_variant_recipe_line(db: Session, variant_id: int, data: DiningItemVariantRecipeLineCreate) -> DiningItemVariantRecipeLine:
    from app.modules.inventory import crud as inventory_crud  # noqa: PLC0415

    variant = crud.get_variant(db, variant_id)
    if not variant:
        raise ValueError(f"المتغيّر {variant_id} غير موجود")
    product = inventory_crud.get_product(db, data.product_id)
    if not product:
        raise ValueError(f"المنتج {data.product_id} غير موجود في المخزون")
    item = crud.get_item(db, variant.item_id)
    if item and product.branch_id != item.branch_id:
        raise ValueError("المنتج المخزني لازم يكون من نفس فرع الصنف")
    if any(line.product_id == data.product_id for line in variant.recipe_lines):
        raise ValueError(f"المنتج '{product.name}' مضاف بالفعل لوصفة هذا المتغيّر")

    line = crud.create_variant_recipe_line(db, variant_id, data)
    db.commit()
    db.refresh(line)
    return line


def update_variant_recipe_line(db: Session, line_id: int, data: DiningItemVariantRecipeLineUpdate) -> DiningItemVariantRecipeLine:
    line = crud.get_variant_recipe_line(db, line_id)
    if not line:
        raise ValueError(f"سطر الوصفة {line_id} غير موجود")
    line = crud.update_variant_recipe_line(db, line, data)
    db.commit()
    db.refresh(line)
    return line


def remove_variant_recipe_line(db: Session, line_id: int) -> None:
    if not crud.delete_variant_recipe_line(db, line_id):
        raise ValueError(f"سطر الوصفة {line_id} غير موجود")
    db.commit()


# ─────────────────────── Orders ────────────────────────────────────────
