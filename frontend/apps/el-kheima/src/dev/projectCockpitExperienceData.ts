import type { IconName } from '@resort-os/ui'
import type { LocalizedText } from './projectCockpitData'

export type ExperienceSurfaceId = 'pos' | 'waiter' | 'kds' | 'admin' | 'guest' | 'superadmin'
export type EvidenceState = 'verified' | 'risk' | 'needs_audit' | 'external'
export type ReviewSeverity = 'critical' | 'high' | 'medium' | 'foundation'

export interface ExperienceSurface {
  id: ExperienceSurfaceId
  icon: IconName
  title: LocalizedText
  audience: LocalizedText
  environment: LocalizedText
  northStar: LocalizedText
  priorities: LocalizedText[]
  avoid: LocalizedText[]
  measures: LocalizedText[]
  promptScope: string
  promptPhase: string
}

export interface DesignPrinciple {
  id: string
  icon: IconName
  title: LocalizedText
  summary: LocalizedText
  proof: LocalizedText
}

export interface QualityGate {
  id: string
  icon: IconName
  title: LocalizedText
  question: LocalizedText
  evidence: LocalizedText
  appliesTo: Array<ExperienceSurfaceId | 'all'>
  critical: boolean
}

export interface ExperiencePattern {
  id: string
  icon: IconName
  title: LocalizedText
  use: LocalizedText
  rules: LocalizedText[]
}

export interface ResearchReference {
  id: string
  title: string
  publisher: string
  url: string
  contribution: LocalizedText
}

export interface ReadinessLens {
  id: string
  icon: IconName
  title: LocalizedText
  state: EvidenceState
  severity: ReviewSeverity
  finding: LocalizedText
  evidence: LocalizedText
  nextGate: LocalizedText
  scope: string
  phase: string
}

export interface CriticalFinding {
  id: string
  icon: IconName
  severity: 'critical' | 'high'
  title: LocalizedText
  impact: LocalizedText
  evidence: LocalizedText
  action: LocalizedText
  source: string
  scope: string
  phase: string
}

export interface SmartExecutionPhase {
  id: string
  order: number
  status: 'complete' | 'ready' | 'locked' | 'external'
  title: LocalizedText
  purpose: LocalizedText
  dependencies: LocalizedText
  exitGate: LocalizedText
}

