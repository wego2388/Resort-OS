export type CockpitLanguage = 'ar' | 'en'

export interface LocalizedText {
  ar: string
  en: string
}

export type ModuleHealth = 'working' | 'attention' | 'deferred'
export type RoadmapStatus = 'complete' | 'ready' | 'queued' | 'locked'
export type RiskSeverity = 'critical' | 'high' | 'medium'
export type WorkMode = 'discuss' | 'plan' | 'implement' | 'review'

export interface ProjectModule {
  id: string
  name: string
  purpose: LocalizedText
  health: ModuleHealth
  note: LocalizedText
}

export interface ProjectDecision {
  id: string
  title: LocalizedText
  summary: LocalizedText
  source: string
  defaultIncluded: boolean
}

export interface RoadmapStep {
  id: string
  track: 'safety' | 'pre_public' | 'dining'
  order: number
  status: RoadmapStatus
  title: LocalizedText
  outcome: LocalizedText
  gate: LocalizedText
}

export interface ProjectRisk {
  id: string
  severity: RiskSeverity
  area: string
  title: LocalizedText
  detail: LocalizedText
}

export interface PromptSuggestion {
  id: string
  title: LocalizedText
  description: LocalizedText
  mode: WorkMode
  scope: string
  phase: string
  objective: LocalizedText
  decisionIds: string[]
}

/**
 * Curated development snapshot derived from wagdy.md and accepted decision
 * records. It is deliberately not presented as live Git/test telemetry.
 * Update this date and the affected entries when Mohamed approves a material
 * project decision or a phase gate is actually completed.
 */
export const PROJECT_SNAPSHOT = {
  product: 'El Kheima Beach Resort OS',
  updatedAt: '2026-07-18',
  sourcePath: 'wagdy.md',
  sourceRevision: '725394b + uncommitted Gate 1B working tree',
  branchAtSnapshot: 'gate-1b-financial-atomicity',
  baseline: {
    modules: 13,
    backendTestsPassed: 1867,
    postgresOnlySkipped: 8,
    alembicHeads: 1,
    alembicHead: '9989c0432ccc',
    productionVpsValidated: false,
  },
} as const

