<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { switchLocale } from '@resort-os/core'
import {
  AppBadge,
  AppButton,
  AppCard,
  AppIcon,
  AppSelect,
  AppTabs,
  AppTextarea,
  SearchInput,
  StatCard,
  useToast,
} from '@resort-os/ui'
import type { IconName, SelectOption, TabItem } from '@resort-os/ui'
import {
  PROJECT_DECISIONS,
  PROJECT_MODULES,
  PROJECT_RISKS,
  PROJECT_ROADMAP,
  PROJECT_SNAPSHOT,
  PROMPT_SUGGESTIONS,
} from '../../dev/projectCockpitData'
import type {
  CockpitLanguage,
  LocalizedText,
  ModuleHealth,
  ProjectRisk,
  RoadmapStatus,
  WorkMode,
} from '../../dev/projectCockpitData'
import {
  CRITICAL_FINDINGS,
  DESIGN_PRINCIPLES,
  EXPERIENCE_PATTERNS,
  EXPERIENCE_SURFACES,
  QUALITY_GATES,
  READINESS_LENSES,
  RESEARCH_REFERENCES,
  SMART_EXECUTION_PHASES,
} from '../../dev/projectCockpitExperienceData'
import type {
  EvidenceState,
  ExperienceSurfaceId,
  ReviewSeverity,
} from '../../dev/projectCockpitExperienceData'

const { locale } = useI18n()
const toast = useToast()

const language = computed<CockpitLanguage>(() => locale.value === 'ar' ? 'ar' : 'en')
const direction = computed(() => language.value === 'ar' ? 'rtl' : 'ltr')
const localize = (value: LocalizedText) => value[language.value]