export const EXPERIENCE_SURFACES: ExperienceSurface[] = [
  {
    id: 'pos',
    icon: 'cart',
    title: { ar: 'الكاشير وPOS', en: 'Cashier and POS' },
    audience: { ar: 'كاشير يعمل لساعات طويلة وتحت ضغط', en: 'Cashiers working long, high-pressure shifts' },
    environment: { ar: 'Desktop أو شاشة لمس؛ طابور، ضوضاء، وطابعة أو شبكة قد تفشل', en: 'Desktop or touch screen; queues, noise, and possible printer/network failure' },
    northStar: { ar: 'إنهاء البيع الصحيح بأقل تفكير ومن دون تكرار أو مفاجآت مالية.', en: 'Complete the correct sale with minimal thought and no duplicate or financial surprises.' },
    priorities: [
      { ar: 'ملخص الطلب والإجمالي وزر الدفع ظاهرون دائمًا.', en: 'Order summary, total, and payment action remain visible.' },
      { ar: 'أهداف لمس 48px للأفعال المتكررة واختصارات لوحة مفاتيح معلنة.', en: '48px operational touch targets and discoverable keyboard shortcuts.' },
      { ar: 'منع الضغط المكرر وحالة واضحة للطابعة والشبكة والوردية.', en: 'Duplicate-submit prevention and explicit printer, network, and shift state.' },
    ],
    avoid: [
      { ar: 'مودالات متلاحقة أو إخفاء الإجمالي أسفل الصفحة.', en: 'Modal chains or totals hidden below the fold.' },
      { ar: 'خلط أدوات الإدارة الحساسة مع مسار البيع اليومي.', en: 'Mixing sensitive administration into the daily sales flow.' },
    ],
    measures: [
      { ar: 'زمن إضافة صنف ودفع الطلب', en: 'Time to add an item and complete payment' },
      { ar: 'نسبة الضغط المكرر والمعاملات المكررة = صفر', en: 'Duplicate submissions and duplicate transactions = zero' },
      { ar: 'نجاح الاستعادة من فشل الطابعة أو الشبكة', en: 'Recovery success after printer or network failure' },
    ],
    promptScope: 'dining',
    promptPhase: 'dining-payment-integrity',
  },
  {
    id: 'waiter',
    icon: 'mobile',
    title: { ar: 'الويتر والخدمة الميدانية', en: 'Waiter and floor service' },
    audience: { ar: 'ويتر يتحرك بين مطعم وشاطئ ويحمل الجهاز بيد واحدة', en: 'Waiters moving between dining and beach areas, often one-handed' },
    environment: { ar: 'ضوء شمس، شبكة متقطعة، ولمس سريع أثناء الحركة', en: 'Sunlight, intermittent connectivity, and fast touch while moving' },
    northStar: { ar: 'يعرف «مين محتاجني وأين وماذا أفعل الآن؟» في نظرة واحدة.', en: 'Answer “who needs me, where, and what do I do now?” at a glance.' },
    priorities: [
      { ar: 'Queue حسب المنطقة والتكليف وعمر الطلب والأولوية.', en: 'Queue by zone, assignment, request age, and priority.' },
      { ar: 'قبول ووصول وفتح الطلب دون إعادة إدخال الموقع.', en: 'Accept, arrive, and open the order without re-entering location.' },
      { ar: 'حالة اتصال ظاهرة وretry آمن بلا طلبات مكررة.', en: 'Visible connection state and safe retry without duplicate work.' },
    ],
    avoid: [
      { ar: 'إرسال كل نداء لكل موظف أو الاعتماد على اللون وحده.', en: 'Broadcasting every request to everyone or relying on color alone.' },
      { ar: 'قوائم صغيرة أو إجراءات صف كثيرة بلا تسمية.', en: 'Tiny menus or rows full of unlabeled actions.' },
    ],
    measures: [
      { ar: 'زمن الاستلام والوصول والحل', en: 'Acknowledgement, arrival, and resolution time' },
      { ar: 'عدد الطلبات غير المعيّنة أو المنسية', en: 'Unassigned or abandoned requests' },
      { ar: 'نجاح العمل في انقطاع الشبكة واستعادتها', en: 'Offline interruption and recovery success' },
    ],
    promptScope: 'dining',
    promptPhase: 'qr-guest-service',
  },
  {
    id: 'kds',
    icon: 'kitchen',
    title: { ar: 'المطبخ والبار KDS', en: 'Kitchen and bar KDS' },
    audience: { ar: 'طاقم تحضير يقرأ من مسافة وفي بيئة صاخبة', en: 'Preparation staff reading at distance in a noisy environment' },
    environment: { ar: 'شاشة ثابتة، بخار وضوضاء، أولوية للسرعة والتسلسل', en: 'Fixed display, noise and steam, with urgency and sequencing' },
    northStar: { ar: 'التذكرة الصحيحة للمحطة الصحيحة، بترتيب واضح ومن دون فقد تحديث.', en: 'The right ticket at the right station, clearly sequenced with no lost update.' },
    priorities: [
      { ar: 'وقت الطلب والمحطة والموقع والويتر والإضافات مقروءة من بعيد.', en: 'Age, station, location, waiter, and modifiers readable at distance.' },
      { ar: 'الإضافات اللاحقة والإلغاء وإعادة الطباعة مميزة ومدققة.', en: 'Later additions, cancellations, and reprints are distinct and audited.' },
      { ar: 'تنبيه صوتي مساعد فقط مع بديل بصري واضح.', en: 'Sound is supplementary, with an equally clear visual cue.' },
    ],
    avoid: [
      { ar: 'نص صغير أو بطاقات مزخرفة تقلل كثافة المعلومات.', en: 'Small type or decorative cards that reduce useful density.' },
      { ar: 'اختفاء فشل الطابعة أو الاتصال خلف toast مؤقت.', en: 'Hiding printer or connection failures in a transient toast.' },
    ],
    measures: [
      { ar: 'زمن بدء التحضير والإكمال', en: 'Time to start and complete preparation' },
      { ar: 'التذاكر المفقودة أو المعاد إرسالها', en: 'Lost or duplicated tickets' },
      { ar: 'وضوح القراءة على مسافة التشغيل', en: 'Readability at operating distance' },
    ],
    promptScope: 'dining',
    promptPhase: 'dining-payment-integrity',
  },
  {
    id: 'admin',
    icon: 'chart',
    title: { ar: 'الإدارة والمالية', en: 'Administration and finance' },
    audience: { ar: 'مدير، محاسب، HR، ومشرف يحتاجون دقة وكثافة بيانات', en: 'Managers, accountants, HR, and supervisors needing dense, accurate data' },
    environment: { ar: 'Desktop، تقارير طويلة، مقارنات، وفترات عمل ممتدة', en: 'Desktop, long reports, comparisons, and extended sessions' },
    northStar: { ar: 'كل رقم مفهوم المصدر والفترة ويمكن الوصول لتفصيله واتخاذ قرار آمن.', en: 'Every number has a clear source and period, supports drill-down, and enables a safe decision.' },
    priorities: [
      { ar: 'جداول موحدة: بحث وفلاتر وترتيب وتصفح وحفظ السياق.', en: 'Standard tables with search, filters, sorting, pagination, and preserved context.' },
      { ar: 'الأرقام المالية tabular ومحاذاتها وتنسيقها ثابتان.', en: 'Financial numbers use stable tabular alignment and formatting.' },
      { ar: 'الأخطاء بجانب الحقل وفي ملخص قابل للتركيز، مع حفظ المدخلات.', en: 'Errors appear inline and in a focusable summary without losing input.' },
    ],
    avoid: [
      { ar: 'Dashboard مليء برسوم زخرفية أو نسب مضللة عند المقام صفر.', en: 'Decorative dashboards or misleading percentages when the baseline is zero.' },
      { ar: 'عشرات أيقونات بلا أسماء داخل كل صف.', en: 'Rows crowded with unlabeled icon actions.' },
    ],
    measures: [
      { ar: 'زمن الوصول للمعلومة أو الاستثناء', en: 'Time to find a record or exception' },
      { ar: 'أخطاء الإدخال والتراجع عن إجراء حساس', en: 'Input errors and recovery from sensitive actions' },
      { ar: 'تطابق التقرير مع استعلام قابل لإعادة الإنتاج', en: 'Report agreement with a reproducible query' },
    ],
    promptScope: 'finance',
    promptPhase: 'staff-screen-batches',
  },
  {
    id: 'guest',
    icon: 'qrcode',
    title: { ar: 'الضيف والمنيو العام', en: 'Guest and public menu' },
    audience: { ar: 'ضيف بلا حساب، قد لا يعرف النظام أو اللغة الافتراضية', en: 'Guests without accounts who may not know the system or default language' },
    environment: { ar: 'موبايل، شمس قوية، باقة أو Wi-Fi بطيء، ووقت انتباه قصير', en: 'Mobile, bright sunlight, slow data/Wi-Fi, and short attention' },
    northStar: { ar: 'يتأكد من موقعه ويفهم المنيو ويرسل طلب خدمة موثوقًا في ثوانٍ.', en: 'Confirm the location, understand the menu, and send a trusted service request in seconds.' },
    priorities: [
      { ar: 'اسم الموقع واللغة واضحان دائمًا، والمنيو خفيف وسريع.', en: 'Location identity and language stay clear; the menu remains lightweight.' },
      { ar: 'أزرار نداء كبيرة منفصلة مع تأكيد من السيرفر وحالة قابلة للاستعادة.', en: 'Large separated service actions with server acknowledgement and recoverable status.' },
      { ar: 'عرض وحجز خدمة فقط افتراضيًا؛ لا طلب ذاتي مالي مباشر.', en: 'View-and-call by default; no direct financial self-ordering.' },
    ],
    avoid: [
      { ar: 'تأكيد وهمي قبل رد السيرفر أو صور ضخمة على شبكة ضعيفة.', en: 'Optimistic “sent” messages before server acknowledgement or oversized images.' },
      { ar: 'عرض IDs أو بيانات موظف أو تفاصيل دفع داخل الرابط العام.', en: 'Exposing IDs, staff data, or payment detail in public URLs.' },
    ],
    measures: [
      { ar: 'LCP وINP وCLS عند p75', en: 'LCP, INP, and CLS at p75' },
      { ar: 'تحويل scan إلى view ثم service request', en: 'Scan-to-view and view-to-service-request conversion' },
      { ar: 'فشل النداء والتكرار ووقت الاستجابة', en: 'Failed/duplicate requests and response time' },
    ],
    promptScope: 'hub',
    promptPhase: 'qr-guest-service',
  },
  {
    id: 'superadmin',
    icon: 'shield',
    title: { ar: 'مركز السوبر أدمن', en: 'Super Admin control center' },
    audience: { ar: 'مالك نظام يدير مستخدمين وصلاحيات وإعدادات عالية الحساسية', en: 'System owners managing highly sensitive users, permissions, and settings' },
    environment: { ar: 'Desktop موثوق؛ أفعال نادرة لكن أثرها واسع وغير قابل للتهاون', en: 'Trusted desktop; rare actions with broad, high-impact consequences' },
    northStar: { ar: 'قوة إدارية كاملة لكن مقيدة بالهوية والتفسير والتدقيق ومنع القفل الذاتي.', en: 'Full administrative power constrained by identity, explanation, audit, and lockout prevention.' },
    priorities: [
      { ar: 'إظهار الصلاحية الفعالة ومصدرها قبل التغيير.', en: 'Show effective permission and its source before changing it.' },
      { ar: 'Step-up وسبب وpreview للأثر في التغييرات الحساسة.', en: 'Step-up, reason, and impact preview for sensitive changes.' },
      { ar: 'منع تعطيل آخر حساب أو تغيير الذات بشكل خطير داخل السيرفر.', en: 'Server-side prevention of last-account disablement and dangerous self-change.' },
    ],
    avoid: [
      { ar: 'Free-form settings أو save شامل بلا validation.', en: 'Free-form settings or a global save without validation.' },
      { ar: 'اعتبار إخفاء الزر صلاحية حقيقية.', en: 'Treating hidden buttons as real authorization.' },
    ],
    measures: [
      { ar: 'محاولات التصعيد أو القفل الذاتي الممنوعة', en: 'Prevented escalation and self-lockout attempts' },
      { ar: 'اكتمال audit context للأفعال الحساسة', en: 'Audit-context completeness for sensitive actions' },
      { ar: 'نجاح الاستعادة وإبطال الجلسات', en: 'Recovery and session-revocation success' },
    ],
    promptScope: 'core',
    promptPhase: 'superadmin-backend',
  },
]