export const PROJECT_MODULES: ProjectModule[] = [
  {
    id: 'core',
    name: 'Core',
    purpose: {
      ar: 'المستخدمون والفروع والمصادقة والصلاحيات والموافقات والإعدادات والتدقيق.',
      en: 'Users, branches, authentication, permissions, approvals, settings, and audit.',
    },
    health: 'attention',
    note: {
      ar: 'Gate 2A مُعتمَدة (2026-07-18): ثوابت أمان السوبر أدمن الأساسية مقفولة. 2FA وقت الدخول والإعدادات المقيّدة لسه البوابة التالية.',
      en: 'Gate 2A accepted (2026-07-18): core Super Admin safety invariants are closed. Login-time 2FA and typed settings are still the next gate.',
    },
  },
  {
    id: 'dining',
    name: 'Dining',
    purpose: {
      ar: 'المطعم والكافيه في مسار واحد: المنيو وPOS وKDS والطلبات والخصم والدفع.',
      en: 'Unified restaurant and café menus, POS, KDS, orders, discounts, and payment workflows.',
    },
    health: 'attention',
    note: {
      ar: 'يعمل، لكن ربط Payment بالكاشير والوردية ومنع الطلب المكرر بالتزامن بوابة مالية حرجة.',
      en: 'Operational, but payment/cashier/shift attribution and concurrent duplicate-order protection remain critical.',
    },
  },
  {
    id: 'finance',
    name: 'Finance',
    purpose: {
      ar: 'القيود المزدوجة والدفعات والخزينة وورديات الكاشير والتقارير المالية.',
      en: 'Double-entry journals, payments, treasury, cashier shifts, and financial reporting.',
    },
    health: 'attention',
    note: {
      ar: 'شريحة دفع Dining أصبحت ذرّية ومُعتمَدة؛ call sites المالية الأخرى وتجاوز قفل الفترة ما زالت تحتاج دفعات مستقلة.',
      en: 'The Dining-paid slice is now atomic and accepted; other financial call sites and period-lock bypasses still need separate batches.',
    },
  },
  {
    id: 'inventory',
    name: 'Inventory',
    purpose: {
      ar: 'الأصناف والمخازن والموردون والشراء والاستلام والحركة والتكلفة.',
      en: 'Products, warehouses, suppliers, purchasing, receiving, movements, and cost.',
    },
    health: 'attention',
    note: {
      ar: 'خصم مخزون Dining داخل الدفع صار مقفولًا وstrict داخل نفس المعاملة؛ الاستدعاءات الأخرى ما زالت تحتاج تدقيقًا.',
      en: 'Dining-paid stock deduction is now locked and strict in one transaction; other callers still need targeted review.',
    },
  },
  {
    id: 'hr',
    name: 'HR',
    purpose: {
      ar: 'الموظفون والحضور والإجازات والورديات والرواتب والخدمة الذاتية.',
      en: 'Employees, attendance, leave, schedules, payroll, and self-service.',
    },
    health: 'attention',
    note: {
      ar: 'المسار قائم؛ اعتماد Payroll قد ينجح مع فشل القيد، ومحاسبة السلف والجزاءات تحتاج قرارًا مستقلًا.',
      en: 'The workflow exists; payroll approval may succeed while posting fails, and advances/penalties accounting needs a separate decision.',
    },
  },
  {
    id: 'pms',
    name: 'PMS',
    purpose: {
      ar: 'الغرف والحجوزات والإقامة والأسعار والتنظيف وعمليات الاستقبال.',
      en: 'Rooms, bookings, stays, rates, housekeeping, and front-office operations.',
    },
    health: 'deferred',
    note: {
      ar: 'المسار يعمل؛ توحيد رؤية إيراد الغرفة مع Finance مؤجل بقرار صريح.',
      en: 'The workflow runs; unified room-revenue recognition with Finance is explicitly deferred.',
    },
  },
  {
    id: 'timeshare',
    name: 'Timeshare',
    purpose: {
      ar: 'العقود والأقساط والزيارات والأسابيع والوحدات وخدمة العملاء.',
      en: 'Contracts, installments, visits, weeks, units, and customer service.',
    },
    health: 'working',
    note: {
      ar: 'وحداته منفصلة عمدًا عن غرف PMS، مع تحصيل ومتابعة وتأخر سداد.',
      en: 'Its units intentionally remain separate from PMS rooms, with collection and overdue tracking.',
    },
  },
  {
    id: 'beach',
    name: 'Beach',
    purpose: {
      ar: 'الدخول والمواقع والسعة والتسعير والبيع المباشر وعقود الشركات.',
      en: 'Entry, locations, capacity, pricing, direct sales, and B2B contracts.',
    },
    health: 'attention',
    note: {
      ar: 'البيع مربوط بالوردية، لكن فشل Folio/ledger قد لا يمنع اكتماله؛ المظلات والبرجولات ستُربط لاحقًا بـService Location.',
      en: 'Sales are shift-attributed, but folio/ledger failure may not block completion; umbrellas and pergolas will later map to Service Location.',
    },
  },
  {
    id: 'crm',
    name: 'CRM',
    purpose: {
      ar: 'العملاء والعملاء المحتملون والحملات والولاء وسجل التواصل.',
      en: 'Customers, leads, campaigns, loyalty, and communication history.',
    },
    health: 'working',
    note: {
      ar: 'المسار موجود؛ البيانات الشخصية تظل محدودة ومشفرة عند الحاجة.',
      en: 'The workflow exists; personal data remains minimized and encrypted where required.',
    },
  },
  {
    id: 'maintenance',
    name: 'Maintenance',
    purpose: {
      ar: 'بلاغات الصيانة والأولوية والتعيين والجدولة والمتابعة والإغلاق.',
      en: 'Maintenance requests, priority, assignment, scheduling, tracking, and closure.',
    },
    health: 'working',
    note: {
      ar: 'يعمل، ويجب أن تظل المسؤولية والحالة ووقت المعالجة واضحة وقابلة للتتبع.',
      en: 'Operational; ownership, status, and response time must remain clear and traceable.',
    },
  },
  {
    id: 'analytics',
    name: 'Analytics',
    purpose: {
      ar: 'لوحات ومؤشرات وتقارير تشغيلية مجمعة من الموديولات.',
      en: 'Dashboards, metrics, and operational reports aggregated from domain modules.',
    },
    health: 'working',
    note: {
      ar: 'كل رقم يجب أن يوضح مصدره وفترته وألا يخفي خطأ باستبداله بصفر.',
      en: 'Every number needs a source and period and must not hide errors by silently becoming zero.',
    },
  },
  {
    id: 'leasing',
    name: 'Leasing',
    purpose: {
      ar: 'عقود إيجار الوحدات التجارية والتحصيل والغرامات والتأمينات.',
      en: 'Commercial-unit leases, collections, penalties, and deposits.',
    },
    health: 'working',
    note: {
      ar: 'العقود والتحصيل مرتبطان بأثر مالي قابل للتتبع.',
      en: 'Contracts and collections remain linked to traceable financial impact.',
    },
  },
  {
    id: 'hub',
    name: 'Hub',
    purpose: {
      ar: 'المحتوى والخدمات العامة والحجوزات والواجهة التي يراها الضيف.',
      en: 'Public content, guest services, online bookings, and guest-facing integration.',
    },
    health: 'attention',
    note: {
      ar: 'الأساس موجود؛ نقل تصميم الموقع القديم وPublic Phase 0 لم يبدآ بعد.',
      en: 'The foundation exists; selective legacy-site migration and Public Phase 0 have not started.',
    },
  },
]

