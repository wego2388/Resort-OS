#!/usr/bin/env python3
"""
Script لتعطيل 2FA للموظفين العاديين (اللي مش في MANDATORY_2FA_ROLES).

الموظفين اللي عملوا حسابات قبل التعديل كانوا مجبرين يفعّلوا 2FA.
دلوقتي بعد التعديل، الأدوار العادية (cashier, waiter...) مش محتاجة 2FA.
الـ script ده بيعطّل 2FA للموظفين العاديين بس.

الأدوار المحمية بـ 2FA إجباري (super_admin, accountant, owner) مش هتتأثر.
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.deps import MANDATORY_2FA_ROLES
from app.core.kernel.models.user import User
from app.core.database import SessionLocal


def disable_2fa_for_regular_staff():
    """عطّل 2FA للموظفين العاديين (اللي مش في MANDATORY_2FA_ROLES)."""
    db = SessionLocal()
    try:
        # اجلب كل الموظفين اللي فعّلوا 2FA ومش من الأدوار المميزة
        regular_staff_with_2fa = db.query(User).filter(
            User.two_factor_enabled.is_(True),
            User.role.notin_(MANDATORY_2FA_ROLES),
        ).all()

        if not regular_staff_with_2fa:
            print("✅ مفيش موظفين عاديين محتاجين تعطيل 2FA")
            return

        print(f"🔍 لقينا {len(regular_staff_with_2fa)} موظف عادي فعّل 2FA:")
        for user in regular_staff_with_2fa:
            print(f"   - {user.full_name} ({user.email}) - {user.role}")

        confirm = input("\n⚠️  تعطيل 2FA لهؤلاء الموظفين؟ (yes/no): ")
        if confirm.lower() != "yes":
            print("❌ العملية اتلغت")
            return

        print("\n🔧 بنعطّل 2FA...")
        for user in regular_staff_with_2fa:
            user.two_factor_enabled = False
            user.two_factor_secret = None
            user.two_factor_bootstrap_required = False
            user.two_factor_enrollment_token_hash = None
            user.two_factor_enrollment_expires_at = None
            print(f"   ✓ {user.full_name} ({user.role})")

        db.commit()
        print(f"\n✅ تم تعطيل 2FA لـ {len(regular_staff_with_2fa)} موظف")
        print("الموظفين دول يقدروا دلوقتي يسجلوا دخول ببريدهم وكلمة مرورهم بس")

    except Exception as e:
        db.rollback()
        print(f"❌ حصل خطأ: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    disable_2fa_for_regular_staff()