export const DESIGN_PRINCIPLES: DesignPrinciple[] = [
  { id: 'status', icon: 'eye', title: { ar: 'الحالة مرئية دائمًا', en: 'Always show system status' }, summary: { ar: 'المستخدم يعرف ماذا حدث، وما الذي ينتظر، وهل الاتصال أو الوردية أو الطابعة جاهزة.', en: 'Users know what happened, what is pending, and whether connection, shift, or printer is ready.' }, proof: { ar: 'حالات loading/success/error/offline واختبار status announcement.', en: 'Loading/success/error/offline states plus status-announcement evidence.' } },
  { id: 'prevention', icon: 'shield-warning', title: { ar: 'امنع الخطأ قبل رسالته', en: 'Prevent errors before explaining them' }, summary: { ar: 'التصميم يمنع الضغط المكرر، المبلغ غير المتزن، والمكان أو الصلاحية الخطأ.', en: 'Design prevents duplicate submission, unbalanced money, and wrong location or permission.' }, proof: { ar: 'Server invariant + UI guard + regression test.', en: 'Server invariant + UI guard + regression test.' } },
  { id: 'language', icon: 'chat', title: { ar: 'لغة بشرية مرتبطة بالعمل', en: 'Speak the user’s operational language' }, summary: { ar: 'مصطلحات الكاشير والويتر والضيف، لا أسماء تقنية أو رسائل غامضة.', en: 'Use cashier, waiter, and guest vocabulary rather than technical names or vague errors.' }, proof: { ar: 'مراجعة نص عربي/إنجليزي مع صاحب الرحلة.', en: 'Arabic/English content review with the workflow owner.' } },
  { id: 'consistency', icon: 'grid', title: { ar: 'نظام واحد لا جزر UI', en: 'One system, not UI islands' }, summary: { ar: 'نفس الزر والحالة والجدول والتأكيد يعني الشيء نفسه في كل موديول.', en: 'Buttons, statuses, tables, and confirmations mean the same thing across modules.' }, proof: { ar: 'مكوّن مشترك وتوثيق usage؛ لا نسخة محلية جديدة.', en: 'Shared component and usage guidance; no new local duplicate.' } },
  { id: 'role', icon: 'user', title: { ar: 'كل دور يرى قراره التالي', en: 'Every role sees its next decision' }, summary: { ar: 'التنقل والمعلومات حسب الدور والسياق، مع صلاحية حقيقية في السيرفر.', en: 'Navigation and information match role and context, backed by server authorization.' }, proof: { ar: 'Permission tests + role walkthrough.', en: 'Permission tests + role walkthrough.' } },
  { id: 'accessible', icon: 'verified', title: { ar: 'الإتاحة جزء من التعريف', en: 'Accessibility is part of done' }, summary: { ar: 'Keyboard وfocus وتباين وتسميات وأهداف لمس وreduced motion، لا ترقيع لاحق.', en: 'Keyboard, focus, contrast, labels, touch targets, and reduced motion are built in.' }, proof: { ar: 'Automated check + keyboard + screen-reader spot check.', en: 'Automated check + keyboard + screen-reader spot check.' } },
  { id: 'bidi', icon: 'language', title: { ar: 'العربية والإنجليزية أصلان', en: 'Arabic and English are peers' }, summary: { ar: 'dir على document root وخصائص منطقية وتنسيق أرقام وتواريخ مستقل عن العملة.', en: 'Root document direction, logical CSS, and locale formatting independent of currency.' }, proof: { ar: 'Screenshot وbrowser flow بالاتجاهين.', en: 'Screenshots and browser flow in both directions.' } },
  { id: 'resilient', icon: 'offline', title: { ar: 'صمم للفشل والاستعادة', en: 'Design for failure and recovery' }, summary: { ar: 'الشبكة والطابعة والـAPI قد تفشل؛ لا نفقد المدخلات ولا نؤكد قبل السيرفر.', en: 'Network, printer, and API can fail; input is preserved and success waits for the server.' }, proof: { ar: 'Failure injection وretry/idempotency evidence.', en: 'Failure injection and retry/idempotency evidence.' } },
  { id: 'measure', icon: 'trend', title: { ar: 'قِس الرحلة لا الزينة', en: 'Measure the journey, not decoration' }, summary: { ar: 'نقيس زمن المهمة والأخطاء والاستعادة وWeb Vitals والاستعلامات الحرجة.', en: 'Measure task time, errors, recovery, Web Vitals, and critical queries.' }, proof: { ar: 'Baseline قبل/بعد مع مصدر وفترة.', en: 'Before/after baseline with source and period.' } },
]