export const PROJECT_DECISIONS: ProjectDecision[] = [
  {
    id: 'brand',
    title: { ar: 'الاسم المعتمد', en: 'Approved brand' },
    summary: { ar: 'الاسم دائمًا El Kheima، وليس Al Kheima.', en: 'The product name is always El Kheima, not Al Kheima.' },
    source: 'wagdy.md',
    defaultIncluded: true,
  },
  {
    id: 'dining-unified',
    title: { ar: 'Dining موحّد', en: 'Unified Dining' },
    summary: { ar: 'لا نعيد إنشاء Restaurant أو Cafe؛ كل تطوير طعام جديد داخل Dining.', en: 'Do not recreate Restaurant or Cafe; all new food-service work stays in Dining.' },
    source: 'AGENTS.md',
    defaultIncluded: true,
  },
  {
    id: 'staff-bilingual',
    title: { ar: 'تطبيق الموظفين بلغتين', en: 'Bilingual staff application' },
    summary: { ar: 'العربية والإنجليزية كاملتان، اختيار المستخدم محفوظ، ولغات public مستقلة.', en: 'Arabic and English are complete, user choice is persisted, and public locales stay independent.' },
    source: 'docs/decisions/0002-staff-app-bilingual-mode.md',
    defaultIncluded: true,
  },
  {
    id: 'currency-independent',
    title: { ar: 'اللغة لا تغيّر المال', en: 'Locale never changes finance' },
    summary: { ar: 'تغيير اللغة لا يغير العملة أو السعر أو الضريبة أو القواعد المالية.', en: 'Changing locale never changes currency, prices, tax, or financial rules.' },
    source: 'docs/decisions/0002-staff-app-bilingual-mode.md',
    defaultIncluded: true,
  },
  {
    id: 'superadmin-safe',
    title: { ar: 'تحكم السوبر أدمن الآمن', en: 'Safe Super Admin control' },
    summary: { ar: 'سلطة إدارية كاملة مع حماية آخر حساب، 2FA، step-up، ولا تجاوز للمال أو audit أو الأسرار.', en: 'Full administration with last-account protection, 2FA, step-up, and no finance/audit/secret bypass.' },
    source: 'docs/decisions/0003-super-admin-control-plane.md',
    defaultIncluded: true,
  },
  {
    id: 'qr-view-call',
    title: { ar: 'QR: عرض وطلب خدمة', en: 'QR: view and call' },
    summary: { ar: 'الوضع الافتراضي view_and_call، ولا يوجد طلب ذاتي مباشر افتراضيًا.', en: 'The default is view_and_call; unrestricted guest self-ordering stays off.' },
    source: 'docs/decisions/0001-qr-guest-service-mode.md',
    defaultIncluded: true,
  },
  {
    id: 'qr-experimental',
    title: { ar: 'QR ما زال تجريبيًا', en: 'QR remains experimental' },
    summary: { ar: 'لا توجد أكواد مطبوعة أو مستخدمة ميدانيًا حاليًا.', en: 'No QR codes are currently printed or deployed in resort operations.' },
    source: 'docs/decisions/0001-qr-guest-service-mode.md',
    defaultIncluded: false,
  },
  {
    id: 'legacy-selective',
    title: { ar: 'استفادة انتقائية من القديم', en: 'Selective legacy reuse' },
    summary: { ar: 'نأخذ التصميم والرحلات المفيدة؛ الباك إند الحالي هو الأساس ولا ننقل الكود أو البيانات القديمة.', en: 'Reuse useful design and workflows; the current backend remains authoritative and legacy code/data is not copied.' },
    source: 'wagdy.md',
    defaultIncluded: true,
  },
  {
    id: 'staged-review',
    title: { ar: 'مرحلة واحدة ومراجعة مستقلة', en: 'One phase and independent review' },
    summary: { ar: 'تغييرات مركزة، اختبارات وdiff، ولا commit أو push قبل مراجعة Mohamed.', en: 'Focused changes, tests and diff, with no commit or push before Mohamed reviews.' },
    source: 'AGENTS.md',
    defaultIncluded: true,
  },
  {
    id: 'finance-first',
    title: { ar: 'المال أولًا', en: 'Finance first' },
    summary: { ar: 'لا float للأموال، لا تعديل صامت للسجلات المنشورة، وكل حركة قابلة للتتبع.', en: 'No floating-point money, no silent edits to posted records, and every movement remains traceable.' },
    source: 'CLAUDE.md',
    defaultIncluded: true,
  },
  {
    id: 'design-operating-system',
    title: { ar: 'الديزاين نظام تشغيل', en: 'Design is an operating system' },
    summary: { ar: 'نصمم حسب سياق POS والويتر وKDS والإدارة والضيف والسوبر أدمن، مع بوابة UX وأدلة لا تجميل صفحات منفردة.', en: 'Design follows POS, waiter, KDS, admin, guest, and Super Admin contexts, with evidence-based UX gates rather than isolated decoration.' },
    source: 'wagdy.md',
    defaultIncluded: true,
  },
  {
    id: 'audit-before-phases',
    title: { ar: 'مراجعة 360° قبل المراحل', en: '360° review before phases' },
    summary: { ar: 'الترتيب يتغير حسب الخطر والتعرض والاعتماديات والدليل؛ لا نسبة تقدم أو تنفيذ آلي.', en: 'Order follows risk, exposure, dependencies, and evidence; no fake progress or direct automation.' },
    source: 'docs/audits/SMART_EXECUTION_ROADMAP.md',
    defaultIncluded: true,
  },
]