const COPY = {
  ar: {
    eyebrow: 'غرفة قيادة التطوير',
    title: 'شايف المشروع كله، وقرارك يتحول لتعليمة واضحة',
    subtitle: 'مركز قرار بشري من wagdy.md: مراجعة 360°، تجربة المستخدم، المخاطر، الاعتماديات، وصانع برومبت للشات.',
    devOnly: 'للتطوير فقط',
    superAdminOnly: 'Super Admin',
    snapshot: 'Snapshot يدوي',
    source: 'المصدر',
    branch: 'فرع اللقطة',
    revision: 'مرجع الكود وقت اللقطة',
    copySource: 'نسخ مسار المصدر',
    languageControl: 'لغة غرفة قيادة المشروع',
    metricsAria: 'ملخص المشروع الموثق',
    sourceCopied: 'تم نسخ مسار wagdy.md',
    snapshotWarningTitle: 'دي لوحة قرار وليست شاشة مراقبة حيّة',
    snapshotWarning: 'الأرقام والحالات هنا لقطة مؤرخة. قبل أي قرار تنفيذي لازم الوكيل يعيد فحص Git والكود والاختبارات الفعلية.',
    modulesMetric: 'الموديولات الرئيسية',
    testsMetric: 'آخر suite ناجح',
    migrationMetric: 'Alembic head',
    deploymentMetric: 'VPS إنتاج حقيقي',
    notValidated: 'غير مُثبت',
    overviewTab: 'الصورة العامة',
    readinessTab: 'مراجعة 360°',
    experienceTab: 'مركز UI/UX',
    roadmapTab: 'خارطة الطريق',
    decisionsTab: 'القرارات والمخاطر',
    instructionTab: 'أعطِ تعليمة',
    nextTitle: 'المرحلة التالية بعد checkpoint نظيف',
    nextPrimary: 'ابدأ تدقيق أمان السوبر أدمن',
    nextPrimaryText: 'Gate 1A وشريحة دفع Dining من Gate 1B اتعمدوا. التالي audit محدود لـlast-admin وself-lockout وTOTP وstep-up، ثم خطة مرحلة واحدة قبل التعديل.',
    parallelTitle: 'خطر مالي متبقٍ ومُسجَّل',
    parallelPrimary: 'مسارات مالية أخرى ما زالت تحتاج نفس عقد الذرّية',
    parallelText: 'شريحة دفع Dining اتقفلت؛ نراجع call site ماليًا واحدًا فقط في كل دفعة مع failure injection وreconciliation واضح.',
    smartStarts: 'بدايات ذكية جاهزة',
    smartStartsText: 'اختَر واحدة فتنتقل لصانع التعليمات ومعها النطاق والقرارات المناسبة.',
    useSuggestion: 'استخدم هذه البداية',
    modulesTitle: 'خريطة المشروع',
    modulesText: 'كل كلمة «يعمل» تعني أن له مسارًا وكودًا واختبارات، ولا تعني اعتماد إنتاج نهائي.',
    searchModules: 'ابحث باسم الموديول أو وظيفته…',
    clearSearch: 'مسح بحث الموديولات',
    moduleFilterAria: 'تصفية الموديولات حسب الحالة',
    moduleLabel: 'موديول',
    all: 'الكل',
    working: 'يعمل',
    attention: 'يحتاج انتباه',
    deferred: 'قرار مؤجل',
    noModules: 'لا توجد نتيجة مطابقة.',
    instructModule: 'أعطِ تعليمة لهذا الجزء',
    safetyTrack: 'بوابات السلامة قبل أي مرحلة منتج',
    prePublicTrack: 'المسار الإلزامي قبل Public Phase 0',
    diningTrack: 'المسار المالي والتشغيلي لـDining وQR',
    roadmapText: 'المراحل المغلقة لا تُنفذ قبل اجتياز بوابتها. لا يوجد تقدّم وهمي بالنسبة المئوية.',
    complete: 'مكتمل',
    ready: 'التالي / جاهز للتخطيط',
    queued: 'في الانتظار',
    locked: 'مغلق ببوابة',
    acceptanceGate: 'بوابة القبول',
    experienceEyebrow: 'نظام تشغيل التجربة',
    experienceTitle: 'ست تجارب مختلفة، لغة تصميم واحدة',
    experienceIntro: 'اختَر المستخدم والسياق أولًا. الصفحة تعرض هدفه، قواعده، الأخطاء التي نتجنبها، وطريقة قياس نجاح الرحلة قبل لمس الشاشة.',
    chooseSurface: 'اختر سياق المستخدم',
    audience: 'المستخدم',
    environment: 'بيئة العمل',
    northStar: 'الهدف الأعلى',
    priorities: 'ما يجب أن يكون سريعًا وواضحًا',
    avoid: 'ممنوعات التجربة',
    measures: 'مقاييس الرحلة',
    planSurface: 'حوّل هذه الرحلة لبرومبت تدقيق',
    principlesTitle: 'مبادئ التصميم الملزمة',
    principlesText: 'كل مبدأ يحتاج دليلًا عند التسليم؛ وجوده هنا لا يعني أن الشاشات اجتازته.',
    proofLabel: 'دليل القبول',
    tokenTitle: 'لغة بصرية دلالية لا ألوان عشوائية',
    tokenText: 'اللون يشرح معنى، ولا يحمل المعنى وحده. الأولوية للوضوح في وردية طويلة وضوء شاطئ قوي.',
    tokenPrimary: 'فعل أساسي',
    tokenSuccess: 'مكتمل/ناجح',
    tokenWarning: 'تنبيه/انتظار',
    tokenDanger: 'فشل/إلغاء/مرتجع',
    tokenNeutral: 'هيكل ومعلومات',
    typeTitle: 'هرمية قابلة للمسح السريع',
    typeDisplay: 'إجمالي 1,284.50 EGP',
    typeHeading: 'طلب #D-1042 · مظلة B23',
    typeBody: 'النص التشغيلي مباشر، والأرقام المالية بمحارف tabular.',
    qualityTitle: 'بوابة جودة الشاشة',
    qualityText: 'Worksheet محلي للمناقشة فقط؛ العلامات لا تُحفظ ولا تثبت الجودة. الدليل المذكور هو الذي يغلق البوابة.',
    reviewedCount: 'تمت مناقشته',
    criticalGate: 'إلزامي للمسار',
    appliesToSurface: 'خاص بالسياق المختار',
    patternsTitle: 'أنماط تفاعل موحدة',
    patternUse: 'يُستخدم في',
    researchTitle: 'المرجع المهني وراء المعيار',
    researchText: 'المصادر توجه القرار، لكن القبول النهائي يعتمد على مستخدمي المنتجع والاختبار الفعلي.',
    openReference: 'فتح المرجع',
    readinessEyebrow: 'أدلة قبل العمل',
    readinessTitle: 'الصورة الشاملة قبل مراحل التنفيذ',
    readinessIntro: 'هذه ليست علامة صحة للمشروع. كل عدسة تعرض الدليل الحالي، ما لم يُثبت، وبوابة الخروج التالية.',
    auditDocument: 'نسخ مسار وثيقة المراجعة',
    roadmapDocument: 'نسخ مسار الخطة الذكية',
    criticalFindingsTitle: 'ما غيّر ترتيب الخطة',
    impact: 'الأثر',
    codeEvidence: 'الدليل',
    requiredAction: 'القرار الآمن',
    planFinding: 'حوّلها لبرومبت Root Cause',
    lensesTitle: 'عدسات المراجعة 360°',
    lensesText: 'صفِّ حسب حالة الدليل، لا حسب الرغبة في بدء feature.',
    evidenceFilter: 'تصفية حسب حالة الدليل',
    verified: 'أساس مثبت',
    risk: 'خطر مثبت',
    needsAudit: 'يحتاج تدقيقًا',
    external: 'يحتاج بيئة خارجية',
    foundation: 'أساس',
    currentEvidence: 'الدليل الحالي',
    nextGateLabel: 'بوابة الخروج',
    smartPlanTitle: 'ترتيب تنفيذي يتكيف مع الخطر',
    smartPlanText: 'الأولوية تعتمد على التعرض وشدة الأثر والاعتماديات وقوة الدليل وقابلية الرجوع. ننفذ مرحلة واحدة ثم نراجع.',
    dependsOn: 'يعتمد على',
    phasePurpose: 'الناتج',
    phaseExternal: 'دليل خارجي',
    noFakeScore: 'لا توجد نسبة «جاهزية»؛ لأن جمع مجالات غير متكافئة في رقم واحد يخفي المخاطر الحرجة.',
    decisionsTitle: 'قرارات Mohamed الملزمة',
    decisionsText: 'اختيار القرار هنا يضيفه تلقائيًا إلى البرومبت الذي ستنسخه للشات.',
    included: 'مضاف للتعليمة',
    notIncluded: 'اضغط لإضافته',
    risksTitle: 'المخاطر المعروفة',
    risksText: 'مأخوذة من آخر فحص موثّق وتحتاج إعادة إثبات على commit المهمة قبل الإصلاح.',
    critical: 'حرج',
    high: 'مرتفع',
    medium: 'متوسط',
    composerTitle: 'صانع تعليمات ذكي للشات',
    composerText: 'لن يرسل شيئًا للخارج. هو يرتب قرارك ويضع معه ملفات المصدر والحواجز ثم تنسخه بنفسك.',
    modeLabel: 'نوع العمل المطلوب',
    scopeLabel: 'جزء المشروع',
    phaseLabel: 'المرحلة أو البوابة',
    objectiveLabel: 'ماذا تريد بالضبط؟',
    objectivePlaceholder: 'مثال: افحص سبب إمكانية تعطيل آخر super_admin واعرض الخطة قبل التعديل…',
    allProject: 'المشروع كله',
    selectedDecisions: 'القرارات التي ستدخل في التعليمة',
    evidenceLabel: 'اطلب أدلة وأوامر تحقق فعلية',
    noCommitLabel: 'امنع commit وpush قبل مراجعتي',
    simpleHandoffLabel: 'اشرح النتيجة لي بلغة بشرية وحدّث wagdy.md عند التنفيذ',
    promptPreview: 'البرومبت الجاهز',
    promptPlaceholder: 'اكتب الهدف أو استخدم بداية ذكية ليكتمل البرومبت.',
    copyPrompt: 'نسخ البرومبت للشات',
    promptCopied: 'تم نسخ البرومبت — الصقه في الشات',
    copyFailed: 'تعذر النسخ تلقائيًا؛ حدّد النص وانسخه يدويًا',
    safetyTitle: 'لماذا لا يوجد زر «تنفيذ مباشر»؟',
    safetyText: 'الصفحة لا تحمل token ذكاء اصطناعي ولا تكتب في Git أو قاعدة البيانات. أنت صاحب القرار، والشات يفحص وينفذ داخل المسار المعتمد ثم يعرض لك الـdiff.',
    modes: {
      discuss: 'فهم ورأي فقط — بدون تعديل',
      plan: 'تدقيق وخطة — توقف قبل التنفيذ',
      implement: 'تنفيذ مرحلة واحدة مع الاختبارات',
      review: 'مراجعة مستقلة للـdiff — بدون تعديل',
    },
  },
  en: {
    eyebrow: 'Development control room',
    title: 'See the whole project and turn decisions into precise instructions',
    subtitle: 'A human decision center from wagdy.md: 360° review, user experience, risks, dependencies, and a chat prompt builder.',
    devOnly: 'Development only',
    superAdminOnly: 'Super Admin',
    snapshot: 'Manual snapshot',
    source: 'Source',
    branch: 'Snapshot branch',
    revision: 'Code reference at snapshot',
    copySource: 'Copy source path',
    languageControl: 'Project Cockpit language',
    metricsAria: 'Documented project snapshot',
    sourceCopied: 'wagdy.md path copied',
    snapshotWarningTitle: 'This is a decision board, not live monitoring',
    snapshotWarning: 'Numbers and statuses are dated snapshots. Before implementation, the agent must re-check Git, code, and actual tests.',
    modulesMetric: 'Core modules',
    testsMetric: 'Last passing suite',
    migrationMetric: 'Alembic head',
    deploymentMetric: 'Real production VPS',
    notValidated: 'Not validated',
    overviewTab: 'Overview',
    readinessTab: '360° readiness',
    experienceTab: 'UI/UX center',
    roadmapTab: 'Roadmap',
    decisionsTab: 'Decisions & risks',
    instructionTab: 'Give instruction',
    nextTitle: 'Next phase after a clean checkpoint',
    nextPrimary: 'Begin the Super Admin safety audit',
    nextPrimaryText: 'Gate 1A and the Gate 1B Dining-paid slice are accepted. Next, run a bounded audit of last-admin, self-lockout, TOTP, and step-up safeguards, then plan one phase before editing.',
    parallelTitle: 'Documented residual financial risk',
    parallelPrimary: 'Other financial paths still need the same atomicity contract',
    parallelText: 'The Dining-paid slice is closed; review one financial call site per batch with failure injection and explicit reconciliation.',
    smartStarts: 'Smart starting points',
    smartStartsText: 'Choose one to prefill the composer with the right scope and decisions.',
    useSuggestion: 'Use this starting point',
    modulesTitle: 'Project map',
    modulesText: '“Working” means code, workflow, and tests exist; it is not final production certification.',
    searchModules: 'Search by module or purpose…',
    clearSearch: 'Clear module search',
    moduleFilterAria: 'Filter modules by status',
    moduleLabel: 'Module',
    all: 'All',
    working: 'Working',
    attention: 'Needs attention',
    deferred: 'Deferred decision',
    noModules: 'No matching modules.',
    instructModule: 'Give instruction for this module',
    safetyTrack: 'Safety gates before any product phase',
    prePublicTrack: 'Mandatory track before Public Phase 0',
    diningTrack: 'Dining finance, operations, and QR track',
    roadmapText: 'Locked phases cannot start before their gates pass. No misleading percentage progress is shown.',
    complete: 'Complete',
    ready: 'Next / ready to plan',
    queued: 'Queued',
    locked: 'Gate locked',
    acceptanceGate: 'Acceptance gate',
    experienceEyebrow: 'Experience operating system',
    experienceTitle: 'Six distinct experiences, one design language',
    experienceIntro: 'Choose the user and operating context first. See their goal, rules, failure modes, and journey measures before touching a screen.',
    chooseSurface: 'Choose user context',
    audience: 'User',
    environment: 'Operating environment',
    northStar: 'North star',
    priorities: 'What must stay fast and clear',
    avoid: 'Experience anti-patterns',
    measures: 'Journey measures',
    planSurface: 'Turn this journey into an audit prompt',
    principlesTitle: 'Binding design principles',
    principlesText: 'Every principle needs delivery evidence; listing it here does not mean screens pass it.',
    proofLabel: 'Acceptance evidence',
    tokenTitle: 'Semantic visual language, not random color',
    tokenText: 'Color communicates meaning but never carries it alone. Clarity during long shifts and bright beach light comes first.',
    tokenPrimary: 'Primary action',
    tokenSuccess: 'Complete/success',
    tokenWarning: 'Warning/pending',
    tokenDanger: 'Failure/void/refund',
    tokenNeutral: 'Structure/information',
    typeTitle: 'Scannable hierarchy',
    typeDisplay: 'Total 1,284.50 EGP',
    typeHeading: 'Order #D-1042 · Umbrella B23',
    typeBody: 'Operational copy is direct and financial numerals are tabular.',
    qualityTitle: 'Screen quality gate',
    qualityText: 'This is a local discussion worksheet only; checks are not saved and do not prove quality. The named evidence closes a gate.',
    reviewedCount: 'Discussed',
    criticalGate: 'Journey-critical',
    appliesToSurface: 'Relevant to selected context',
    patternsTitle: 'Standard interaction patterns',
    patternUse: 'Use for',
    researchTitle: 'Professional references behind the standard',
    researchText: 'Sources guide decisions; actual resort users and field testing determine acceptance.',
    openReference: 'Open reference',
    readinessEyebrow: 'Evidence before action',
    readinessTitle: 'The whole-system view before execution phases',
    readinessIntro: 'This is not a project health score. Each lens shows current evidence, what remains unproven, and its next exit gate.',
    auditDocument: 'Copy audit document path',
    roadmapDocument: 'Copy smart roadmap path',
    criticalFindingsTitle: 'Findings that changed the plan order',
    impact: 'Impact',
    codeEvidence: 'Evidence',
    requiredAction: 'Safe action',
    planFinding: 'Turn into a root-cause prompt',
    lensesTitle: '360° review lenses',
    lensesText: 'Filter by evidence state, not by eagerness to start a feature.',
    evidenceFilter: 'Filter by evidence state',
    verified: 'Verified foundation',
    risk: 'Proven risk',
    needsAudit: 'Needs audit',
    external: 'Needs external environment',
    foundation: 'Foundation',
    currentEvidence: 'Current evidence',
    nextGateLabel: 'Exit gate',
    smartPlanTitle: 'Execution order that adapts to risk',
    smartPlanText: 'Priority follows exposure, impact, dependencies, evidence confidence, and reversibility. Execute one phase, then review.',
    dependsOn: 'Depends on',
    phasePurpose: 'Outcome',
    phaseExternal: 'External evidence',
    noFakeScore: 'No readiness percentage is shown; combining unequal domains into one number would hide critical risks.',
    decisionsTitle: 'Mohamed’s binding decisions',
    decisionsText: 'Selecting a decision adds it automatically to the prompt you will copy into chat.',
    included: 'Included in instruction',
    notIncluded: 'Click to include',
    risksTitle: 'Known risks',
    risksText: 'Based on the latest documented review and must be re-proven on the task commit before fixing.',
    critical: 'Critical',
    high: 'High',
    medium: 'Medium',
    composerTitle: 'Smart chat instruction builder',
    composerText: 'Nothing is sent externally. It structures your decision with source files and guardrails, then you copy it yourself.',
    modeLabel: 'Requested work mode',
    scopeLabel: 'Project scope',
    phaseLabel: 'Phase or gate',
    objectiveLabel: 'What do you want exactly?',
    objectivePlaceholder: 'Example: inspect why the last super_admin can be disabled and present a plan before editing…',
    allProject: 'Whole project',
    selectedDecisions: 'Decisions included in the instruction',
    evidenceLabel: 'Require evidence and real validation commands',
    noCommitLabel: 'Prevent commit and push before my review',
    simpleHandoffLabel: 'Explain the outcome plainly and update wagdy.md after implementation',
    promptPreview: 'Ready prompt',
    promptPlaceholder: 'Write an objective or use a smart starting point to complete the prompt.',
    copyPrompt: 'Copy prompt for chat',
    promptCopied: 'Prompt copied — paste it into chat',
    copyFailed: 'Automatic copy failed; select the text and copy it manually',
    safetyTitle: 'Why is there no “execute directly” button?',
    safetyText: 'The page stores no AI token and writes neither Git nor the database. You own the decision; chat inspects and works inside the approved scope, then shows you the diff.',
    modes: {
      discuss: 'Understand and advise only — no edits',
      plan: 'Audit and plan — stop before implementation',
      implement: 'Implement one phase with tests',
      review: 'Independent diff review — no edits',
    },
  },
} as const