export const QUALITY_GATES: QualityGate[] = [
  { id: 'job', icon: 'flag', title: { ar: 'المهمة الأساسية', en: 'Primary job' }, question: { ar: 'هل يفهم المستخدم هدف الشاشة وخطوته التالية خلال ثوانٍ؟', en: 'Can the user understand the screen goal and next action in seconds?' }, evidence: { ar: 'اختبار مهمة مع مستخدم الدور أو walkthrough مسجل.', en: 'Role-user task test or recorded walkthrough.' }, appliesTo: ['all'], critical: true },
  { id: 'authority', icon: 'lock', title: { ar: 'الدور والصلاحية', en: 'Role and authority' }, question: { ar: 'هل يرى أقل ما يلزمه، وهل المنع مثبت في السيرفر؟', en: 'Does the role see only what it needs, with denial enforced server-side?' }, evidence: { ar: 'Permission integration tests وحالة Access Denied.', en: 'Permission integration tests and an Access Denied state.' }, appliesTo: ['all'], critical: true },
  { id: 'hierarchy', icon: 'grid', title: { ar: 'الهرمية والفعل الأول', en: 'Hierarchy and primary action' }, question: { ar: 'هل الإجمالي/الحالة/الفعل المتكرر ظاهر بلا بحث؟', en: 'Are totals, status, and frequent action visible without hunting?' }, evidence: { ar: 'Desktop وtarget-device screenshots.', en: 'Desktop and target-device screenshots.' }, appliesTo: ['all'], critical: false },
  { id: 'states', icon: 'info', title: { ar: 'كل الحالات', en: 'Complete states' }, question: { ar: 'هل loading وempty وerror وoffline وsuccess وdenied مصممة؟', en: 'Are loading, empty, error, offline, success, and denied states designed?' }, evidence: { ar: 'Story/test لكل حالة حرجة.', en: 'Story/test for every critical state.' }, appliesTo: ['all'], critical: true },
  { id: 'forms', icon: 'clipboard-check', title: { ar: 'النماذج والأخطاء', en: 'Forms and errors' }, question: { ar: 'هل labels ظاهرة، الأخطاء مرتبطة، والمدخلات محفوظة عند الفشل؟', en: 'Are labels visible, errors associated, and input preserved after failure?' }, evidence: { ar: 'Keyboard validation test وserver-error simulation.', en: 'Keyboard validation test and server-error simulation.' }, appliesTo: ['admin', 'superadmin', 'pos', 'waiter'], critical: true },
  { id: 'duplicate', icon: 'document-duplicate', title: { ar: 'منع التكرار', en: 'Duplicate prevention' }, question: { ar: 'هل الضغط أو retry مرتين ينتج عملية واحدة فقط؟', en: 'Do repeated clicks or retries create exactly one operation?' }, evidence: { ar: 'Idempotency/concurrency test، لا تعطيل زر فقط.', en: 'Idempotency/concurrency test, not only a disabled button.' }, appliesTo: ['pos', 'waiter', 'guest', 'superadmin'], critical: true },
  { id: 'keyboard', icon: 'key', title: { ar: 'Keyboard وFocus', en: 'Keyboard and focus' }, question: { ar: 'هل الترتيب منطقي والتركيز مرئي والمودال يعيد التركيز؟', en: 'Is tab order logical, focus visible, and modal focus restored?' }, evidence: { ar: 'Keyboard-only walkthrough.', en: 'Keyboard-only walkthrough.' }, appliesTo: ['all'], critical: true },
  { id: 'perception', icon: 'eye', title: { ar: 'التباين والمعنى', en: 'Contrast and meaning' }, question: { ar: 'هل النص مقروء والحالة لا تعتمد على اللون وحده؟', en: 'Is text readable and status independent of color alone?' }, evidence: { ar: 'Contrast check + icon/text status labels.', en: 'Contrast check + icon/text status labels.' }, appliesTo: ['all'], critical: true },
  { id: 'bidi', icon: 'language', title: { ar: 'RTL/LTR والترجمة', en: 'RTL/LTR and localization' }, question: { ar: 'هل الاتجاه على root والنصوص في catalog والمال مستقل؟', en: 'Is direction root-level, copy catalogued, and finance locale-independent?' }, evidence: { ar: 'Arabic/English screenshots وmissing-key check.', en: 'Arabic/English screenshots and missing-key check.' }, appliesTo: ['all'], critical: true },
  { id: 'responsive', icon: 'mobile', title: { ar: 'الجهاز واللمس', en: 'Device and touch' }, question: { ar: 'هل يعمل في الجهاز الحقيقي بأهداف لمس تشغيلية لا تقل عن 44px؟', en: 'Does it work on the real device with operational touch targets of at least 44px?' }, evidence: { ar: 'Viewport matrix وتجربة لمس؛ 48px للمسارات الميدانية.', en: 'Viewport matrix and touch test; 48px for field workflows.' }, appliesTo: ['all'], critical: false },
  { id: 'performance', icon: 'trend', title: { ar: 'الأداء والشبكة', en: 'Performance and network' }, question: { ar: 'هل القياس مناسب للـPOS أو شبكة الضيف البطيئة؟', en: 'Is performance measured for POS or slow guest connectivity?' }, evidence: { ar: 'Bundle/network trace وWeb Vitals أو query budget.', en: 'Bundle/network trace and Web Vitals or query budget.' }, appliesTo: ['pos', 'waiter', 'kds', 'guest'], critical: false },
  { id: 'audit', icon: 'archive', title: { ar: 'الأثر والتدقيق', en: 'Impact and audit' }, question: { ar: 'هل الفعل الحساس يعرض أثره ويطلب سببًا ويُسجل الفاعل؟', en: 'Does a sensitive action preview impact, require reason, and record the actor?' }, evidence: { ar: 'Audit record + reversal/approval test.', en: 'Audit record + reversal/approval test.' }, appliesTo: ['pos', 'admin', 'superadmin'], critical: true },
]

export const EXPERIENCE_PATTERNS: ExperiencePattern[] = [
  { id: 'forms', icon: 'clipboard', title: { ar: 'نموذج آمن', en: 'Safe form' }, use: { ar: 'إنشاء أو تعديل بيانات تشغيلية.', en: 'Creating or editing operational data.' }, rules: [{ ar: 'Label دائم وrequired واضح ومساعدة قبل الخطأ.', en: 'Persistent label, clear required state, and help before error.' }, { ar: 'ملخص أخطاء أعلى النموذج وروابط للحقول مع focus.', en: 'Focusable linked error summary plus inline errors.' }, { ar: 'حفظ المدخلات ومنع duplicate submit.', en: 'Preserve input and prevent duplicate submission.' }] },
  { id: 'tables', icon: 'table', title: { ar: 'جدول تشغيلي', en: 'Operational table' }, use: { ar: 'قوائم إدارية ومراقبة وحالات كثيرة.', en: 'Administrative lists, monitoring, and state-heavy data.' }, rules: [{ ar: 'عنوان ومصدر/فترة ثم search/filter/actions في toolbar.', en: 'Title and source/period, then search/filter/actions in a toolbar.' }, { ar: 'أرقام ومال بمحاذاة ثابتة وsticky header عند الحاجة.', en: 'Stable numeric alignment and sticky header where useful.' }, { ar: 'إجراء شائع ظاهر والباقي في قائمة مسماة.', en: 'One common action visible; the rest in a labelled menu.' }] },
  { id: 'sensitive', icon: 'shield-warning', title: { ar: 'فعل حساس', en: 'Sensitive action' }, use: { ar: 'Refund أو void أو role أو setting أو إغلاق وردية.', en: 'Refund, void, role, setting, or forced shift close.' }, rules: [{ ar: 'شرح أثر قبل التأكيد، لا سؤال عام «هل أنت متأكد؟».', en: 'Explain consequence before confirmation; avoid generic prompts.' }, { ar: 'Permission + step-up/approval + reason حسب السياسة.', en: 'Permission + step-up/approval + reason per policy.' }, { ar: 'لا success قبل transaction وaudit المؤكدين.', en: 'No success before confirmed transaction and audit.' }] },
  { id: 'offline', icon: 'offline', title: { ar: 'انقطاع واستعادة', en: 'Offline and recovery' }, use: { ar: 'QR وPOS والويتر وKDS.', en: 'QR, POS, waiter, and KDS.' }, rules: [{ ar: 'حالة اتصال ثابتة لا toast يختفي.', en: 'Persistent connection state, not a disappearing toast.' }, { ar: 'Retry بنفس idempotency key وحالة pending واضحة.', en: 'Retry with the same idempotency key and clear pending state.' }, { ar: 'التأكيد فقط بعد server acknowledgement.', en: 'Confirm only after server acknowledgement.' }] },
]