export const PROJECT_ROADMAP: RoadmapStep[] = [
  {
    id: 'readiness-baseline',
    track: 'safety',
    order: 0,
    status: 'complete',
    title: { ar: 'مراجعة 360° وعقد الجودة', en: '360° review and quality contract' },
    outcome: { ar: 'توثيق الواقع والمخاطر ومعيار UI/UX قبل إصلاحات المنتج.', en: 'Document reality, risks, and the UI/UX standard before product fixes.' },
    gate: { ar: 'أدلة مؤرخة، Cockpit، وخطة اعتماديات بلا ادعاء production-ready.', en: 'Dated evidence, Cockpit, and dependency plan without production-ready claims.' },
  },
  {
    id: 'public-exposure-containment',
    track: 'safety',
    order: 1,
    status: 'ready',
    title: { ar: 'تحقق التعرض واحتواء Public/QR', en: 'Verify exposure and contain Public/QR' },
    outcome: { ar: 'إذا كان النظام مكشوفًا: إغلاق self-order افتراضيًا وتصحيح سياق الثقة والـrate limiting دون بناء QR كامل.', en: 'If exposed: default-close self-ordering and correct trust context/rate limiting without building full QR.' },
    gate: { ar: 'لا endpoint عام يثق في outlet/table/order ID غير موثوق أو يخالف view_and_call.', en: 'No public endpoint trusts unverified outlet/table/order IDs or violates view_and_call.' },
  },
  {
    id: 'financial-atomicity',
    track: 'safety',
    order: 2,
    status: 'ready',
    title: { ar: 'عقد الذرّية والتسوية المالية', en: 'Financial atomicity and reconciliation contract' },
    outcome: { ar: 'تصنيف كل قيد/Folio/COGS إلى atomic أو outbox/reconciliation ثم إصلاح مسار واحد عالي الخطورة.', en: 'Classify each journal/folio/COGS effect as atomic or outbox/reconciliation, then fix one high-risk path.' },
    gate: { ar: 'Failure-injection يثبت rollback أو حالة reconciliation صريحة قابلة للإعادة.', en: 'Failure injection proves rollback or an explicit, retryable reconciliation state.' },
  },
  {
    id: 'decision-contracts',
    track: 'pre_public',
    order: 1,
    status: 'complete',
    title: { ar: 'تثبيت القرارات والعقود', en: 'Decision and acceptance contracts' },
    outcome: { ar: 'توثيق اللغة والسوبر أدمن وقراءة ميثاق التطوير.', en: 'Record localization and Super Admin decisions and review the development charter.' },
    gate: { ar: 'توثيق فقط؛ لا تغيير في سلوك المنتج.', en: 'Documentation only; no product behavior change.' },
  },
  {
    id: 'superadmin-backend',
    track: 'pre_public',
    order: 2,
    status: 'ready',
    title: { ar: 'أمان السوبر أدمن في الباك إند', en: 'Super Admin backend safeguards' },
    outcome: { ar: 'Gate 2A مُعتمَدة (2026-07-18): منع صريح لا يُسقط super_admin نشط، منع override يستهدفه، حماية self-lockout وآخر حساب نشط تحت تزامن حقيقي. باقي: 2FA وقت الدخول، step-up، والجلسات/التدقيق العام (Gate 2B فأبعد).', en: 'Gate 2A accepted (2026-07-18): explicit deny cannot drop an active super_admin, overrides targeting super_admin are rejected, self-lockout and last-active-account are protected under real concurrency. Remaining: login-time 2FA, step-up, and broader session/audit work (Gate 2B onward).' },
    gate: { ar: 'اختبارات منع التصعيد والقفل الذاتي والتزامن — Gate 2A منها اجتازت مراجعة Codex واعتماد نهائي.', en: 'Privilege-escalation, self-lockout, and concurrency tests — Gate 2A passed Codex review and final acceptance.' },
  },
  {
    id: 'staff-i18n-foundation',
    track: 'pre_public',
    order: 3,
    status: 'queued',
    title: { ar: 'أساس اللغة وحفظ الاختيار', en: 'Locale runtime and preference' },
    outcome: { ar: 'preferred_language آمن، runtime عربي/إنجليزي، واتجاه وتنسيق صحيح.', en: 'Secure preferred_language, Arabic/English runtime, and correct direction/formatting.' },
    gate: { ar: 'اللغة لا تمس العملة أو البيانات المالية.', en: 'Locale changes never alter currency or financial data.' },
  },
  {
    id: 'superadmin-control-center',
    track: 'pre_public',
    order: 4,
    status: 'queued',
    title: { ar: 'مركز تحكم السوبر أدمن', en: 'Super Admin control center' },
    outcome: { ar: 'مستخدمون وصلاحيات فعالة وإعدادات typed وجلسات وتدقيق بلغتين.', en: 'Bilingual users, effective permissions, typed settings, sessions, and audit.' },
    gate: { ar: 'كل حماية حقيقية في السيرفر، وليست إخفاء أزرار.', en: 'Every protection is server-side, not merely hidden controls.' },
  },
  {
    id: 'staff-screen-batches',
    track: 'pre_public',
    order: 5,
    status: 'queued',
    title: { ar: 'ترجمة شاشات الموظفين على دفعات', en: 'Translate staff screens in batches' },
    outcome: { ar: 'Shell ثم POS/KDS ثم الإدارة ثم بقية الموديولات.', en: 'Shell, then POS/KDS, administration, and remaining modules.' },
    gate: { ar: 'لا mass rewrite ولا نصوص أو RTL عشوائية.', en: 'No mass rewrite and no arbitrary copy or direction rules.' },
  },
  {
    id: 'bilingual-quality-gate',
    track: 'pre_public',
    order: 6,
    status: 'locked',
    title: { ar: 'بوابة جودة اللغتين', en: 'Bilingual quality gate' },
    outcome: { ar: 'فحص مفاتيح وترجمة وبناء وتجربة متصفح وطباعة بالاتجاهين.', en: 'Catalog validation, build, browser walkthrough, and printing in both directions.' },
    gate: { ar: 'عربي RTL وإنجليزي LTR على Desktop وPOS وTablet.', en: 'Arabic RTL and English LTR on desktop, POS, and tablet.' },
  },
  {
    id: 'public-phase-zero',
    track: 'pre_public',
    order: 7,
    status: 'ready',
    title: { ar: 'Public Phase 0: تثبيت المرجع', en: 'Public Phase 0: freeze the reference' },
    outcome: { ar: 'خريطة صفحات وصور وأصول وعقود API وقائمة Keep/Adapt/Remove.', en: 'Route map, screenshots, assets, API contracts, and Keep/Adapt/Remove list.' },
    gate: { ar: 'يبدأ الآن كجمع أدلة فقط؛ لا نقل كود أو تغيير API قبل بوابات الإدارة واللغة والسلامة.', en: 'May start now as evidence collection only; no code migration or API changes before the safety, administration, and localization gates.' },
  },
  {
    id: 'dining-payment-integrity',
    track: 'dining',
    order: 1,
    status: 'locked',
    title: { ar: 'سلامة دفع Dining والوردية', en: 'Dining payment and shift integrity' },
    outcome: { ar: 'Payment حقيقي، كاشير ووردية وطريقة دفع وidempotency ومعاملة واحدة.', en: 'Real payment, cashier, shift, method, idempotency, and one transaction boundary.' },
    gate: { ar: 'كل بيع يظهر مرة واحدة فقط في تقرير الوردية والدفتر.', en: 'Every sale appears exactly once in the shift report and ledger.' },
  },
  {
    id: 'qr-guest-service',
    track: 'dining',
    order: 2,
    status: 'locked',
    title: { ar: 'QR وGuest Service الآمن', en: 'Secure QR and guest service' },
    outcome: { ar: 'Service Location وtoken آمن ونداء بلا تكرار وربط الويتر والكاشير.', en: 'Service Location, secure token, deduplicated requests, waiter and cashier integration.' },
    gate: { ar: 'view_and_call أولًا؛ لا أثر مطبخ أو مالي من النداء وحده.', en: 'view_and_call first; a service call alone creates no kitchen or financial action.' },
  },
]