const c = computed(() => COPY[language.value])

const tabs = computed<TabItem[]>(() => [
  { value: 'overview', label: c.value.overviewTab },
  { value: 'readiness', label: c.value.readinessTab, count: CRITICAL_FINDINGS.length },
  { value: 'experience', label: c.value.experienceTab },
  { value: 'roadmap', label: c.value.roadmapTab },
  { value: 'decisions', label: c.value.decisionsTab, count: PROJECT_DECISIONS.length },
  { value: 'instruction', label: c.value.instructionTab },
])

const activeTab = ref('overview')
const moduleSearch = ref('')
const moduleHealth = ref<'all' | ModuleHealth>('all')
const activeSurfaceId = ref<ExperienceSurfaceId>('pos')
const reviewedGateIds = ref<string[]>([])
const evidenceFilter = ref<'all' | EvidenceState>('all')

const activeSurface = computed(() => (
  EXPERIENCE_SURFACES.find((surface) => surface.id === activeSurfaceId.value) ?? EXPERIENCE_SURFACES[0]!
))

const relevantQualityGates = computed(() => QUALITY_GATES.filter((gate) => (
  gate.appliesTo.includes('all') || gate.appliesTo.includes(activeSurfaceId.value)
)))

const reviewedRelevantCount = computed(() => relevantQualityGates.value.filter(
  (gate) => reviewedGateIds.value.includes(gate.id),
).length)

const filteredReadinessLenses = computed(() => READINESS_LENSES.filter((lens) => (
  evidenceFilter.value === 'all' || lens.state === evidenceFilter.value
)))

const evidenceStateLabel = (state: EvidenceState) => ({
  verified: c.value.verified,
  risk: c.value.risk,
  needs_audit: c.value.needsAudit,
  external: c.value.external,
}[state])

const evidenceStateVariant = (state: EvidenceState): 'success' | 'danger' | 'warning' | 'info' => ({
  verified: 'success',
  risk: 'danger',
  needs_audit: 'warning',
  external: 'info',
}[state] as 'success' | 'danger' | 'warning' | 'info')

const reviewSeverityLabel = (severity: ReviewSeverity) => ({
  critical: c.value.critical,
  high: c.value.high,
  medium: c.value.medium,
  foundation: c.value.foundation,
}[severity])

const reviewSeverityVariant = (severity: ReviewSeverity): 'danger' | 'warning' | 'info' | 'neutral' => ({
  critical: 'danger',
  high: 'warning',
  medium: 'info',
  foundation: 'neutral',
}[severity] as 'danger' | 'warning' | 'info' | 'neutral')

const healthLabel = (health: ModuleHealth) => ({
  working: c.value.working,
  attention: c.value.attention,
  deferred: c.value.deferred,
}[health])

const healthVariant = (health: ModuleHealth): 'success' | 'warning' | 'neutral' => ({
  working: 'success',
  attention: 'warning',
  deferred: 'neutral',
}[health] as 'success' | 'warning' | 'neutral')

const filteredModules = computed(() => {
  const query = moduleSearch.value.trim().toLocaleLowerCase(language.value)
  return PROJECT_MODULES.filter((module) => {
    if (moduleHealth.value !== 'all' && module.health !== moduleHealth.value) return false
    if (!query) return true
    return [module.name, localize(module.purpose), localize(module.note)]
      .some((value) => value.toLocaleLowerCase(language.value).includes(query))
  })
})

const roadmapStatusLabel = (status: RoadmapStatus) => ({
  complete: c.value.complete,
  ready: c.value.ready,
  queued: c.value.queued,
  locked: c.value.locked,
}[status])

const roadmapStatusVariant = (status: RoadmapStatus): 'success' | 'info' | 'neutral' | 'warning' => ({
  complete: 'success',
  ready: 'info',
  queued: 'neutral',
  locked: 'warning',
}[status] as 'success' | 'info' | 'neutral' | 'warning')

const roadmapIcon = (status: RoadmapStatus): IconName => ({
  complete: 'verified',
  ready: 'sparkles',
  queued: 'clock',
  locked: 'lock',
}[status] as IconName)

const roadmapBorderClass = (status: RoadmapStatus) => ({
  complete: 'border-s-success',
  ready: 'border-s-info',
  queued: 'border-s-border',
  locked: 'border-s-warning',
}[status])

const riskLabel = (severity: ProjectRisk['severity']) => ({
  critical: c.value.critical,
  high: c.value.high,
  medium: c.value.medium,
}[severity])

const riskVariant = (severity: ProjectRisk['severity']): 'danger' | 'warning' | 'info' => ({
  critical: 'danger',
  high: 'warning',
  medium: 'info',
}[severity] as 'danger' | 'warning' | 'info')

const mode = ref<WorkMode>('plan')
const selectedScope = ref('core')
const selectedPhase = ref('superadmin-backend')
const objective = ref('')
const activeSuggestionId = ref<string | null>(null)
const selectedDecisionIds = ref(
  PROJECT_DECISIONS.filter((decision) => decision.defaultIncluded).map((decision) => decision.id),
)
const requireEvidence = ref(true)
const preventCommit = ref(true)
const plainLanguageHandoff = ref(true)

const modeOptions = computed<SelectOption[]>(() => (
  (Object.keys(c.value.modes) as WorkMode[]).map((value) => ({
    value,
    label: c.value.modes[value],
  }))
))

const scopeOptions = computed<SelectOption[]>(() => [
  { value: 'all', label: c.value.allProject },
  ...PROJECT_MODULES.map((module) => ({
    value: module.id,
    label: `${module.name} — ${localize(module.purpose)}`,
  })),
])

const smartPhaseStatusLabel = (status: 'complete' | 'ready' | 'locked' | 'external') => ({
  complete: c.value.complete,
  ready: c.value.ready,
  locked: c.value.locked,
  external: c.value.phaseExternal,
}[status])

const smartPhaseStatusVariant = (status: 'complete' | 'ready' | 'locked' | 'external'): 'success' | 'info' | 'warning' | 'neutral' => ({
  complete: 'success',
  ready: 'info',
  locked: 'warning',
  external: 'neutral',
}[status] as 'success' | 'info' | 'warning' | 'neutral')

const smartPhaseIcon = (status: 'complete' | 'ready' | 'locked' | 'external'): IconName => ({
  complete: 'verified',
  ready: 'sparkles',
  locked: 'lock',
  external: 'building',
}[status] as IconName)

const phaseOptions = computed<SelectOption[]>(() => [
  ...PROJECT_ROADMAP.map((step) => ({
    value: step.id,
    label: `${localize(step.title)} — ${roadmapStatusLabel(step.status)}`,
  })),
  ...SMART_EXECUTION_PHASES
    .filter((phase) => !PROJECT_ROADMAP.some((step) => step.id === phase.id))
    .map((phase) => ({
      value: phase.id,
      label: `${localize(phase.title)} — ${smartPhaseStatusLabel(phase.status)}`,
    })),
])

const selectedDecisionRecords = computed(() => PROJECT_DECISIONS.filter(
  (decision) => selectedDecisionIds.value.includes(decision.id),
))

const scopeRecord = computed(() => PROJECT_MODULES.find((module) => module.id === selectedScope.value))
const phaseRecord = computed(() => PROJECT_ROADMAP.find((step) => step.id === selectedPhase.value))
const smartPhaseRecord = computed(() => SMART_EXECUTION_PHASES.find((step) => step.id === selectedPhase.value))