export const RESEARCH_REFERENCES: ResearchReference[] = [
  { id: 'wcag', title: 'Web Content Accessibility Guidelines (WCAG) 2.2', publisher: 'W3C', url: 'https://www.w3.org/TR/WCAG22/', contribution: { ar: 'معيار AA، التباين، focus، status messages، reflow، وأمان الإدخال المالي.', en: 'AA criteria for contrast, focus, status messages, reflow, and financial/data input safety.' } },
  { id: 'rtl', title: 'Structural markup and right-to-left text', publisher: 'W3C Internationalization', url: 'https://www.w3.org/International/questions/qa-html-dir', contribution: { ar: 'ضبط `dir` على جذر HTML واستخدام start/end بدل CSS يفرض الاتجاه.', en: 'Set `dir` on the HTML root and use logical start/end instead of forcing direction in CSS.' } },
  { id: 'heuristics', title: '10 Usability Heuristics for User Interface Design', publisher: 'Nielsen Norman Group', url: 'https://www.nngroup.com/articles/ten-usability-heuristics/', contribution: { ar: 'رؤية الحالة، منع الخطأ، التحكم، الاتساق، لغة الواقع، والتعرف بدل التذكر.', en: 'Status visibility, error prevention, user control, consistency, real-world language, and recognition over recall.' } },
  { id: 'errors', title: 'Error summary', publisher: 'GOV.UK Design System', url: 'https://design-system.service.gov.uk/components/error-summary/', contribution: { ar: 'ملخص قابل للتركيز أعلى النموذج مع أخطاء بجانب الحقول وروابط إليها.', en: 'Focusable top-level summary paired with inline, linked field errors.' } },
  { id: 'context', title: 'Making your service accessible', publisher: 'GOV.UK Service Manual', url: 'https://www.gov.uk/service-manual/helping-people-to-use-your-service/making-your-service-accessible-an-introduction', contribution: { ar: 'المستخدم قد يكون متعبًا أو تحت الشمس أو على موبايل وشبكة ضعيفة؛ الإتاحة تبدأ من التصميم.', en: 'Users may be tired, outdoors, mobile, or on slow connections; accessibility starts in design.' } },
  { id: 'tables', title: 'Data table usage', publisher: 'Carbon Design System', url: 'https://carbondesignsystem.com/components/data-table/usage/', contribution: { ar: 'Toolbar منظم، كثافة وصفوف متسقة، pagination، skeleton، وإجراءات محدودة.', en: 'Structured toolbar, consistent density, pagination, skeletons, and restrained actions.' } },
  { id: 'vitals', title: 'Defining Core Web Vitals thresholds', publisher: 'web.dev', url: 'https://web.dev/articles/defining-core-web-vitals-thresholds', contribution: { ar: 'أهداف p75: LCP ≤ 2.5s، INP ≤ 200ms، CLS ≤ 0.1 للموقع العام.', en: 'p75 targets: LCP ≤ 2.5s, INP ≤ 200ms, and CLS ≤ 0.1 for public experiences.' } },
]

export const CRITICAL_FINDINGS: CriticalFinding[] = [
  { id: 'finance-fail-open', icon: 'currency', severity: 'critical', title: { ar: 'باقي آثار مالية قد تُبتلع أخطاؤها', en: 'Other financial side-effect failures remain' }, impact: { ar: 'شريحة دفع Dining اتأمّنت، لكن رواتب ومسارات بيع/مرتجع أخرى قد تنجح بينما يفشل قيد أو أثر مالي.', en: 'The Dining-paid slice is protected, but payroll and other sale/refund paths can still succeed while a financial effect fails.' }, evidence: { ar: 'Gate 1B أثبت وأغلق المسار المختار فقط؛ بقية call sites موثقة كمخاطر مؤجلة.', en: 'Gate 1B proved and closed only the selected path; remaining call sites are documented as deferred risks.' }, action: { ar: 'طبّق نفس منهج atomic/outbox واختبارات الفشل على call site واحد في كل دفعة.', en: 'Apply the same atomic/outbox and failure-test method to one call site per batch.' }, source: 'docs/audits/gate-1b-financial-atomicity-plan.md', scope: 'finance', phase: 'financial-atomicity' },
  { id: 'public-trust', icon: 'qrcode', severity: 'critical', title: { ar: 'QR الكامل ما زال يحتاج token/session آمنين', en: 'Full QR still needs secure tokens and sessions' }, impact: { ar: 'Gate 1A عطلت self-order والتسريب غير الآمنين؛ إعادة فتح الخدمة بلا Service Location آمنة تعيد الخطر.', en: 'Gate 1A disabled unsafe self-ordering and leakage; reopening without secure Service Location context would restore the risk.' }, evidence: { ar: 'Gate 1A مُعتمَدة؛ QR token وguest session وdedupe مؤجلة لـGate 8.', en: 'Gate 1A is accepted; QR tokens, guest sessions, and dedupe are deferred to Gate 8.' }, action: { ar: 'أبقِ الاحتواء فعالًا حتى بناء Gate 8 واختباره end-to-end.', en: 'Keep containment enabled until Gate 8 is built and tested end to end.' }, source: 'docs/audits/PRODUCTION_READINESS_AUDIT.md#c-02--حدود-الثقة-العامة-للـqr-والطلب-الذاتي-لا-تطابق-القرار-المعتمد', scope: 'dining', phase: 'qr-guest-service' },
  { id: 'superadmin', icon: 'shield-warning', severity: 'high', title: { ar: 'حماية الهوية — الأساسيات مُعتمَدة، step-up العام باقٍ', en: 'Identity safeguards — core layers accepted, general step-up remains' }, impact: { ar: 'Gate 2B2 مُعتمَدة: bootstrap محلي آمن، تغيير كلمة مؤقتة إجباري، enrollment مستقل، TOTP fail-closed، وأكواد استرداد أحادية الاستخدام. المتبقي: recent-auth/step-up عام (Gate 2B3، تحليل قراءة فقط جارٍ) والتدقيق الشامل.', en: 'Gate 2B2 is accepted: secure local bootstrap, forced temporary-password replacement, independent enrollment proof, fail-closed TOTP, and single-use recovery codes. Remaining: reusable recent-auth/step-up (Gate 2B3, read-only analysis underway) and comprehensive audit coverage.' }, evidence: { ar: '1,924 اختبارًا ناجحًا + 3 اختبارات تزامن PostgreSQL + دورة migration كاملة + frontend build — أعادت مراجعة Claude المستقلة إنتاجها كلها بنفسها. راجع docs/audits/gate-2b2-totp-bootstrap-recovery.md.', en: '1,924 passing tests, three PostgreSQL concurrency proofs, a full migration cycle, and a frontend build — all independently reproduced by Claude\'s review. See docs/audits/gate-2b2-totp-bootstrap-recovery.md.' }, action: { ar: 'Gate 2B3: صمّم step-up عام قابل لإعادة الاستخدام لتعديل الأدوار والصلاحيات والإعدادات، ثم نفّذه في شريحة مستقلة.', en: 'Gate 2B3: design a reusable general step-up for role, permission, and settings mutations, then implement it as a separate slice.' }, source: 'docs/audits/gate-2b2-totp-bootstrap-recovery.md', scope: 'core', phase: 'superadmin-backend' },
  { id: 'frontend-harness', icon: 'desktop', severity: 'high', title: { ar: 'لا توجد بوابة اختبار Frontend', en: 'No frontend test quality gate' }, impact: { ar: 'يمكن أن ينجح build مع كسر تفاعل أو keyboard أو RTL أو صلاحية مرئية.', en: 'A build can pass while interaction, keyboard, RTL, or visible authorization regresses.' }, evidence: { ar: 'scripts الحالية توفر type-check/build فقط.', en: 'Current scripts provide only type-check and build.' }, action: { ar: 'اختيار minimal lint/component/a11y/smoke harness بعد الأساس.', en: 'Select a minimal lint/component/a11y/smoke harness after the foundation.' }, source: 'frontend/package.json', scope: 'core', phase: 'ui-foundation' },
]