export const PROJECT_RISKS: ProjectRisk[] = [
  {
    id: 'financial-side-effects-fail-open',
    severity: 'critical',
    area: 'finance',
    title: { ar: 'عمليات تشغيلية قد تنجح رغم فشل أثرها المالي', en: 'Operational actions may succeed while their financial effect fails' },
    detail: { ar: 'Finance وHR وDining وBeach وInventory تحتوي call sites تبتلع فشل journal أو folio أو COGS؛ يلزم عقد ذرّية/تسوية واختبارات فشل قبل الإصلاح.', en: 'Finance, HR, Dining, Beach, and Inventory contain call sites that swallow journal, folio, or COGS failures; an atomicity/reconciliation contract and failure tests must precede fixes.' },
  },
  {
    id: 'public-qr-trust-boundary',
    severity: 'critical',
    area: 'dining/public',
    title: { ar: 'حدود Public/QR الحالية غير موثوقة', en: 'Current Public/QR trust boundaries are unsafe' },
    detail: { ar: 'المسارات العامة تستخدم IDs متسلسلة، تسمح self-order، وrate limiter لا يغطي Dining public الجديد؛ هذا يخالف view_and_call.', en: 'Public routes use sequential IDs, allow self-ordering, and the limiter misses new Dining public paths; this conflicts with view_and_call.' },
  },
  {
    id: 'dining-payment-gap',
    severity: 'critical',
    area: 'dining',
    title: { ar: 'بيع Dining لا يملك نسبة كاملة للكاشير والوردية', en: 'Dining sales lack complete cashier and shift attribution' },
    detail: { ar: 'الدفع يحتاج عقدًا مستقلًا يثبت Payment وطريقة الدفع وظهور البيع مرة واحدة في تقرير الوردية.', en: 'Payment needs a dedicated contract proving method, cashier/shift attribution, and exactly-once shift reporting.' },
  },
  {
    id: 'superadmin-lockout',
    severity: 'high',
    area: 'core',
    title: { ar: 'حماية السوبر أدمن — الأساسيات مقفولة، step-up/TOTP باقيان', en: 'Super Admin safety — core invariants closed, step-up/TOTP remain' },
    detail: { ar: 'Gate 2A (مُعتمَدة 2026-07-18) أصلحت explicit deny والـoverrides وحماية آخر حساب نشط تحت تزامن حقيقي. لسه باقي: فرض login-time TOTP فعليًا في الإنتاج، وstep-up عام للعمليات الحساسة (Gate 2B فأبعد).', en: 'Gate 2A (accepted 2026-07-18) fixed explicit denies, overrides, and last-active-account protection under real concurrency. Still open: enforcing login-time TOTP in production and general step-up for sensitive actions (Gate 2B onward).' },
  },
  {
    id: 'staff-localization',
    severity: 'high',
    area: 'core',
    title: { ar: 'الإنجليزية ليست تجربة كاملة بعد', en: 'English is not yet a complete staff experience' },
    detail: { ar: 'معظم الشاشات فيها نص واتجاه وتنسيق عربي hard-coded وكتالوجات placeholder.', en: 'Most screens still contain hard-coded Arabic copy, direction/formatting, and placeholder catalogs.' },
  },
  {
    id: 'duplicate-order-race',
    severity: 'high',
    area: 'dining',
    title: { ar: 'فتح طلبين لنفس المكان ممكن تحت التزامن', en: 'Concurrent duplicate location orders remain possible' },
    detail: { ar: 'الفحص قبل الإنشاء يحتاج قيد قاعدة بيانات أو lock ومعاملة واختبار PostgreSQL.', en: 'The create check needs a database invariant or lock, transaction boundary, and PostgreSQL test.' },
  },
  {
    id: 'deployment-unproven',
    severity: 'high',
    area: 'core',
    title: { ar: 'النشر على VPS حقيقي غير مُثبت', en: 'Real VPS deployment is unproven' },
    detail: { ar: 'ملفات Docker موجودة، لكن لا نعلن production-ready قبل نشر وhealth checks وbackup/restore فعلي.', en: 'Docker assets exist, but production readiness requires real deployment, health checks, and backup/restore evidence.' },
  },
  {
    id: 'frontend-bundle',
    severity: 'medium',
    area: 'hub',
    title: { ar: 'حزم الواجهة الرئيسية كبيرة', en: 'Primary frontend bundles are large' },
    detail: { ar: 'التحذير مهم خصوصًا للموقع العام وQR على شبكة موبايل ضعيفة، ويحتاج قياسًا قبل التحسين.', en: 'This matters especially for public/QR use on slow mobile networks and needs measurement before optimization.' },
  },
  {
    id: 'frontend-quality-gate',
    severity: 'high',
    area: 'frontend',
    title: { ar: 'لا توجد اختبارات Frontend أو Accessibility أو E2E', en: 'No frontend, accessibility, or E2E test gate' },
    detail: { ar: 'الـscripts الحالية تبني وتفحص TypeScript فقط؛ نجاح build لا يثبت التفاعل أو keyboard أو RTL.', en: 'Current scripts build and type-check only; a successful build does not prove interaction, keyboard, or RTL behavior.' },
  },
]