const generatedPrompt = computed(() => {
  const goal = objective.value.trim()
  if (!goal) return ''

  const scope = selectedScope.value === 'all'
    ? c.value.allProject
    : `${scopeRecord.value?.name ?? selectedScope.value}: ${scopeRecord.value ? localize(scopeRecord.value.purpose) : ''}`
  const phase = phaseRecord.value
    ? localize(phaseRecord.value.title)
    : smartPhaseRecord.value
      ? localize(smartPhaseRecord.value.title)
      : selectedPhase.value
  const decisions = selectedDecisionRecords.value
    .map((decision, index) => `${index + 1}. ${localize(decision.title)} — ${localize(decision.summary)} [${decision.source}]`)
    .join('\n')

  if (language.value === 'ar') {
    const modeRule = {
      discuss: 'افهم وقيّم واشرح رأيك فقط. لا تعدّل أي ملف ولا تنشئ migration ولا commit.',
      plan: 'افحص Root Cause والكود والاختبارات، ثم اعرض خطة مرحلة واحدة والملفات ومعايير القبول وتوقف قبل أي تعديل.',
      implement: 'نفّذ المرحلة المحددة فقط بعد التحقق من حدودها، ثم اختبر وراجع الـdiff ولا توسّع النطاق.',
      review: 'راجع التعديلات الحالية كمراجع مستقل قراءةً فقط. لا تعدّل الملفات، ورتب النتائج Critical ثم High ثم Medium ثم Low مع دليل وإصلاح مقترح.',
    }[mode.value]

    return `أنت تعمل داخل المستودع:\n/home/wego/projects/resort-os\n\nقبل أي عمل اقرأ بالكامل ما يخص المهمة من:\n- AGENTS.md\n- CLAUDE.md\n- wagdy.md\n- docs/decisions/\n- الكود والاختبارات والمigrations المرتبطة\n\nنوع العمل:\n${c.value.modes[mode.value]}\n\nالنطاق:\n${scope}\n\nالمرحلة أو البوابة:\n${phase}\n\nهدفي:\n${goal}\n\nالقرارات الملزمة:\n${decisions || '- لا يوجد قرار مختار؛ ارجع إلى wagdy.md قبل التقدم.'}\n\nطريقة العمل الإلزامية:\n- ${modeRule}\n- استخدم التنفيذ الحالي كمصدر حقيقة وابحث عن الموجود قبل إنشاء أي بديل.\n- حافظ على أعمال المستخدم غير المسجلة ولا تستخدم أوامر Git مدمرة.\n- الصلاحيات الحقيقية في الباك إند، والمال Decimal وقابل للتتبع، والسجلات المنشورة لا تُعدّل بصمت.\n- لا تغيّر public APIs أو migrations أو dependencies إلا بدليل وخطة توافق واضحة.${requireEvidence.value ? '\n- اذكر كل أمر تحقق شغّلته ونتيجته الحقيقية، وافصل فشل البيئة عن فشل الكود.' : ''}${preventCommit.value ? '\n- لا تعمل commit أو push قبل أن أراجع النتيجة وأوافق.' : ''}${plainLanguageHandoff.value ? '\n- اشرح النتيجة لي بالعربي البسيط، وحدّث wagdy.md فقط بما تم فعليًا وما لم يتم.' : ''}\n\nفي النهاية اعرض: ما وجدته، ما فعلته أو تقترحه حسب نوع العمل، الملفات المتأثرة، الاختبارات، المخاطر المتبقية، والخطوة التالية فقط.`
  }

  const modeRule = {
    discuss: 'Understand, assess, and explain only. Do not edit files, create migrations, or commit.',
    plan: 'Inspect root cause, code, and tests; present one bounded phase, expected files, and acceptance criteria, then stop before editing.',
    implement: 'Implement only the selected phase after verifying its boundary, then test and review the diff without expanding scope.',
    review: 'Review current changes independently and read-only. Rank findings Critical, High, Medium, Low with evidence and a proposed fix.',
  }[mode.value]

  return `Work inside this repository:\n/home/wego/projects/resort-os\n\nBefore acting, read the task-relevant parts of:\n- AGENTS.md\n- CLAUDE.md\n- wagdy.md\n- docs/decisions/\n- related code, tests, and migrations\n\nWork mode:\n${c.value.modes[mode.value]}\n\nScope:\n${scope}\n\nPhase or gate:\n${phase}\n\nMy objective:\n${goal}\n\nBinding decisions:\n${decisions || '- No decision selected; consult wagdy.md before proceeding.'}\n\nMandatory working rules:\n- ${modeRule}\n- Treat the current implementation as source of truth and search before creating an alternative.\n- Preserve uncommitted user work and never use destructive Git commands.\n- Enforce authorization on the backend, use Decimal and traceability for money, and never silently edit posted records.\n- Do not change public APIs, migrations, or dependencies without evidence and a compatibility plan.${requireEvidence.value ? '\n- List every validation command and its real result, separating environment failure from code failure.' : ''}${preventCommit.value ? '\n- Do not commit or push before I review and approve the result.' : ''}${plainLanguageHandoff.value ? '\n- Explain the result in plain language and update wagdy.md only with what was actually completed and what remains.' : ''}\n\nFinish with: findings, work performed or proposed for this mode, affected files, tests, remaining risks, and only the next highest-value step.`
})

function toggleDecision(id: string) {
  selectedDecisionIds.value = selectedDecisionIds.value.includes(id)
    ? selectedDecisionIds.value.filter((decisionId) => decisionId !== id)
    : [...selectedDecisionIds.value, id]
}

function useSuggestion(suggestionId: string) {
  const suggestion = PROMPT_SUGGESTIONS.find((item) => item.id === suggestionId)
  if (!suggestion) return
  mode.value = suggestion.mode
  selectedScope.value = suggestion.scope
  selectedPhase.value = suggestion.phase
  objective.value = localize(suggestion.objective)
  activeSuggestionId.value = suggestion.id
  selectedDecisionIds.value = [...suggestion.decisionIds]
  activeTab.value = 'instruction'
}

function instructModule(moduleId: string) {
  const module = PROJECT_MODULES.find((item) => item.id === moduleId)
  if (!module) return
  selectedScope.value = moduleId
  objective.value = language.value === 'ar'
    ? `افحص ${module.name} في ضوء الملاحظة الحالية: ${localize(module.note)}. اشرح السبب والأثر واقترح مرحلة واحدة آمنة قبل التنفيذ.`
    : `Inspect ${module.name} in light of this current note: ${localize(module.note)}. Explain cause and impact and propose one safe phase before implementation.`
  activeSuggestionId.value = null
  mode.value = 'plan'
  activeTab.value = 'instruction'
}

function includeDecisions(ids: string[]) {
  selectedDecisionIds.value = Array.from(new Set([...selectedDecisionIds.value, ...ids]))
}

function planExperienceSurface(surfaceId: ExperienceSurfaceId) {
  const surface = EXPERIENCE_SURFACES.find((item) => item.id === surfaceId)
  if (!surface) return
  activeSurfaceId.value = surfaceId
  selectedScope.value = surface.promptScope
  selectedPhase.value = surface.promptPhase
  mode.value = 'plan'
  activeSuggestionId.value = null
  includeDecisions(['brand', 'design-operating-system', 'staff-bilingual', 'currency-independent', 'audit-before-phases', 'staged-review'])
  objective.value = language.value === 'ar'
    ? `راجع رحلة «${localize(surface.title)}» الحالية قراءةً فقط في سياقها الفعلي: ${localize(surface.environment)}. الهدف الأعلى: ${localize(surface.northStar)}. استخدم بوابة UI/UX في wagdy.md ومركز المشروع لتقييم المهمة الأساسية والصلاحيات والحالات والأخطاء وRTL/LTR وkeyboard والتباين واللمس والشبكة والأداء والتدقيق. اعرض الأدلة الناقصة وأصغر مرحلة آمنة ومعايير قبولها، ثم توقف قبل التعديل.`
    : `Review the current “${localize(surface.title)}” journey read-only in its real operating context: ${localize(surface.environment)}. North star: ${localize(surface.northStar)}. Use the UI/UX gate in wagdy.md and the project cockpit to assess the primary job, authorization, states, errors, RTL/LTR, keyboard, contrast, touch, network, performance, and auditability. Present missing evidence and the smallest safe phase with acceptance criteria, then stop before editing.`
  activeTab.value = 'instruction'
}

function planReadinessLens(lensId: string) {
  const lens = READINESS_LENSES.find((item) => item.id === lensId)
  if (!lens) return
  selectedScope.value = lens.scope
  selectedPhase.value = lens.phase
  mode.value = 'plan'
  activeSuggestionId.value = null
  includeDecisions(['brand', 'audit-before-phases', 'staged-review', 'finance-first'])
  objective.value = language.value === 'ar'
    ? `راجع عدسة «${localize(lens.title)}» قراءةً فقط. الدليل الحالي: ${localize(lens.evidence)}. النتيجة الحالية: ${localize(lens.finding)}. أثبت أو انقض ذلك من الكود والاختبارات، ثم صمم بوابة الخروج التالية: ${localize(lens.nextGate)}. اعرض Root Cause والنطاق والاعتماديات ومعايير القبول، وتوقف قبل أي تعديل.`
    : `Review the “${localize(lens.title)}” lens read-only. Current evidence: ${localize(lens.evidence)}. Current finding: ${localize(lens.finding)}. Prove or disprove it from code and tests, then design the next exit gate: ${localize(lens.nextGate)}. Present root cause, scope, dependencies, and acceptance criteria, then stop before editing.`
  activeTab.value = 'instruction'
}

function planCriticalFinding(findingId: string) {
  const finding = CRITICAL_FINDINGS.find((item) => item.id === findingId)
  if (!finding) return
  selectedScope.value = finding.scope
  selectedPhase.value = finding.phase
  mode.value = 'plan'
  activeSuggestionId.value = null
  includeDecisions(['brand', 'audit-before-phases', 'staged-review', 'finance-first'])
  objective.value = language.value === 'ar'
    ? `راجع Root Cause للمشكلة «${localize(finding.title)}» قراءةً فقط. الأثر: ${localize(finding.impact)}. الدليل المبدئي: ${localize(finding.evidence)} [${finding.source}]. تحقق بنفسك، وحدد أصغر مرحلة آمنة وقابلة للرجوع واختبارات الفشل/الأمان المطلوبة، ثم توقف قبل التعديل.`
    : `Review the root cause of “${localize(finding.title)}” read-only. Impact: ${localize(finding.impact)}. Preliminary evidence: ${localize(finding.evidence)} [${finding.source}]. Verify it independently, define the smallest safe reversible phase and required failure/security tests, then stop before editing.`
  activeTab.value = 'instruction'
}

async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
      return true
    }
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.setAttribute('readonly', '')
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    const copied = document.execCommand('copy')
    textarea.remove()
    return copied
  } catch {
    return false
  }
}

async function copySourcePath() {
  const copied = await copyText(PROJECT_SNAPSHOT.sourcePath)
  copied ? toast.success(c.value.sourceCopied) : toast.error(c.value.copyFailed)
}

async function copyDocumentPath(path: string) {
  const copied = await copyText(path)
  copied ? toast.success(language.value === 'ar' ? `تم نسخ المسار: ${path}` : `Path copied: ${path}`) : toast.error(c.value.copyFailed)
}

async function copyPrompt() {
  if (!generatedPrompt.value) return
  const copied = await copyText(generatedPrompt.value)
  copied ? toast.success(c.value.promptCopied) : toast.error(c.value.copyFailed)
}

async function selectLanguage(nextLanguage: CockpitLanguage) {
  const activeSuggestion = PROMPT_SUGGESTIONS.find((item) => item.id === activeSuggestionId.value)
  if (activeSuggestion && objective.value === activeSuggestion.objective[language.value]) {
    objective.value = activeSuggestion.objective[nextLanguage]
  }
  await switchLocale(nextLanguage)
}
</script>

