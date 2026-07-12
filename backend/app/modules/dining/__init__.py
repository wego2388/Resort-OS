"""app/modules/dining — Unified Dining Platform (Foodics/Toast-style).

يوحّد restaurant + cafe (وأي outlet مستقبلي: بار، بوفيه، Pool Bar،
Rooftop...) على نفس محرك الطلبات/شاشة POS/إدارة الطاولات/KDS/الفواتير
والخصومات والمدفوعات — الاختلاف بين الـ outlets Configuration
(Outlet.outlet_type) مش نسخ كود منفصلة. راجع wagdy.md "المرحلة الثالثة —
المشروع الكبير (Dining Module Merge)" للمواصفة الكاملة، ومذكرة Mohamed
المعمارية الأخيرة لتبرير القرار.

⚠️ Batch A (D-01 → D-04, هذا الموديول): إضافي بالكامل جنب restaurant/cafe
مش بدلهم — الموديولين القديمين لسه المصدر الوحيد للحقيقة (source of truth)
لكل عملية بيع حقيقية حتى D-05 (قرار cutover منفصل، راجع
DINING_CUTOVER_PLAN.md في جذر المشروع)."""