export const PROMPT_SUGGESTIONS: PromptSuggestion[] = [
  {
    id: 'public-trust-audit',
    title: { ar: 'راجع ثبات احتواء Public/QR', en: 'Review Public/QR containment' },
    description: { ar: 'قراءة فقط: تأكد إن Gate 1A لم تتراجع قبل بناء Gate 8.', en: 'Read-only: confirm Gate 1A has not regressed before Gate 8.' },
    mode: 'review',
    scope: 'dining',
    phase: 'qr-guest-service',
    objective: {
      ar: 'راجع Gate 1A قراءة فقط: تأكد إن self-order وguest alerts ما زالوا مقفولين افتراضيًا، وإن متابعة الطلب العامة مغلقة، وفحص الفرع وrate limiting لم يتراجعا. لا تبنِ QR أو Service Location الآن؛ اعرض النتائج فقط.',
      en: 'Review Gate 1A read-only: confirm self-order and guest alerts remain disabled by default, public order tracking remains closed, and branch/rate-limit protections have not regressed. Do not build QR or Service Location now; report findings only.',
    },
    decisionIds: ['brand', 'dining-unified', 'qr-view-call', 'qr-experimental', 'audit-before-phases', 'staged-review'],
  },
  {
    id: 'financial-atomicity-audit',
    title: { ar: 'راجع الذرّية المالية', en: 'Review financial atomicity' },
    description: { ar: 'صنّف journal/folio/COGS fail-open قبل إصلاح call site.', en: 'Classify fail-open journal/folio/COGS effects before fixing a call site.' },
    mode: 'plan',
    scope: 'finance',
    phase: 'financial-atomicity',
    objective: {
      ar: 'راجع call sites الموثقة في PRODUCTION_READINESS_AUDIT التي تبتلع فشل journal أو folio أو COGS. صنّف كل أثر: هل يجب أن يكون atomic داخل transaction أم outbox/reconciliation؟ اختر مسارًا واحدًا أعلى خطورة، وحدد Root Cause وrollback/idempotency واختبارات failure injection، ثم توقف قبل التعديل.',
      en: 'Review the PRODUCTION_READINESS_AUDIT call sites that swallow journal, folio, or COGS failures. Classify each effect as atomic in-transaction or outbox/reconciliation. Select one highest-risk path and define root cause, rollback/idempotency, and failure-injection tests, then stop before editing.',
    },
    decisionIds: ['brand', 'finance-first', 'audit-before-phases', 'staged-review'],
  },
  {
    id: 'experience-baseline',
    title: { ar: 'خطط لتجربة دور محدد', en: 'Plan a role experience baseline' },
    description: { ar: 'حوّل معيار UI/UX إلى رحلة وأدلة قبل تعديل الشاشة.', en: 'Turn the UI/UX standard into a journey and evidence before editing a screen.' },
    mode: 'plan',
    scope: 'core',
    phase: 'staff-i18n-foundation',
    objective: {
      ar: 'اختر رحلة مستخدم واحدة من مركز UI/UX، وافحص شاشاتها الحالية على الجهاز والسياق الحقيقي. اعرض المهمة الأساسية والحالات والصلاحيات وRTL/LTR وkeyboard والتباين واللمس والشبكة والأداء والأدلة المطلوبة. اقترح مرحلة صغيرة ولا تعدل قبل موافقتي.',
      en: 'Choose one user journey from the UI/UX center and inspect its current screens on the real target context. Cover the primary task, states, authorization, RTL/LTR, keyboard, contrast, touch, network, performance, and required evidence. Propose one small phase and do not edit before approval.',
    },
    decisionIds: ['brand', 'design-operating-system', 'staff-bilingual', 'audit-before-phases', 'staged-review'],
  },
  {
    id: 'superadmin-audit',
    title: { ar: 'خطط لـGate 2B — step-up وTOTP وقت الدخول', en: 'Plan Gate 2B — step-up and login-time TOTP' },
    description: { ar: 'Gate 2A مُعتمَدة (explicit deny، overrides، self-lockout، آخر حساب نشط). خطة أمنية فقط للباقي قبل أي تعديل.', en: 'Gate 2A accepted (explicit deny, overrides, self-lockout, last-active-account). Security-only plan for what remains before any edit.' },
    mode: 'plan',
    scope: 'core',
    phase: 'superadmin-backend',
    objective: {
      ar: 'راجع فجوة change_password (تتخطى تحقق كلمة السر الحالية لـadmin/super_admin بالكامل)، وغياب فرض login-time TOTP فعليًا في الإنتاج، وغياب step-up عام للعمليات الحساسة. اعرض Root Cause والملفات والاختبارات وخطة مرحلة واحدة (Gate 2B)، ثم توقف قبل التعديل.',
      en: 'Review the change_password gap (bypasses the current-password check entirely for admin/super_admin), the missing production enforcement of login-time TOTP, and the missing general step-up for sensitive actions. Present root cause, files, tests, and one bounded phase (Gate 2B), then stop before editing.',
    },
    decisionIds: ['brand', 'superadmin-safe', 'audit-before-phases', 'staged-review', 'finance-first'],
  },
  {
    id: 'i18n-foundation',
    title: { ar: 'خطط لأساس العربي والإنجليزي', en: 'Plan the Arabic/English foundation' },
    description: { ar: 'تفضيل المستخدم والاتجاه والتنسيق قبل ترجمة 51 شاشة.', en: 'User preference, direction, and formatting before translating 51 screens.' },
    mode: 'plan',
    scope: 'core',
    phase: 'staff-i18n-foundation',
    objective: {
      ar: 'راجع preferred_language و/auth/me وLanguageSwitcher وi18n وCSS الحالي. صمم مرحلة الأساس فقط لتطبيق الموظفين عربي/إنجليزي، مع بقاء لغات public مستقلة وعدم ربط اللغة بالعملة. اعرض الخطة وانتظر الموافقة.',
      en: 'Review preferred_language, /auth/me, LanguageSwitcher, i18n, and current CSS. Design only the Arabic/English staff-app foundation while public locales remain independent and currency stays separate. Present the plan and wait for approval.',
    },
    decisionIds: ['brand', 'staff-bilingual', 'currency-independent', 'staged-review'],
  },
  {
    id: 'dining-payment',
    title: { ar: 'راجع سلامة دفع Dining', en: 'Review Dining payment integrity' },
    description: { ar: 'اربط البيع بالكاشير والوردية قبل QR والدفع.', en: 'Tie sales to cashier and shift before QR/payment integration.' },
    mode: 'plan',
    scope: 'dining',
    phase: 'dining-payment-integrity',
    objective: {
      ar: 'راجع دورة دفع Dining من الطلب حتى Payment وتقرير الوردية والقيد. أثبت أين تضيع هوية الكاشير والوردية وطريقة الدفع، وحدد transaction وidempotency والمigrations والاختبارات المطلوبة. لا تعدل قبل عرض الخطة.',
      en: 'Review the Dining payment path from order through Payment, shift report, and journal. Prove where cashier, shift, and payment method attribution is lost, then define transaction, idempotency, migration, and test needs. Do not edit before presenting the plan.',
    },
    decisionIds: ['brand', 'dining-unified', 'finance-first', 'staged-review'],
  },
  {
    id: 'public-phase-zero',
    title: { ar: 'نفّذ Public Phase 0 المرجعية', en: 'Execute the Public Phase 0 reference pass' },
    description: { ar: 'جمع أدلة وخريطة مرجع للموقع القديم والحالي، بلا نقل كود.', en: 'Evidence and reference map for the legacy and current public sites, with no code migration.' },
    mode: 'implement',
    scope: 'hub',
    phase: 'public-phase-zero',
    objective: {
      ar: 'اقرأ docs/agent-workflow/PUBLIC_PHASE_0_CLAUDE_HANDOFF.md كاملًا ونفّذه في الحدود المعتمدة. قارن /home/wego/projects/elkheima-beach-resort/frontend بـ frontend/apps/public والـBackend الحالي كمصدر حقيقة. أنشئ مخرجات التوثيق والأدلة فقط، ولا تنقل كودًا ولا تعدل Backend/API/DB/migrations/dependencies ولا تعمل commit أو push. توقف بعد تقرير Phase 0 لمراجعة Codex وMohamed.',
      en: 'Read docs/agent-workflow/PUBLIC_PHASE_0_CLAUDE_HANDOFF.md in full and execute only its approved boundaries. Compare /home/wego/projects/elkheima-beach-resort/frontend with frontend/apps/public, treating the current backend as the source of truth. Create documentation and evidence outputs only; do not migrate code, change backend/API/database/migrations/dependencies, commit, or push. Stop after the Phase 0 report for Codex and Mohamed review.',
    },
    decisionIds: ['brand', 'legacy-selective', 'staged-review'],
  },
  {
    id: 'qr-review',
    title: { ar: 'راجع QR ونداءات الضيوف', en: 'Review QR and guest service' },
    description: { ar: 'مراجعة الموجود فقط وربطه بقرار view_and_call.', en: 'Review the existing implementation against view_and_call.' },
    mode: 'review',
    scope: 'dining',
    phase: 'qr-guest-service',
    objective: {
      ar: 'راجع الكود الحالي للـQR والمنيو العام وGuestAlert والـWebSocket وربط POS قراءةً فقط. رتب الفجوات حسب الخطورة وبيّن ما يعاد استخدامه، مع اعتبار QR تجريبيًا وview_and_call هو الوضع الافتراضي.',
      en: 'Review the current QR, public menu, GuestAlert, WebSocket, and POS integration read-only. Rank gaps by severity and identify reusable parts, treating QR as experimental and view_and_call as the default.',
    },
    decisionIds: ['brand', 'dining-unified', 'qr-view-call', 'qr-experimental', 'staged-review'],
  },
]