<template>
  <div :dir="direction" class="mx-auto max-w-[1600px] space-y-6 text-gray-900 dark:text-gray-100">
    <section class="relative overflow-hidden rounded-2xl bg-primary-900 px-5 py-6 text-white shadow-elevation-2 sm:px-8 sm:py-8">
      <div class="absolute inset-y-0 end-0 w-1.5 bg-secondary" aria-hidden="true" />
      <div class="relative flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
        <div class="max-w-4xl">
          <div class="mb-4 flex flex-wrap items-center gap-2">
            <AppBadge variant="warning">{{ c.devOnly }}</AppBadge>
            <AppBadge variant="info">{{ c.superAdminOnly }}</AppBadge>
            <span class="rounded-full border border-white/20 px-3 py-1 text-xs text-blue-100">
              {{ c.snapshot }} · {{ PROJECT_SNAPSHOT.updatedAt }}
            </span>
          </div>
          <p class="mb-2 text-xs font-bold uppercase tracking-[0.22em] text-gold-light">{{ c.eyebrow }}</p>
          <h1 class="max-w-3xl text-2xl font-black leading-tight sm:text-3xl lg:text-4xl">{{ c.title }}</h1>
          <p class="mt-3 max-w-3xl text-sm leading-7 text-blue-100 sm:text-base">{{ c.subtitle }}</p>
        </div>

        <div class="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center">
          <div class="inline-flex rounded-xl border border-white/20 bg-white/10 p-1" :aria-label="c.languageControl">
            <button
              v-for="lang in (['ar', 'en'] as const)"
              :key="lang"
              type="button"
              :aria-pressed="language === lang"
              :class="[
                'min-h-10 rounded-lg px-4 text-sm font-bold transition-colors',
                language === lang ? 'bg-white text-primary-900 shadow-sm' : 'text-white hover:bg-white/10',
              ]"
              @click="selectLanguage(lang)"
            >
              {{ lang === 'ar' ? 'العربية' : 'English' }}
            </button>
          </div>
          <AppButton variant="secondary" type="button" @click="copySourcePath">
            <AppIcon name="document" size="sm" />
            {{ c.copySource }}
          </AppButton>
        </div>
      </div>

      <div class="relative mt-6 flex flex-wrap gap-x-6 gap-y-2 border-t border-white/10 pt-4 text-xs text-blue-100">
        <span><strong class="text-white">{{ c.source }}:</strong> {{ PROJECT_SNAPSHOT.sourcePath }}</span>
        <span><strong class="text-white">{{ c.branch }}:</strong> {{ PROJECT_SNAPSHOT.branchAtSnapshot }}</span>
        <span><strong class="text-white">{{ c.revision }}:</strong> {{ PROJECT_SNAPSHOT.sourceRevision }}</span>
      </div>
    </section>

    <section class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" :aria-label="c.metricsAria">
      <StatCard :label="c.modulesMetric" :value="PROJECT_SNAPSHOT.baseline.modules" icon="grid" variant="primary" />
      <StatCard
        :label="c.testsMetric"
        :value="PROJECT_SNAPSHOT.baseline.backendTestsPassed"
        icon="clipboard-check"
        variant="success"
      />
      <StatCard
        :label="c.migrationMetric"
        :value="`${PROJECT_SNAPSHOT.baseline.alembicHeads} · ${PROJECT_SNAPSHOT.baseline.alembicHead}`"
        icon="archive"
        variant="info"
      />
      <StatCard :label="c.deploymentMetric" :value="c.notValidated" icon="desktop" variant="warning" />
    </section>

    <section class="flex items-start gap-3 rounded-xl border border-info/25 bg-info/5 px-4 py-3 text-sm">
      <AppIcon name="info" class="mt-0.5 shrink-0 text-info" />
      <div>
        <p class="font-bold text-gray-900 dark:text-gray-100">{{ c.snapshotWarningTitle }}</p>
        <p class="mt-1 leading-6 text-muted">{{ c.snapshotWarning }}</p>
      </div>
    </section>

    <AppTabs v-model="activeTab" :tabs="tabs" />

    <section v-if="activeTab === 'overview'" class="space-y-6">
      <div class="grid gap-4 lg:grid-cols-2">
        <AppCard padding="lg" :shadow="false" class="border-s-4 border-s-info">
          <div class="flex items-start gap-4">
            <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-info/10 text-info">
              <AppIcon name="shield" size="lg" />
            </div>
            <div>
              <p class="text-xs font-bold uppercase tracking-wide text-info">{{ c.nextTitle }}</p>
              <h2 class="mt-1 text-xl font-black">{{ c.nextPrimary }}</h2>
              <p class="mt-2 text-sm leading-6 text-muted">{{ c.nextPrimaryText }}</p>
              <button type="button" class="mt-4 text-sm font-bold text-primary-700 hover:underline" @click="useSuggestion('superadmin-audit')">
                {{ c.useSuggestion }}
              </button>
            </div>
          </div>
        </AppCard>

        <AppCard padding="lg" :shadow="false" class="border-s-4 border-s-danger">
          <div class="flex items-start gap-4">
            <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-danger/10 text-danger">
              <AppIcon name="currency" size="lg" />
            </div>
            <div>
              <p class="text-xs font-bold uppercase tracking-wide text-danger">{{ c.parallelTitle }}</p>
              <h2 class="mt-1 text-xl font-black">{{ c.parallelPrimary }}</h2>
              <p class="mt-2 text-sm leading-6 text-muted">{{ c.parallelText }}</p>
              <button type="button" class="mt-4 text-sm font-bold text-primary-700 hover:underline" @click="useSuggestion('financial-atomicity-audit')">
                {{ c.useSuggestion }}
              </button>
            </div>
          </div>
        </AppCard>
      </div>

      <div>
        <div class="mb-4">
          <h2 class="text-xl font-black">{{ c.smartStarts }}</h2>
          <p class="mt-1 text-sm text-muted">{{ c.smartStartsText }}</p>
        </div>
        <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          <button
            v-for="suggestion in PROMPT_SUGGESTIONS.slice(0, 3)"
            :key="suggestion.id"
            type="button"
            class="group rounded-xl border border-border bg-white p-4 text-start shadow-sm transition hover:border-primary-300 hover:shadow-md dark:bg-surface"
            @click="useSuggestion(suggestion.id)"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="font-bold group-hover:text-primary-700">{{ localize(suggestion.title) }}</p>
                <p class="mt-1 text-sm leading-6 text-muted">{{ localize(suggestion.description) }}</p>
              </div>
              <AppIcon name="send" class="mt-1 shrink-0 text-primary-700" />
            </div>
          </button>
        </div>
      </div>

      <div>
        <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 class="text-xl font-black">{{ c.modulesTitle }}</h2>
            <p class="mt-1 text-sm text-muted">{{ c.modulesText }}</p>
          </div>
          <SearchInput v-model="moduleSearch" :placeholder="c.searchModules" :clear-label="c.clearSearch" class="w-full lg:max-w-md" />
        </div>

        <div class="my-4 flex flex-wrap gap-2" role="group" :aria-label="c.moduleFilterAria">
          <button
            v-for="filter in (['all', 'working', 'attention', 'deferred'] as const)"
            :key="filter"
            type="button"
            :aria-pressed="moduleHealth === filter"
            :class="[
              'min-h-10 rounded-full border px-4 text-sm font-semibold transition-colors',
              moduleHealth === filter
                ? 'border-primary-700 bg-primary-700 text-white'
                : 'border-border bg-white text-muted hover:border-primary-300 hover:text-primary-700 dark:bg-surface',
            ]"
            @click="moduleHealth = filter"
          >
            {{ filter === 'all' ? c.all : healthLabel(filter) }}
          </button>
        </div>

        <div v-if="filteredModules.length" class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <article
            v-for="module in filteredModules"
            :key="module.id"
            class="flex min-h-64 flex-col rounded-xl border border-border bg-white p-5 shadow-sm dark:bg-surface"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="text-xs font-bold uppercase tracking-wider text-muted">{{ c.moduleLabel }}</p>
                <h3 class="mt-1 text-xl font-black">{{ module.name }}</h3>
              </div>
              <AppBadge :variant="healthVariant(module.health)">{{ healthLabel(module.health) }}</AppBadge>
            </div>
            <p class="mt-4 text-sm leading-6 text-gray-700 dark:text-gray-300">{{ localize(module.purpose) }}</p>
            <div class="mt-4 rounded-lg bg-background p-3 text-sm leading-6 text-muted">
              {{ localize(module.note) }}
            </div>
            <button
              type="button"
              class="mt-auto flex min-h-11 items-center gap-2 pt-4 text-sm font-bold text-primary-700 hover:underline"
              @click="instructModule(module.id)"
            >
              <AppIcon name="chat" size="sm" />
              {{ c.instructModule }}
            </button>
          </article>
        </div>
        <div v-else class="rounded-xl border border-dashed border-border bg-white p-10 text-center text-muted dark:bg-surface">
          {{ c.noModules }}
        </div>
      </div>
    </section>

    <section v-else-if="activeTab === 'readiness'" class="space-y-8">
      <div class="overflow-hidden rounded-2xl border border-primary-200 bg-gradient-to-br from-primary-50 via-white to-secondary-50 p-5 dark:border-primary-800 dark:from-primary-950/40 dark:via-surface dark:to-gray-900 sm:p-7">
        <div class="flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between">
          <div class="max-w-4xl">
            <p class="text-xs font-black uppercase tracking-[0.2em] text-primary-700">{{ c.readinessEyebrow }}</p>
            <h2 class="mt-2 text-2xl font-black sm:text-3xl">{{ c.readinessTitle }}</h2>
            <p class="mt-3 text-sm leading-7 text-muted sm:text-base">{{ c.readinessIntro }}</p>
          </div>
          <div class="flex flex-col gap-2 sm:flex-row">
            <AppButton variant="outline" type="button" @click="copyDocumentPath('docs/audits/PRODUCTION_READINESS_AUDIT.md')">
              <AppIcon name="clipboard" size="sm" />
              {{ c.auditDocument }}
            </AppButton>
            <AppButton variant="outline" type="button" @click="copyDocumentPath('docs/audits/SMART_EXECUTION_ROADMAP.md')">
              <AppIcon name="link" size="sm" />
              {{ c.roadmapDocument }}
            </AppButton>
          </div>
        </div>
        <div class="mt-5 flex items-start gap-3 rounded-xl border border-warning/30 bg-warning/10 p-4 text-sm">
          <AppIcon name="warning" class="mt-0.5 shrink-0 text-warning" />
          <p class="leading-6 text-gray-800 dark:text-gray-200">{{ c.noFakeScore }}</p>
        </div>
      </div>

      <div>
        <div class="mb-4 flex items-center gap-3">
          <div class="flex h-11 w-11 items-center justify-center rounded-xl bg-danger/10 text-danger">
            <AppIcon name="shield-warning" />
          </div>
          <h2 class="text-xl font-black">{{ c.criticalFindingsTitle }}</h2>
        </div>
        <div class="grid gap-4 xl:grid-cols-2">
          <article
            v-for="finding in CRITICAL_FINDINGS"
            :key="finding.id"
            class="flex flex-col rounded-xl border border-border border-s-4 border-s-danger bg-white p-5 shadow-sm dark:bg-surface"
          >
            <div class="flex items-start justify-between gap-4">
              <div class="flex items-start gap-3">
                <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-danger/10 text-danger">
                  <AppIcon :name="finding.icon" />
                </div>
                <div>
                  <AppBadge :variant="riskVariant(finding.severity)" size="sm">{{ riskLabel(finding.severity) }}</AppBadge>
                  <h3 class="mt-2 text-lg font-black">{{ localize(finding.title) }}</h3>
                </div>
              </div>
              <button
                type="button"
                class="shrink-0 rounded-lg p-2 text-muted transition hover:bg-background hover:text-primary-700 focus:outline-none focus-visible:shadow-focus-ring"
                :aria-label="`${c.codeEvidence}: ${finding.source}`"
                @click="copyDocumentPath(finding.source)"
              >
                <AppIcon name="document-duplicate" size="sm" />
              </button>
            </div>
            <dl class="mt-4 space-y-3 text-sm">
              <div class="rounded-lg bg-danger/5 p-3">
                <dt class="font-bold text-danger">{{ c.impact }}</dt>
                <dd class="mt-1 leading-6 text-gray-700 dark:text-gray-300">{{ localize(finding.impact) }}</dd>
              </div>
              <div>
                <dt class="font-bold">{{ c.codeEvidence }}</dt>
                <dd class="mt-1 leading-6 text-muted">{{ localize(finding.evidence) }}</dd>
              </div>
              <div>
                <dt class="font-bold">{{ c.requiredAction }}</dt>
                <dd class="mt-1 leading-6 text-muted">{{ localize(finding.action) }}</dd>
              </div>
            </dl>
            <button
              type="button"
              class="mt-auto flex min-h-11 items-center gap-2 pt-4 text-start text-sm font-bold text-primary-700 hover:underline"
              @click="planCriticalFinding(finding.id)"
            >
              <AppIcon name="chat" size="sm" />
              {{ c.planFinding }}
            </button>
          </article>
        </div>
      </div>

      <div>
        <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h2 class="text-xl font-black">{{ c.lensesTitle }}</h2>
            <p class="mt-1 text-sm leading-6 text-muted">{{ c.lensesText }}</p>
          </div>
          <div class="flex flex-wrap gap-2" role="group" :aria-label="c.evidenceFilter">
            <button
              v-for="filter in (['all', 'risk', 'needs_audit', 'verified', 'external'] as const)"
              :key="filter"
              type="button"
              :aria-pressed="evidenceFilter === filter"
              :class="[
                'min-h-11 rounded-full border px-4 text-sm font-semibold transition-colors',
                evidenceFilter === filter
                  ? 'border-primary-700 bg-primary-700 text-white'
                  : 'border-border bg-white text-muted hover:border-primary-300 hover:text-primary-700 dark:bg-surface',
              ]"
              @click="evidenceFilter = filter"
            >
              {{ filter === 'all' ? c.all : evidenceStateLabel(filter) }}
            </button>
          </div>
        </div>

        <div class="mt-4 grid gap-4 lg:grid-cols-2 2xl:grid-cols-3">
          <article
            v-for="lens in filteredReadinessLenses"
            :key="lens.id"
            class="flex flex-col rounded-xl border border-border bg-white p-5 shadow-sm dark:bg-surface"
          >
            <div class="flex items-start justify-between gap-3">
              <div class="flex items-start gap-3">
                <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-background text-primary-700">
                  <AppIcon :name="lens.icon" />
                </div>
                <h3 class="pt-1 font-black">{{ localize(lens.title) }}</h3>
              </div>
              <div class="flex flex-col items-end gap-1.5">
                <AppBadge :variant="evidenceStateVariant(lens.state)" size="sm">{{ evidenceStateLabel(lens.state) }}</AppBadge>
                <AppBadge :variant="reviewSeverityVariant(lens.severity)" size="sm">{{ reviewSeverityLabel(lens.severity) }}</AppBadge>
              </div>
            </div>
            <p class="mt-4 text-sm leading-6 text-gray-700 dark:text-gray-300">{{ localize(lens.finding) }}</p>
            <div class="mt-4 space-y-3 border-t border-border pt-4 text-sm">
              <div>
                <p class="text-xs font-bold uppercase tracking-wide text-muted">{{ c.currentEvidence }}</p>
                <p class="mt-1 leading-6">{{ localize(lens.evidence) }}</p>
              </div>
              <div class="rounded-lg bg-background p-3">
                <p class="text-xs font-bold uppercase tracking-wide text-primary-700">{{ c.nextGateLabel }}</p>
                <p class="mt-1 leading-6 text-muted">{{ localize(lens.nextGate) }}</p>
              </div>
            </div>
            <button
              type="button"
              class="mt-auto flex min-h-11 items-center gap-2 pt-4 text-start text-sm font-bold text-primary-700 hover:underline"
              @click="planReadinessLens(lens.id)"
            >
              <AppIcon name="send" size="sm" />
              {{ c.useSuggestion }}
            </button>
          </article>
        </div>
      </div>

      <div>
        <h2 class="text-xl font-black">{{ c.smartPlanTitle }}</h2>
        <p class="mt-1 max-w-4xl text-sm leading-6 text-muted">{{ c.smartPlanText }}</p>
        <ol class="mt-5 space-y-3">
          <li
            v-for="phase in SMART_EXECUTION_PHASES"
            :key="phase.id"
            class="grid gap-4 rounded-xl border border-border bg-white p-4 shadow-sm dark:bg-surface md:grid-cols-[3.25rem_minmax(0,1fr)_auto] md:items-start"
          >
            <div class="flex h-11 w-11 items-center justify-center rounded-xl bg-background font-black tabular-nums text-primary-700">
              {{ phase.order }}
            </div>
            <div>
              <div class="flex flex-wrap items-center gap-2">
                <h3 class="font-black">{{ localize(phase.title) }}</h3>
                <AppBadge :variant="smartPhaseStatusVariant(phase.status)" size="sm">
                  <span class="inline-flex items-center gap-1.5">
                    <AppIcon :name="smartPhaseIcon(phase.status)" size="xs" />
                    {{ smartPhaseStatusLabel(phase.status) }}
                  </span>
                </AppBadge>
              </div>
              <p class="mt-2 text-sm leading-6 text-gray-700 dark:text-gray-300">
                <strong>{{ c.phasePurpose }}:</strong> {{ localize(phase.purpose) }}
              </p>
              <p class="mt-1 text-sm leading-6 text-muted">
                <strong>{{ c.dependsOn }}:</strong> {{ localize(phase.dependencies) }}
              </p>
              <p class="mt-2 rounded-lg bg-background p-3 text-sm leading-6 text-muted">
                <strong class="text-gray-800 dark:text-gray-200">{{ c.acceptanceGate }}:</strong>
                {{ localize(phase.exitGate) }}
              </p>
            </div>
            <button
              type="button"
              class="flex min-h-11 items-center gap-2 self-center rounded-lg px-3 text-sm font-bold text-primary-700 hover:bg-primary-50 focus:outline-none focus-visible:shadow-focus-ring dark:hover:bg-primary-900/20"
              @click="selectedPhase = phase.id; activeTab = 'instruction'"
            >
              <AppIcon name="chat" size="sm" />
              {{ c.useSuggestion }}
            </button>
          </li>
        </ol>
      </div>
    </section>

    <section v-else-if="activeTab === 'experience'" class="space-y-8">
      <div class="relative overflow-hidden rounded-2xl bg-gray-950 p-5 text-white shadow-elevation-2 sm:p-7">
        <div class="absolute inset-y-0 start-0 w-1.5 bg-secondary" aria-hidden="true" />
        <div class="relative max-w-4xl">
          <p class="text-xs font-black uppercase tracking-[0.2em] text-gold-light">{{ c.experienceEyebrow }}</p>
          <h2 class="mt-2 text-2xl font-black sm:text-3xl">{{ c.experienceTitle }}</h2>
          <p class="mt-3 text-sm leading-7 text-gray-300 sm:text-base">{{ c.experienceIntro }}</p>
        </div>
      </div>

      <div>
        <h2 class="text-lg font-black">{{ c.chooseSurface }}</h2>
        <div class="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-6" role="group" :aria-label="c.chooseSurface">
          <button
            v-for="surface in EXPERIENCE_SURFACES"
            :key="surface.id"
            type="button"
            :aria-pressed="activeSurfaceId === surface.id"
            :class="[
              'min-h-24 rounded-xl border p-4 text-start transition focus:outline-none focus-visible:shadow-focus-ring',
              activeSurfaceId === surface.id
                ? 'border-primary-700 bg-primary-700 text-white shadow-md'
                : 'border-border bg-white hover:border-primary-300 hover:shadow-sm dark:bg-surface',
            ]"
            @click="activeSurfaceId = surface.id"
          >
            <AppIcon :name="surface.icon" :class="activeSurfaceId === surface.id ? 'text-gold-light' : 'text-primary-700'" />
            <span class="mt-3 block text-sm font-black">{{ localize(surface.title) }}</span>
          </button>
        </div>
      </div>

      <AppCard padding="lg" :shadow="false" class="overflow-hidden border-s-4 border-s-primary-700">
        <div class="grid gap-6 xl:grid-cols-[minmax(0,1.35fr)_minmax(20rem,0.65fr)]">
          <div>
            <div class="flex items-start gap-4">
              <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary-50 text-primary-700 dark:bg-primary-900/30">
                <AppIcon :name="activeSurface.icon" size="lg" />
              </div>
              <div>
                <h2 class="text-2xl font-black">{{ localize(activeSurface.title) }}</h2>
                <p class="mt-1 text-sm text-muted">{{ localize(activeSurface.audience) }}</p>
              </div>
            </div>
            <dl class="mt-5 grid gap-3 md:grid-cols-2">
              <div class="rounded-xl bg-background p-4">
                <dt class="text-xs font-bold uppercase tracking-wide text-muted">{{ c.environment }}</dt>
                <dd class="mt-2 text-sm leading-6">{{ localize(activeSurface.environment) }}</dd>
              </div>
              <div class="rounded-xl bg-primary-50 p-4 dark:bg-primary-900/20">
                <dt class="text-xs font-bold uppercase tracking-wide text-primary-700">{{ c.northStar }}</dt>
                <dd class="mt-2 text-sm font-semibold leading-6">{{ localize(activeSurface.northStar) }}</dd>
              </div>
            </dl>
          </div>
          <div class="flex flex-col justify-between rounded-xl border border-primary-200 bg-primary-50/60 p-5 dark:border-primary-800 dark:bg-primary-900/15">
            <div>
              <p class="text-xs font-bold uppercase tracking-wide text-primary-700">{{ c.audience }}</p>
              <p class="mt-2 text-sm leading-6">{{ localize(activeSurface.audience) }}</p>
            </div>
            <AppButton class="mt-5 w-full" type="button" @click="planExperienceSurface(activeSurface.id)">
              <AppIcon name="send" size="sm" />
              {{ c.planSurface }}
            </AppButton>
          </div>
        </div>

        <div class="mt-6 grid gap-4 lg:grid-cols-3">
          <div class="rounded-xl border border-success/25 bg-success/5 p-4">
            <h3 class="flex items-center gap-2 font-black text-success"><AppIcon name="verified" /> {{ c.priorities }}</h3>
            <ul class="mt-3 space-y-2 text-sm leading-6">
              <li v-for="item in activeSurface.priorities" :key="item.ar" class="flex items-start gap-2">
                <AppIcon name="check" size="xs" class="mt-1.5 shrink-0 text-success" />
                <span>{{ localize(item) }}</span>
              </li>
            </ul>
          </div>
          <div class="rounded-xl border border-danger/25 bg-danger/5 p-4">
            <h3 class="flex items-center gap-2 font-black text-danger"><AppIcon name="void" /> {{ c.avoid }}</h3>
            <ul class="mt-3 space-y-2 text-sm leading-6">
              <li v-for="item in activeSurface.avoid" :key="item.ar" class="flex items-start gap-2">
                <AppIcon name="close" size="xs" class="mt-1.5 shrink-0 text-danger" />
                <span>{{ localize(item) }}</span>
              </li>
            </ul>
          </div>
          <div class="rounded-xl border border-info/25 bg-info/5 p-4">
            <h3 class="flex items-center gap-2 font-black text-info"><AppIcon name="trend" /> {{ c.measures }}</h3>
            <ul class="mt-3 space-y-2 text-sm leading-6">
              <li v-for="item in activeSurface.measures" :key="item.ar" class="flex items-start gap-2">
                <AppIcon name="chart" size="xs" class="mt-1.5 shrink-0 text-info" />
                <span>{{ localize(item) }}</span>
              </li>
            </ul>
          </div>
        </div>
      </AppCard>

      <div class="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(20rem,0.85fr)]">
        <AppCard padding="lg" :shadow="false">
          <h2 class="text-xl font-black">{{ c.tokenTitle }}</h2>
          <p class="mt-2 text-sm leading-6 text-muted">{{ c.tokenText }}</p>
          <div class="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-5">
            <div class="overflow-hidden rounded-xl border border-border"><div class="h-16 bg-primary-700" /><p class="p-3 text-xs font-bold">{{ c.tokenPrimary }}</p></div>
            <div class="overflow-hidden rounded-xl border border-border"><div class="h-16 bg-success" /><p class="p-3 text-xs font-bold">{{ c.tokenSuccess }}</p></div>
            <div class="overflow-hidden rounded-xl border border-border"><div class="h-16 bg-warning" /><p class="p-3 text-xs font-bold">{{ c.tokenWarning }}</p></div>
            <div class="overflow-hidden rounded-xl border border-border"><div class="h-16 bg-danger" /><p class="p-3 text-xs font-bold">{{ c.tokenDanger }}</p></div>
            <div class="col-span-2 overflow-hidden rounded-xl border border-border sm:col-span-1"><div class="h-16 bg-gray-700" /><p class="p-3 text-xs font-bold">{{ c.tokenNeutral }}</p></div>
          </div>
        </AppCard>
        <AppCard padding="lg" :shadow="false">
          <h2 class="text-xl font-black">{{ c.typeTitle }}</h2>
          <div class="mt-5 space-y-4">
            <p class="text-3xl font-black tabular-nums text-primary-900 dark:text-primary-100">{{ c.typeDisplay }}</p>
            <p class="text-lg font-black">{{ c.typeHeading }}</p>
            <p class="text-sm leading-7 text-muted">{{ c.typeBody }}</p>
            <div class="flex flex-wrap gap-2">
              <AppBadge variant="success"><AppIcon name="success" size="xs" class="me-1" /> Paid / مدفوع</AppBadge>
              <AppBadge variant="warning"><AppIcon name="clock" size="xs" class="me-1" /> Pending / انتظار</AppBadge>
              <AppBadge variant="danger"><AppIcon name="void" size="xs" class="me-1" /> Void / ملغي</AppBadge>
            </div>
          </div>
        </AppCard>
      </div>

      <div>
        <h2 class="text-xl font-black">{{ c.principlesTitle }}</h2>
        <p class="mt-1 text-sm leading-6 text-muted">{{ c.principlesText }}</p>
        <div class="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <article v-for="(principle, index) in DESIGN_PRINCIPLES" :key="principle.id" class="rounded-xl border border-border bg-white p-5 shadow-sm dark:bg-surface">
            <div class="flex items-start justify-between gap-3">
              <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-primary-50 text-primary-700 dark:bg-primary-900/30"><AppIcon :name="principle.icon" /></div>
              <span class="text-2xl font-black tabular-nums text-gray-200 dark:text-gray-700">{{ String(index + 1).padStart(2, '0') }}</span>
            </div>
            <h3 class="mt-4 font-black">{{ localize(principle.title) }}</h3>
            <p class="mt-2 text-sm leading-6 text-muted">{{ localize(principle.summary) }}</p>
            <div class="mt-4 rounded-lg bg-background p-3 text-xs leading-5">
              <strong class="text-primary-700">{{ c.proofLabel }}:</strong> {{ localize(principle.proof) }}
            </div>
          </article>
        </div>
      </div>

      <div>
        <div class="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 class="text-xl font-black">{{ c.qualityTitle }}</h2>
            <p class="mt-1 max-w-4xl text-sm leading-6 text-muted">{{ c.qualityText }}</p>
          </div>
          <AppBadge variant="info">
            {{ c.reviewedCount }}: <span class="ms-1 tabular-nums">{{ reviewedRelevantCount }}/{{ relevantQualityGates.length }}</span>
          </AppBadge>
        </div>
        <div class="mt-4 grid gap-3 lg:grid-cols-2">
          <label
            v-for="gate in relevantQualityGates"
            :key="gate.id"
            :class="[
              'flex cursor-pointer items-start gap-4 rounded-xl border bg-white p-4 transition hover:border-primary-300 dark:bg-surface',
              reviewedGateIds.includes(gate.id) ? 'border-success/50 ring-1 ring-success/20' : 'border-border',
            ]"
          >
            <input v-model="reviewedGateIds" type="checkbox" :value="gate.id" class="mt-1 h-5 w-5 shrink-0 accent-primary-700" />
            <span class="min-w-0 flex-1">
              <span class="flex flex-wrap items-center gap-2">
                <span class="flex items-center gap-2 font-black"><AppIcon :name="gate.icon" size="sm" class="text-primary-700" /> {{ localize(gate.title) }}</span>
                <AppBadge v-if="gate.critical" variant="warning" size="sm">{{ c.criticalGate }}</AppBadge>
              </span>
              <span class="mt-2 block text-sm leading-6">{{ localize(gate.question) }}</span>
              <span class="mt-2 block rounded-lg bg-background p-2.5 text-xs leading-5 text-muted"><strong>{{ c.proofLabel }}:</strong> {{ localize(gate.evidence) }}</span>
            </span>
          </label>
        </div>
      </div>

      <div>
        <h2 class="text-xl font-black">{{ c.patternsTitle }}</h2>
        <div class="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <article v-for="pattern in EXPERIENCE_PATTERNS" :key="pattern.id" class="rounded-xl border border-border bg-white p-5 shadow-sm dark:bg-surface">
            <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-secondary-50 text-secondary-700 dark:bg-gray-800"><AppIcon :name="pattern.icon" /></div>
            <h3 class="mt-4 font-black">{{ localize(pattern.title) }}</h3>
            <p class="mt-2 text-xs font-bold uppercase tracking-wide text-muted">{{ c.patternUse }}</p>
            <p class="mt-1 text-sm leading-6">{{ localize(pattern.use) }}</p>
            <ul class="mt-3 space-y-2 border-t border-border pt-3 text-sm leading-6 text-muted">
              <li v-for="rule in pattern.rules" :key="rule.ar" class="flex items-start gap-2"><AppIcon name="check" size="xs" class="mt-1.5 shrink-0 text-success" />{{ localize(rule) }}</li>
            </ul>
          </article>
        </div>
      </div>

      <div>
        <h2 class="text-xl font-black">{{ c.researchTitle }}</h2>
        <p class="mt-1 text-sm leading-6 text-muted">{{ c.researchText }}</p>
        <div class="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          <a
            v-for="reference in RESEARCH_REFERENCES"
            :key="reference.id"
            :href="reference.url"
            target="_blank"
            rel="noreferrer"
            class="group rounded-xl border border-border bg-white p-4 transition hover:border-primary-300 hover:shadow-sm focus:outline-none focus-visible:shadow-focus-ring dark:bg-surface"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <p class="text-xs font-bold uppercase tracking-wide text-primary-700">{{ reference.publisher }}</p>
                <h3 class="mt-1 font-black group-hover:text-primary-700">{{ reference.title }}</h3>
              </div>
              <AppIcon name="external-link" size="sm" class="shrink-0 text-muted group-hover:text-primary-700" />
            </div>
            <p class="mt-3 text-sm leading-6 text-muted">{{ localize(reference.contribution) }}</p>
            <span class="mt-3 inline-block text-xs font-bold text-primary-700">{{ c.openReference }}</span>
          </a>
        </div>
      </div>
    </section>

    <section v-else-if="activeTab === 'roadmap'" class="space-y-8">
      <p class="max-w-4xl text-sm leading-6 text-muted">{{ c.roadmapText }}</p>

      <div v-for="track in (['safety', 'pre_public', 'dining'] as const)" :key="track" class="space-y-4">
        <div class="flex items-center gap-3">
          <div class="flex h-10 w-10 items-center justify-center rounded-xl bg-primary-50 text-primary-700">
            <AppIcon :name="track === 'safety' ? 'shield-warning' : track === 'pre_public' ? 'flag' : 'currency'" />
          </div>
          <h2 class="text-xl font-black">{{ track === 'safety' ? c.safetyTrack : track === 'pre_public' ? c.prePublicTrack : c.diningTrack }}</h2>
        </div>

        <ol class="grid gap-4 xl:grid-cols-2">
          <li
            v-for="step in PROJECT_ROADMAP.filter((item) => item.track === track).sort((a, b) => a.order - b.order)"
            :key="step.id"
            :class="['rounded-xl border border-border border-s-4 bg-white p-5 shadow-sm dark:bg-surface', roadmapBorderClass(step.status)]"
          >
            <div class="flex items-start gap-4">
              <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-background font-black tabular-nums text-primary-700">
                {{ step.order }}
              </div>
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center justify-between gap-2">
                  <h3 class="font-black">{{ localize(step.title) }}</h3>
                  <AppBadge :variant="roadmapStatusVariant(step.status)">
                    <span class="inline-flex items-center gap-1.5">
                      <AppIcon :name="roadmapIcon(step.status)" size="xs" />
                      {{ roadmapStatusLabel(step.status) }}
                    </span>
                  </AppBadge>
                </div>
                <p class="mt-2 text-sm leading-6 text-gray-700 dark:text-gray-300">{{ localize(step.outcome) }}</p>
                <div class="mt-3 flex items-start gap-2 rounded-lg bg-background p-3 text-sm text-muted">
                  <AppIcon name="clipboard-check" size="sm" class="mt-0.5 shrink-0" />
                  <p><strong class="text-gray-700 dark:text-gray-300">{{ c.acceptanceGate }}:</strong> {{ localize(step.gate) }}</p>
                </div>
              </div>
            </div>
          </li>
        </ol>
      </div>
    </section>

    <section v-else-if="activeTab === 'decisions'" class="space-y-8">
      <div>
        <h2 class="text-xl font-black">{{ c.decisionsTitle }}</h2>
        <p class="mt-1 text-sm text-muted">{{ c.decisionsText }}</p>
        <div class="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          <button
            v-for="decision in PROJECT_DECISIONS"
            :key="decision.id"
            type="button"
            :aria-pressed="selectedDecisionIds.includes(decision.id)"
            :class="[
              'rounded-xl border p-4 text-start transition-colors',
              selectedDecisionIds.includes(decision.id)
                ? 'border-primary-300 bg-primary-50/70 dark:bg-primary-900/20'
                : 'border-border bg-white hover:border-primary-200 dark:bg-surface',
            ]"
            @click="toggleDecision(decision.id)"
          >
            <div class="flex items-start justify-between gap-3">
              <div>
                <h3 class="font-bold">{{ localize(decision.title) }}</h3>
                <p class="mt-1 text-sm leading-6 text-muted">{{ localize(decision.summary) }}</p>
              </div>
              <AppIcon
                :name="selectedDecisionIds.includes(decision.id) ? 'success' : 'add-circle'"
                :class="selectedDecisionIds.includes(decision.id) ? 'text-success' : 'text-muted'"
              />
            </div>
            <div class="mt-3 flex flex-wrap items-center justify-between gap-2 text-xs">
              <code class="rounded bg-white/70 px-2 py-1 text-muted dark:bg-gray-900/40">{{ decision.source }}</code>
              <span :class="selectedDecisionIds.includes(decision.id) ? 'text-success' : 'text-muted'">
                {{ selectedDecisionIds.includes(decision.id) ? c.included : c.notIncluded }}
              </span>
            </div>
          </button>
        </div>
      </div>

      <div>
        <h2 class="text-xl font-black">{{ c.risksTitle }}</h2>
        <p class="mt-1 text-sm text-muted">{{ c.risksText }}</p>
        <div class="mt-4 overflow-hidden rounded-xl border border-border bg-white dark:bg-surface">
          <div
            v-for="risk in PROJECT_RISKS"
            :key="risk.id"
            class="grid gap-3 border-b border-border p-4 last:border-b-0 md:grid-cols-[auto_8rem_1fr] md:items-start"
          >
            <AppBadge :variant="riskVariant(risk.severity)">{{ riskLabel(risk.severity) }}</AppBadge>
            <code class="text-xs font-bold uppercase tracking-wide text-muted">{{ risk.area }}</code>
            <div>
              <h3 class="font-bold">{{ localize(risk.title) }}</h3>
              <p class="mt-1 text-sm leading-6 text-muted">{{ localize(risk.detail) }}</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <section v-else class="space-y-6">
      <div>
        <h2 class="text-xl font-black">{{ c.composerTitle }}</h2>
        <p class="mt-1 max-w-4xl text-sm leading-6 text-muted">{{ c.composerText }}</p>
      </div>

      <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
        <button
          v-for="suggestion in PROMPT_SUGGESTIONS"
          :key="suggestion.id"
          type="button"
          class="rounded-xl border border-border bg-white p-4 text-start transition hover:border-primary-300 hover:shadow-sm dark:bg-surface"
          @click="useSuggestion(suggestion.id)"
        >
          <p class="text-sm font-bold">{{ localize(suggestion.title) }}</p>
          <p class="mt-1 text-xs leading-5 text-muted">{{ localize(suggestion.description) }}</p>
        </button>
      </div>

      <div class="grid gap-6 xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <AppCard padding="lg" :shadow="false">
          <div class="space-y-5">
            <div class="grid gap-4 md:grid-cols-2">
              <AppSelect v-model="mode" :label="c.modeLabel" :options="modeOptions" :placeholder="''" />
              <AppSelect v-model="selectedScope" :label="c.scopeLabel" :options="scopeOptions" :placeholder="''" />
            </div>
            <AppSelect v-model="selectedPhase" :label="c.phaseLabel" :options="phaseOptions" :placeholder="''" />
            <AppTextarea v-model="objective" :label="c.objectiveLabel" :placeholder="c.objectivePlaceholder" :rows="6" />

            <fieldset>
              <legend class="mb-2 text-sm font-semibold text-gray-700 dark:text-gray-300">{{ c.selectedDecisions }}</legend>
              <div class="max-h-52 space-y-2 overflow-y-auto rounded-xl border border-border bg-background p-3">
                <label
                  v-for="decision in PROJECT_DECISIONS"
                  :key="decision.id"
                  class="flex cursor-pointer items-start gap-3 rounded-lg p-2 text-sm hover:bg-white dark:hover:bg-gray-800"
                >
                  <input v-model="selectedDecisionIds" type="checkbox" :value="decision.id" class="mt-1 h-4 w-4 rounded border-border text-primary-700 focus:ring-primary-500" />
                  <span>
                    <span class="block font-semibold">{{ localize(decision.title) }}</span>
                    <span class="mt-0.5 block text-xs leading-5 text-muted">{{ localize(decision.summary) }}</span>
                  </span>
                </label>
              </div>
            </fieldset>

            <div class="space-y-3 rounded-xl border border-border bg-background p-4">
              <label class="flex cursor-pointer items-start gap-3 text-sm">
                <input v-model="requireEvidence" type="checkbox" class="mt-0.5 h-4 w-4 rounded border-border text-primary-700 focus:ring-primary-500" />
                <span>{{ c.evidenceLabel }}</span>
              </label>
              <label class="flex cursor-pointer items-start gap-3 text-sm">
                <input v-model="preventCommit" type="checkbox" class="mt-0.5 h-4 w-4 rounded border-border text-primary-700 focus:ring-primary-500" />
                <span>{{ c.noCommitLabel }}</span>
              </label>
              <label class="flex cursor-pointer items-start gap-3 text-sm">
                <input v-model="plainLanguageHandoff" type="checkbox" class="mt-0.5 h-4 w-4 rounded border-border text-primary-700 focus:ring-primary-500" />
                <span>{{ c.simpleHandoffLabel }}</span>
              </label>
            </div>
          </div>
        </AppCard>

        <div class="xl:sticky xl:top-0 xl:self-start">
          <AppCard padding="none" :shadow="false">
            <div class="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4">
              <div>
                <h3 class="font-black">{{ c.promptPreview }}</h3>
                <p class="mt-0.5 text-xs text-muted">{{ c.modes[mode] }}</p>
              </div>
              <AppButton type="button" size="sm" :disabled="!generatedPrompt" @click="copyPrompt">
                <AppIcon name="document-duplicate" size="sm" />
                {{ c.copyPrompt }}
              </AppButton>
            </div>
            <div class="max-h-[42rem] min-h-[28rem] overflow-auto bg-gray-950 p-5 text-gray-100" :dir="direction">
              <pre v-if="generatedPrompt" class="whitespace-pre-wrap break-words font-sans text-sm leading-7 [unicode-bidi:plaintext]">{{ generatedPrompt }}</pre>
              <div v-else class="flex min-h-[24rem] flex-col items-center justify-center px-6 text-center text-gray-400">
                <AppIcon name="chat" size="xl" />
                <p class="mt-3 max-w-sm text-sm leading-6">{{ c.promptPlaceholder }}</p>
              </div>
            </div>
          </AppCard>

          <div class="mt-4 flex items-start gap-3 rounded-xl border border-success/25 bg-success/5 p-4 text-sm">
            <AppIcon name="shield" class="mt-0.5 shrink-0 text-success" />
            <div>
              <p class="font-bold">{{ c.safetyTitle }}</p>
              <p class="mt-1 leading-6 text-muted">{{ c.safetyText }}</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>