export const READINESS_LENSES: ReadinessLens[] = [
  { id: 'architecture', icon: 'grid', title: { ar: 'Architecture والحدود', en: 'Architecture and boundaries' }, state: 'verified', severity: 'foundation', finding: { ar: 'Modular Monolith وDining موحدان، مع coupling يحتاج تدقيقًا موجهًا.', en: 'The modular monolith and unified Dining are sound foundations, with targeted coupling debt.' }, evidence: { ar: '13 router modules؛ Analytics service يرفع HTTPException.', en: '13 router modules; an Analytics service raises HTTPException.' }, nextGate: { ar: 'Dependency map واختبار service boundaries عند تعديل كل مجال.', en: 'Dependency map and service-boundary tests per changed domain.' }, scope: 'all', phase: 'readiness-baseline' },
  { id: 'database', icon: 'archive', title: { ar: 'Database وMigrations', en: 'Database and migrations' }, state: 'verified', severity: 'foundation', finding: { ar: 'head واحد، وGate 2B2 اجتازت upgrade→downgrade→upgrade على PostgreSQL مؤقتة — أعادت مراجعة Claude المستقلة الدورة كاملة بنفسها. المراجعة model-by-model الشاملة لم تتم بعد.', en: 'One head; Gate 2B2 passed upgrade→downgrade→upgrade on disposable PostgreSQL — Claude\'s independent review reproduced the full cycle itself. The comprehensive model-by-model review remains.' }, evidence: { ar: 'Alembic head = a7c2e91f4b6d (مُعتمَد).', en: 'Alembic head = a7c2e91f4b6d (accepted).' }, nextGate: { ar: 'كل migration جديدة لها data impact وrollback وPostgreSQL test.', en: 'Every new migration needs data impact, rollback, and PostgreSQL tests.' }, scope: 'all', phase: 'readiness-baseline' },
  { id: 'finance', icon: 'currency', title: { ar: 'المال والمحاسبة', en: 'Finance and accounting' }, state: 'risk', severity: 'critical', finding: { ar: 'دفع Dining أصبح atomic؛ fail-open ما زال موجودًا في call sites مالية أخرى.', en: 'Dining payment is now atomic; fail-open behavior remains in other financial call sites.' }, evidence: { ar: '1,867 test + 5 اختبارات PostgreSQL اعتمدت الشريحة المختارة؛ المخاطر المؤجلة موثقة.', en: '1,867 tests plus five PostgreSQL tests accepted the selected slice; deferred risks are documented.' }, nextGate: { ar: 'دفعة واحدة لكل call site مع failure injection وreconciliation واضح.', en: 'One call site per batch with failure injection and an explicit reconciliation contract.' }, scope: 'finance', phase: 'financial-atomicity' },
  { id: 'authorization', icon: 'key', title: { ar: 'الصلاحيات والعزل', en: 'Authorization and isolation' }, state: 'risk', severity: 'high', finding: { ar: 'Gate 2A وGate 2B1 وGate 2B2 مُعتمَدة كلها. عزل النطاق وrecent-auth/step-up العام ما زالا غير مكتملين — Gate 2B3 تحليل قراءة فقط جارٍ.', en: 'Gates 2A, 2B1, and 2B2 are all accepted. Scope isolation and reusable recent-auth/step-up remain incomplete — Gate 2B3 read-only analysis is underway.' }, evidence: { ar: 'last-admin وrefresh/recovery/TOTP consumption مُختبرة تحت تزامن PostgreSQL حقيقي؛ راجع تقارير Gates 2A و2B1 و2B2.', en: 'Last-admin and refresh/recovery/TOTP consumption are tested under real PostgreSQL concurrency; see the Gate 2A, 2B1, and 2B2 reports.' }, nextGate: { ar: 'صمّم ونفّذ recent-auth/step-up (Gate 2B3)، وبعدها عزل الفرع/المنفذ.', en: 'Design and implement recent-auth/step-up (Gate 2B3), then branch/outlet isolation.' }, scope: 'core', phase: 'superadmin-backend' },
  { id: 'public-security', icon: 'qrcode', title: { ar: 'أمان Public وQR', en: 'Public and QR security' }, state: 'verified', severity: 'foundation', finding: { ar: 'Gate 1A احتوت المسارات المكشوفة؛ QR التشغيلي الكامل ما زال مقفولًا.', en: 'Gate 1A contained exposed routes; the full operational QR workflow remains disabled.' }, evidence: { ar: 'self-order/alerts مقفولان افتراضيًا، order status العام مقفول، وفحص الفرع/rate-limit اتصلح.', en: 'Self-order/alerts default off, public order status closed, and branch/rate-limit checks fixed.' }, nextGate: { ar: 'Gate 8: Service Location token/session/dedupe ثم E2E.', en: 'Gate 8: Service Location token/session/dedupe, then E2E proof.' }, scope: 'dining', phase: 'qr-guest-service' },
  { id: 'api', icon: 'link', title: { ar: 'API والعقود', en: 'API and contracts' }, state: 'needs_audit', severity: 'medium', finding: { ar: 'OpenAPI/error middleware موجودان لكن response/error/pagination ليست موحدة بالكامل.', en: 'OpenAPI and error middleware exist, but response/error/pagination contracts are not fully unified.' }, evidence: { ar: 'أكثر من شكل error وrequest ID ليس في كل body.', en: 'Multiple error shapes and request ID absent from some bodies.' }, nextGate: { ar: 'Endpoint inventory وعقد توافق قبل أي refactor.', en: 'Endpoint inventory and compatibility contract before refactoring.' }, scope: 'core', phase: 'readiness-baseline' },
  { id: 'audit', icon: 'clipboard-check', title: { ar: 'Auditability', en: 'Auditability' }, state: 'needs_audit', severity: 'high', finding: { ar: 'AuditLog مركزي جيد، لكن تغطية الأفعال والـretention/immutability لم تُثبت بالكامل.', en: 'Central AuditLog is a solid base, but action coverage and retention/immutability are unproven.' }, evidence: { ar: 'فلاتر وفهارس وapproval actor موجودة.', en: 'Filters, indexes, and approval actor are present.' }, nextGate: { ar: 'Sensitive-action coverage matrix واختبار عدم التعديل.', en: 'Sensitive-action coverage matrix and immutability tests.' }, scope: 'core', phase: 'superadmin-backend' },
  { id: 'frontend', icon: 'desktop', title: { ar: 'Frontend architecture', en: 'Frontend architecture' }, state: 'needs_audit', severity: 'medium', finding: { ar: 'حزم core/ui مشتركة؛ 43 ملفًا بها إشارات any تحتاج تصنيفًا.', en: 'Shared core/ui packages exist; 43 files contain `any` signals needing classification.' }, evidence: { ar: 'Vue/TS build موجود بلا lint/tests.', en: 'Vue/TS builds exist without lint/tests.' }, nextGate: { ar: 'Typed API/state review حسب الرحلة لا mass rewrite.', en: 'Typed API/state review per workflow, not a mass rewrite.' }, scope: 'core', phase: 'ui-foundation' },
  { id: 'design', icon: 'sparkles', title: { ar: 'Design System', en: 'Design system' }, state: 'verified', severity: 'foundation', finding: { ar: 'Tokens و43 مكوّنًا موجودة، لكن adoption غير موحد.', en: 'Tokens and 43 components exist, but adoption is inconsistent.' }, evidence: { ar: '@resort-os/ui مع focus/reduced-motion primitives.', en: '@resort-os/ui with focus/reduced-motion primitives.' }, nextGate: { ar: 'مرجع شاشة لكل سياق ثم migration على batches.', en: 'Reference screen per context, then batched migration.' }, scope: 'core', phase: 'ui-foundation' },
  { id: 'ux', icon: 'user', title: { ar: 'UI/UX التشغيلية', en: 'Operational UI/UX' }, state: 'needs_audit', severity: 'high', finding: { ar: 'السياقات الستة محددة، لكن task testing على الجهاز الحقيقي غير موجود.', en: 'Six experience contexts are defined, but real-device task testing is absent.' }, evidence: { ar: '38 شاشة موظفين و7 عامة تحتاج baseline رحلة.', en: '38 staff and 7 public views need journey baselines.' }, nextGate: { ar: 'Quality contract + target-device walkthrough لكل batch.', en: 'Quality contract + target-device walkthrough per batch.' }, scope: 'core', phase: 'ui-foundation' },
  { id: 'a11y', icon: 'verified', title: { ar: 'Accessibility', en: 'Accessibility' }, state: 'needs_audit', severity: 'high', finding: { ar: 'primitives جيدة، ولا يوجد automated/keyboard/screen-reader gate.', en: 'Primitives are promising, but no automated/keyboard/screen-reader gate exists.' }, evidence: { ar: 'focus-visible وreduced-motion موجودان.', en: 'focus-visible and reduced-motion exist.' }, nextGate: { ar: 'WCAG 2.2 AA audit عملي للرحلات الحرجة.', en: 'Practical WCAG 2.2 AA audit for critical journeys.' }, scope: 'core', phase: 'ui-foundation' },
  { id: 'i18n', icon: 'language', title: { ar: 'اللغة وRTL/LTR', en: 'Localization and RTL/LTR' }, state: 'risk', severity: 'high', finding: { ar: '42 ملفًا يفرض RTL و37 شاشة تحتوي عربية مباشرة.', en: '42 files force RTL and 37 views contain direct Arabic copy.' }, evidence: { ar: 'vue-i18n موجود لكن locale محفوظ في 3 مفاتيح.', en: 'vue-i18n exists, but locale is persisted under three keys.' }, nextGate: { ar: 'Root dir + catalog policy + preferred_language.', en: 'Root direction + catalog policy + preferred_language.' }, scope: 'core', phase: 'staff-i18n-foundation' },
  { id: 'testing', icon: 'clipboard', title: { ar: 'Testing والجودة', en: 'Testing and quality' }, state: 'risk', severity: 'high', finding: { ar: 'Backend واسع؛ Frontend بلا tests/lint/a11y/E2E.', en: 'Backend coverage is broad; frontend has no tests/lint/a11y/E2E.' }, evidence: { ar: '1,937 اختبار Backend يُجمع؛ frontend scripts build/type-check فقط.', en: '1,937 Backend tests collect; frontend scripts only build and type-check.' }, nextGate: { ar: 'Minimal quality harness واختبارات الرحلات المالية والعامة.', en: 'Minimal quality harness plus financial/public journey tests.' }, scope: 'all', phase: 'ui-foundation' },
  { id: 'performance', icon: 'trend', title: { ar: 'Performance', en: 'Performance' }, state: 'needs_audit', severity: 'medium', finding: { ar: 'لا توجد budgets حديثة للـqueries أو bundles أو p75 Web Vitals.', en: 'No current query, bundle, or p75 Web Vitals budgets.' }, evidence: { ar: 'pagination/cache موجودان في أجزاء، لا baseline شامل.', en: 'Pagination/cache exist in parts, without a full baseline.' }, nextGate: { ar: 'قِس POS وPublic قبل optimization.', en: 'Measure POS and Public before optimizing.' }, scope: 'all', phase: 'production' },
  { id: 'realtime', icon: 'online', title: { ar: 'Realtime وOffline', en: 'Realtime and offline' }, state: 'needs_audit', severity: 'high', finding: { ar: 'WebSocket وoffline queue موجودان، لكن dedupe/fallback/recovery غير مثبتة end-to-end.', en: 'WebSocket and offline queue exist, but end-to-end dedupe/fallback/recovery is unproven.' }, evidence: { ar: 'GuestAlertsBell وuseWebSocket/useOfflineQueue.', en: 'GuestAlertsBell and useWebSocket/useOfflineQueue.' }, nextGate: { ar: 'Failure-mode tests قبل QR الميداني.', en: 'Failure-mode tests before field QR.' }, scope: 'dining', phase: 'qr-guest-service' },
  { id: 'observability', icon: 'eye', title: { ar: 'Observability والأخطاء', en: 'Observability and errors' }, state: 'verified', severity: 'foundation', finding: { ar: 'Logs وrequest ID وSentry/health أساس موجود؛ alerts/SLO تحتاج تشغيل فعلي.', en: 'Logs, request ID, Sentry/health foundations exist; alerts/SLOs need real operation.' }, evidence: { ar: 'middleware مركزي وhealth 200 محليًا.', en: 'Central middleware and local HTTP 200 health.' }, nextGate: { ar: 'Runbooks وerror-to-request-id correlation في staging.', en: 'Runbooks and error-to-request-id correlation in staging.' }, scope: 'core', phase: 'production' },
  { id: 'deployment', icon: 'building', title: { ar: 'Deployment وDR', en: 'Deployment and DR' }, state: 'external', severity: 'high', finding: { ar: 'Compose وbackup scripts موجودة؛ VPS/TLS/offsite restore غير مثبتة في هذه الجلسة.', en: 'Compose and backup scripts exist; VPS/TLS/offsite restore are not proven in this session.' }, evidence: { ar: 'dev/prod compose config ينجح.', en: 'Dev/prod compose config passes.' }, nextGate: { ar: 'Staging deploy وmigration/restore/rollback drill.', en: 'Staging deploy plus migration/restore/rollback drill.' }, scope: 'core', phase: 'production' },
  { id: 'dependencies', icon: 'inventory', title: { ar: 'Dependencies وSupply chain', en: 'Dependencies and supply chain' }, state: 'needs_audit', severity: 'medium', finding: { ar: 'Frontend audit نظيف وpip check سليم؛ Python CVE audit لم يُشغّل.', en: 'Frontend audit is clean and pip check passes; Python CVE audit was not run.' }, evidence: { ar: 'pnpm audit --prod وpip check.', en: 'pnpm audit --prod and pip check.' }, nextGate: { ar: 'تجهيز pip-audit/CI بعد قرار الأدوات.', en: 'Introduce pip-audit/CI after toolchain decision.' }, scope: 'core', phase: 'production' },
  { id: 'ci', icon: 'settings', title: { ar: 'CI وتجربة المطور', en: 'CI and developer experience' }, state: 'risk', severity: 'high', finding: { ar: 'agent-check مفيد محليًا، ولا يوجد workflow CI مستضاف.', en: 'The local agent-check is useful, but no hosted CI workflow exists.' }, evidence: { ar: 'لا ملفات .github workflow في اللقطة.', en: 'No .github workflow files in the snapshot.' }, nextGate: { ar: 'بوابات CI مركزة بعد تثبيت أوامر lint/test/build.', en: 'Focused CI gates after lint/test/build commands are settled.' }, scope: 'core', phase: 'production' },
]

