"""app/tasks/inventory_tasks.py — Low stock alerts"""
from __future__ import annotations

import logging

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.tasks.inventory_tasks.check_low_stock", bind=True)
def check_low_stock(self):
    """
    كل يوم 7 صباحاً — تنبيه الأصناف التي وصلت لحد إعادة الطلب.
    """
    try:
        from app.core.database import SessionLocal   # noqa: PLC0415
        from app.modules.core.models import Branch   # noqa: PLC0415

        with SessionLocal() as db:
            try:
                from app.modules.inventory.services import get_low_stock_products  # noqa: PLC0415
                from app.core.kernel.whatsapp import notify_admin  # noqa: PLC0415

                branches = db.query(Branch).filter(Branch.is_active.is_(True)).all()
                for branch in branches:
                    low = get_low_stock_products(db, branch.id)
                    for product in low:
                        logger.warning(
                            "Low stock: branch=%s product=%s sku=%s stock=%s reorder=%s",
                            branch.id, product.name, product.sku,
                            product.current_stock, product.reorder_point,
                        )
                    if low:
                        logger.info("Low stock alert: branch=%s count=%s", branch.id, len(low))
                        names = "، ".join(p.name for p in low[:5])
                        more = f" و{len(low) - 5} صنف آخر" if len(low) > 5 else ""
                        notify_admin(f"تنبيه مخزون: {len(low)} صنف وصل لحد إعادة الطلب — {names}{more}.")

            except ImportError:
                logger.debug("Inventory module not yet built — skipped")

    except Exception as exc:
        logger.error("inventory check_low_stock failed: %s", exc)