export const SMART_EXECUTION_PHASES: SmartExecutionPhase[] = [
  { id: 'baseline', order: 0, status: 'complete', title: { ar: 'خط الأساس ومركز القرار', en: 'Baseline and decision cockpit' }, purpose: { ar: 'مراجعة 360° ومعيار UI/UX وخارطة اعتماديات بلا إصلاحات منتج.', en: '360° review, UI/UX standard, and dependency map without product fixes.' }, dependencies: { ar: 'لا شيء؛ يحمي كل ما بعده.', en: 'None; it protects everything that follows.' }, exitGate: { ar: 'Docs + Cockpit + type-check/build/browser evidence.', en: 'Docs + Cockpit + type-check/build/browser evidence.' } },
  { id: 'containment', order: 1, status: 'complete', title: { ar: 'احتواء الأخطار الحرجة', en: 'Critical-risk containment' }, purpose: { ar: 'Gate 1A احتوت Public، وشريحة Gate 1B أمّنت دفع Dining.', en: 'Gate 1A contained Public exposure and the Gate 1B slice secured Dining payment.' }, dependencies: { ar: 'اعتماد مراجعة Gate 0.', en: 'Approval of Gate 0 review.' }, exitGate: { ar: 'تحقق: لا self-order غير مقصود ولا أثر مالي صامت في المسار المختار.', en: 'Verified: no unintended self-ordering or silent financial loss in the selected path.' } },
  { id: 'admin-security', order: 2, status: 'ready', title: { ar: 'أمان مركز التحكم — Gate 2B2 مُعتمَدة', en: 'Control-plane security — Gate 2B2 accepted' }, purpose: { ar: 'حماية Super Admin والجلسات وTOTP وstep-up والتدقيق.', en: 'Protect Super Admin, sessions, TOTP, step-up, and audit.' }, dependencies: { ar: 'Gate 2A وGate 2B1 وGate 2B2 مُعتمَدة كلها؛ Gate 2B3 (تحليل قراءة فقط جارٍ الآن) للـrecent-auth/step-up والتدقيق الشامل.', en: 'Gates 2A, 2B1, and 2B2 are all accepted; Gate 2B3 (read-only analysis underway now) covers reusable recent-auth/step-up and comprehensive audit coverage.' }, exitGate: { ar: 'bootstrap/TOTP/recovery اتعمد بالدليل — Claude راجع الـdiff كاملًا وأعاد إنتاج كل التحقق بنفسه. المتبقي: إثبات step-up حديث ومربوط بالغرض للأفعال الحساسة.', en: 'bootstrap/TOTP/recovery are accepted with evidence — Claude reviewed the full diff and independently reproduced every verification step. Remaining: prove recent, purpose-bound step-up for sensitive actions.' } },
  { id: 'ui-foundation', order: 3, status: 'locked', title: { ar: 'أساس اللغة والديزاين والاختبار', en: 'Language, design, and test foundation' }, purpose: { ar: 'i18n/RTL/LTR، adoption للمكونات، وquality harness صغير.', en: 'i18n/RTL/LTR, component adoption, and a minimal quality harness.' }, dependencies: { ar: 'Gate 2 للشاشات الحساسة؛ التحليل يمكن قبلها.', en: 'Gate 2 for sensitive screens; analysis may happen earlier.' }, exitGate: { ar: 'شاشات مرجعية صحيحة في السياقات الستة.', en: 'Correct reference screens across the six contexts.' } },
  { id: 'dining', order: 4, status: 'locked', title: { ar: 'Dining المالي والتشغيلي', en: 'Dining finance and operations' }, purpose: { ar: 'Payment/shift/method/idempotency وownership والتزامن.', en: 'Payment/shift/method/idempotency, ownership, and concurrency.' }, dependencies: { ar: 'Gate 1 المالي + سياسات Gate 2.', en: 'Financial Gate 1 + Gate 2 policies.' }, exitGate: { ar: 'كل بيع يظهر مرة واحدة في الوردية والفوليو والدفتر.', en: 'Every sale appears exactly once in shift, folio, and ledger.' } },
  { id: 'staff', order: 5, status: 'locked', title: { ar: 'توحيد تجربة الموظفين', en: 'Unify staff experience' }, purpose: { ar: 'Shell ثم POS/KDS/Admin وبقية الشاشات على دفعات.', en: 'Shell, then POS/KDS/Admin and remaining views in batches.' }, dependencies: { ar: 'Gates 3 و4 حسب الشاشة.', en: 'Gates 3 and 4 as applicable.' }, exitGate: { ar: 'Arabic/English + keyboard + target-device + error states.', en: 'Arabic/English + keyboard + target device + error states.' } },
  { id: 'public-reference', order: 6, status: 'complete', title: { ar: 'Public Phase 0: تثبيت المرجع', en: 'Public Phase 0: freeze the reference' }, purpose: { ar: 'خريطة routes وصور Desktop/Mobile وأصول ومحتوى وAPI وKeep/Adapt/Remove فقط.', en: 'Route map, desktop/mobile screenshots, assets, content, APIs, and Keep/Adapt/Remove only.' }, dependencies: { ar: 'Gate 0 وموافقة Mohamed؛ لا يحتاج تغيير منتج.', en: 'Gate 0 and Mohamed’s approval; no product change is required.' }, exitGate: { ar: 'اكتمل التقرير وراجعته Codex؛ لا كود أو Backend أو بيانات قديمة نُقلت.', en: 'The report is complete and Codex-reviewed; no legacy code, backend, or data was moved.' } },
  { id: 'public-migration', order: 7, status: 'locked', title: { ar: 'نقل الموقع العام على دفعات', en: 'Batched public-site migration' }, purpose: { ar: 'نقل التصميم والصفحات المختارة إلى apps/public مع Backend الحالي.', en: 'Move selected design and pages into apps/public against the current backend.' }, dependencies: { ar: 'Gates 2 و3 + اعتماد مخرجات Phase 0.', en: 'Gates 2 and 3 + approval of Phase 0 outputs.' }, exitGate: { ar: 'Visual/API comparison وبناء واختبار لكل batch.', en: 'Visual/API comparison, build, and tests per batch.' } },
  { id: 'qr', order: 8, status: 'locked', title: { ar: 'QR وGuest Service', en: 'QR and guest service' }, purpose: { ar: 'Service Location/token/session/view_and_call/realtime/dedupe وربط الويتر والكاشير.', en: 'Service Location/token/session/view_and_call/realtime/dedupe plus waiter/cashier integration.' }, dependencies: { ar: 'Public containment + UI foundation + Dining integrity + Public shell.', en: 'Public containment + UI foundation + Dining integrity + Public shell.' }, exitGate: { ar: 'Scan→call→accept→order→pay→close بالعربي والإنجليزي وعلى شبكة ضعيفة.', en: 'Scan→call→accept→order→pay→close in both languages and on a weak network.' } },
  { id: 'production', order: 9, status: 'external', title: { ar: 'دليل الإنتاج الفعلي', en: 'Real production evidence' }, purpose: { ar: 'CI/security/performance/staging/VPS/TLS/backup-restore/rollback.', en: 'CI/security/performance/staging/VPS/TLS/backup-restore/rollback.' }, dependencies: { ar: 'نطاق إصدار مكتمل ومراجع.', en: 'A completed, reviewed release scope.' }, exitGate: { ar: 'فقط الدليل الفعلي يسمح بوصف النطاق production-ready.', en: 'Only real evidence permits calling the scope production-ready.' } },
]
