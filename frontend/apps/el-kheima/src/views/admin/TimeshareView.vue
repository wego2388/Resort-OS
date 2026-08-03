<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
import {
  AppBadge,
  AppButton,
  AppCard,
  AppIcon,
  AppInput,
  AppModal,
  AppSelect,
  EmptyState,
  LoadingState,
  SearchInput,
  useConfirm,
  useToast,
  type SelectOption,
} from '@resort-os/ui'

const toast = useToast()
const { confirm } = useConfirm()
const { t, locale } = useI18n()
const { formatDate, formatMoney } = useStaffFormat()
const auth = useAuthStore()
const branchId = computed(() => auth.branchId)

// ── Types ──────────────────────────────────────────────────────────────────
interface Installment {
  id: number; contract_id: number; installment_no: number; due_date: string
  amount: number; paid_amount: number; status: string
  customer_name?: string; customer_phone?: string; room_type?: string
}
interface MaintenanceDue {
  id: number; contract_id: number; fee_year: number; due_date: string
  amount: number; paid_amount: number; status: string
  customer_name?: string; customer_phone?: string; room_type?: string
}
interface Contract {
  id: number; contract_number: string; customer_name: string; customer_phone: string | null
  customer_email: string | null; customer_national_id?: string | null; room_type: string; week_number: number | null
  nights_per_year: number; season: string; total_value: number; down_payment: number
  installments: number; status: string; booking_frozen: boolean
  start_date: string; end_date: string | null; notes: string | null
  nationality: string | null; address: string | null; rci_included: boolean
  partner_company: string | null; maintenance_fee: number
  installments_list: Installment[]
  maintenance_dues_list: MaintenanceDue[]
  collected?: number; overdue_amount?: number
  unit_id: number | null
}
interface CalendarWeek { week: number; start_date: string; end_date: string; is_current: boolean; is_past: boolean; contracts: CalendarContract[] }
interface CalendarContract { id: number; customer_name: string; rci_included: boolean; status: string; contract_number?: string; room_type: string }
interface ImportResult { error?: string; imported?: number; skipped?: number; errors?: string[] }
interface SummaryData {
  active_contracts?: number; collection_rate_pct?: number; total_collected?: number
  total_value?: number; total_overdue?: number; overdue_contracts_count?: number
  this_month_due?: number; upcoming_visits?: Visit[]; overdue_clients?: OverdueClient[]
  occupied_units?: number; total_units?: number; occupancy_rate_pct?: number
  pending_visit_requests?: number; open_support_tickets?: number
}
interface CalendarMonth { month: number; month_name: string; weeks: CalendarWeek[] }
interface TimeshareUnit { id: number; branch_id: number; unit_number: string; unit_type: string; status: string; notes?: string | null }
interface WaitlistEntry {
  id: number; branch_id: number; contract_id: number
  requested_start: string; requested_end: string; position: number
  status: string; notified_at: string | null; expires_at: string | null
}
interface Visit {
  id: number; contract_id: number; unit_id: number | null
  check_in: string; check_out: string; nights: number; status: string
  // fields returned from the summary/upcoming-visits endpoint
  customer_name?: string; customer_phone?: string; room_type?: string
  week_number?: number; visit_start?: string
  days_until: number
}
// Overdue client summary shape returned by the dashboard endpoint
interface OverdueClient {
  id: number; customer_name: string; customer_phone?: string | null
  room_type: string; overdue_amount?: number
  pending_count?: number; next_due?: string
}
interface GuestReview {
  id: number; guest_name: string; overall_rating: number; comment: string | null
  source: string; reviewed_at: string
}

// ── Tabs ───────────────────────────────────────────────────────────────────
const TABS = computed(() => [
  { id: 'dashboard', icon: '🏠', label: t('backoffice.timeshare.tabs.dashboard') },
  { id: 'calendar', icon: '📅', label: t('backoffice.timeshare.tabs.calendar') },
  { id: 'clients', icon: '👤', label: t('backoffice.timeshare.tabs.clients') },
  { id: 'installments', icon: '💰', label: t('backoffice.timeshare.tabs.installments') },
  { id: 'maintenance', icon: '🛠️', label: t('backoffice.timeshare.tabs.maintenance') },
  // طلبات الزيارة/الدعم (2026-08-03، بوابة العميل العامة الجديدة) — متاحة
  // لـtimeshare_admin وtimeshare_agent الاتنين (نفس نمط جدولة الزيارة).
  // إدارة الموظفين نفسها timeshare_admin بس، زي باقي العمليات الإدارية.
  { id: 'requests', icon: '📝', label: t('backoffice.timeshare.tabs.requests'), badge: summary.value.pending_visit_requests || 0 },
  { id: 'support', icon: '💬', label: t('backoffice.timeshare.tabs.support'), badge: summary.value.open_support_tickets || 0 },
  { id: 'waitlist', icon: '⏳', label: t('backoffice.timeshare.tabs.waitlist') },
  ...(auth.hasRole('timeshare_admin') ? [
    { id: 'staff', icon: '🧑‍💼', label: t('backoffice.timeshare.tabs.staff') },
    { id: 'units', icon: '🏘️', label: t('backoffice.timeshare.tabs.units') },
  ] : []),
])
const activeTab = ref('dashboard')
const loading = ref(false)

// ── Dashboard ────────────────────────────────────────────────────────────
const summary = ref<SummaryData>({})

// ── Calendar ─────────────────────────────────────────────────────────────
const calYear = ref(new Date().getFullYear())
const calLoading = ref(false)
const calendar = ref<{ calendar: CalendarMonth[]; total_booked_weeks: number }>({ calendar: [], total_booked_weeks: 0 })

// ── Clients ──────────────────────────────────────────────────────────────
const allClients = ref<Contract[]>([])
const clientSearch = ref('')
const clientStatusFilter = ref('')
const clientRoomFilter = ref('')
const clientsLoading = ref(false)
const expandedClient = ref<number | null>(null)

// ── Units (لعرض رقم الوحدة الفعلي بدل unit_id خام في بروفايل العميل) ──────
const units = ref<TimeshareUnit[]>([])
const unitNumberById = computed<Record<number, string>>(() =>
  Object.fromEntries(units.value.map(u => [u.id, u.unit_number])),
)
const contractById = computed<Record<number, Contract>>(() =>
  Object.fromEntries(allClients.value.map(c => [c.id, c])),
)

// ── Customer Profile (ملف عميل مجمّع — كل عقوده/زياراته/أقساطه/تقييماته) ──
// العقود مفيهاش كيان "عميل" منفصل (customer_name/phone/email مباشرة على كل
// صف عقد) — فبنجمّع حسب customer_phone (الأكثر ثباتاً ووجوداً) وإلا
// customer_national_id، وإلا كل عقد بروفايله لوحده (مفيش حاجة تجمعه بحاجة تانية).
function customerKey(c: Contract): string {
  return c.customer_phone?.trim() || c.customer_national_id?.trim() || `contract-${c.id}`
}

const profileModal = reactive({
  open: false, loading: false,
  contracts: [] as Contract[],
  visits: [] as Visit[],
  reviews: [] as GuestReview[],
})

const profileCustomerName = computed(() => profileModal.contracts[0]?.customer_name ?? '')
const profileAllInstallments = computed(() =>
  profileModal.contracts.flatMap(c => (c.installments_list ?? []).map(i => ({ ...i, contract_number: c.contract_number }))),
)
const profileAllMaintenanceDues = computed(() =>
  profileModal.contracts.flatMap(c => (c.maintenance_dues_list ?? []).map(d => ({ ...d, contract_number: c.contract_number }))),
)
const profileTotals = computed(() => {
  const totals = { total_value: 0, collected: 0, overdue: 0, pending: 0 }
  for (const c of profileModal.contracts) totals.total_value += Number(c.total_value) || 0
  for (const i of profileAllInstallments.value) {
    if (i.status === 'paid') totals.collected += Number(i.paid_amount) || 0
    else if (i.status === 'overdue') totals.overdue += Number(i.amount) || 0
    else if (i.status === 'pending') totals.pending += Number(i.amount) || 0
  }
  return totals
})

async function loadUnits() {
  try {
    const r = await api.get('/api/v1/timeshare/units', { params: { branch_id: branchId.value } })
    units.value = r.data ?? []
  } catch { toast.error(t('backoffice.timeshare.msg.loadUnitsError')) }
}

// ── إدارة مخزون الوحدات (2026-08-03) — كان مفيش أي طريقة لإضافة وحدة
// جديدة أو تعليمها "تحت الصيانة" غير التعديل المباشر في قاعدة البيانات.
const newUnitModal = ref(false)
const newUnitForm = ref({ unit_number: '', unit_type: '2R', notes: '' })
const savingUnit = ref(false)
const togglingUnitId = ref<number | null>(null)

function openNewUnitModal() {
  newUnitForm.value = { unit_number: '', unit_type: '2R', notes: '' }
  newUnitModal.value = true
}

async function submitNewUnit() {
  if (!newUnitForm.value.unit_number.trim()) {
    toast.error(t('backoffice.timeshare.msg.unitNumberRequired'))
    return
  }
  savingUnit.value = true
  try {
    const { data } = await api.post('/api/v1/timeshare/units', {
      branch_id: branchId.value,
      unit_number: newUnitForm.value.unit_number.trim(),
      unit_type: newUnitForm.value.unit_type,
      notes: newUnitForm.value.notes.trim() || null,
    })
    units.value = [...units.value, data]
    toast.success(t('backoffice.timeshare.msg.unitAdded'))
    newUnitModal.value = false
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.timeshare.msg.unitSaveError'))
  } finally { savingUnit.value = false }
}

async function toggleUnitMaintenance(unit: TimeshareUnit) {
  const nextStatus = unit.status === 'maintenance' ? 'available' : 'maintenance'
  togglingUnitId.value = unit.id
  try {
    const { data } = await api.patch(`/api/v1/timeshare/units/${unit.id}`, { status: nextStatus })
    units.value = units.value.map(u => (u.id === unit.id ? { ...u, ...data } : u))
    toast.success(t('backoffice.timeshare.msg.unitStatusUpdated'))
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.timeshare.msg.unitSaveError'))
  } finally { togglingUnitId.value = null }
}

// ── قائمة الانتظار (2026-08-03) — كانت موديل + endpoints بدون أي شاشة
// خالص (حتى للقراءة بس)، ومفيش مهمة مجدولة كانت بتنقل حد من "منتظر"
// لـ"اتبلّغ" لما وحدة تفضى (راجع app.tasks.timeshare_tasks.process_waitlist
// الجديدة). عميل كان ممكن يتسجّل ويفضل في القائمة للأبد من غير حد يعرف.
const waitlist = ref<WaitlistEntry[]>([])
const waitlistLoading = ref(false)
const updatingWaitlistId = ref<number | null>(null)
const newWaitlistModal = ref(false)
const newWaitlistContract = ref<Contract | null>(null)
const newWaitlistForm = ref({ requested_start: '', requested_end: '' })
const savingWaitlist = ref(false)

async function loadWaitlist() {
  waitlistLoading.value = true
  try {
    const r = await api.get('/api/v1/timeshare/waitlist', { params: { branch_id: branchId.value } })
    waitlist.value = r.data ?? []
  } catch { toast.error(t('backoffice.timeshare.msg.loadWaitlistError')) }
  finally { waitlistLoading.value = false }
}

function openNewWaitlistModal(c: Contract) {
  newWaitlistContract.value = c
  newWaitlistForm.value = { requested_start: '', requested_end: '' }
  newWaitlistModal.value = true
}

async function submitNewWaitlist() {
  if (!newWaitlistContract.value) return
  if (!newWaitlistForm.value.requested_start || !newWaitlistForm.value.requested_end) {
    toast.error(t('backoffice.timeshare.msg.waitlistDatesRequired'))
    return
  }
  savingWaitlist.value = true
  try {
    const { data } = await api.post('/api/v1/timeshare/waitlist', {
      branch_id: branchId.value,
      contract_id: newWaitlistContract.value.id,
      requested_start: newWaitlistForm.value.requested_start,
      requested_end: newWaitlistForm.value.requested_end,
    })
    waitlist.value = [...waitlist.value, data]
    toast.success(t('backoffice.timeshare.msg.waitlistAdded'))
    newWaitlistModal.value = false
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.timeshare.msg.waitlistSaveError'))
  } finally { savingWaitlist.value = false }
}

async function updateWaitlistStatus(entry: WaitlistEntry, newStatus: 'confirmed' | 'cancelled') {
  updatingWaitlistId.value = entry.id
  try {
    await api.patch(`/api/v1/timeshare/waitlist/${entry.id}`, { status: newStatus })
    waitlist.value = waitlist.value.filter(w => w.id !== entry.id)
    toast.success(t('backoffice.timeshare.msg.waitlistStatusUpdated'))
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.timeshare.msg.waitlistSaveError'))
  } finally { updatingWaitlistId.value = null }
}

async function openProfile(c: Contract) {
  const key = customerKey(c)
  profileModal.contracts = allClients.value.filter(x => customerKey(x) === key)
  profileModal.visits = []
  profileModal.reviews = []
  profileModal.open = true
  profileModal.loading = true
  try {
    const visitLists = await Promise.all(
      profileModal.contracts.map(ct =>
        api.get('/api/v1/timeshare/visits', { params: { branch_id: branchId.value, contract_id: ct.id } })
          .then(r => r.data as Visit[]).catch(() => [] as Visit[])),
    )
    profileModal.visits = visitLists.flat().sort((a, b) => b.check_in.localeCompare(a.check_in))

    // التقييمات محتاجة صلاحية manager على الباك إند (GET /analytics/reviews) —
    // لو المستخدم أقل من كده (مثلاً supervisor بيشوف شاشة التايم شير) بنتخطى
    // القسم ده بهدوء بدل ما نطلب endpoint هيرجع 403.
    if (auth.hasRole('timeshare_admin') && profileModal.visits.length) {
      const reviewLists = await Promise.all(
        profileModal.visits.map(v =>
          api.get('/api/v1/analytics/reviews', { params: { branch_id: branchId.value, timeshare_visit_id: v.id } })
            .then(r => (r.data?.items ?? []) as GuestReview[]).catch(() => [] as GuestReview[])),
      )
      profileModal.reviews = reviewLists.flat()
    }
  } catch (e) { toast.error(t('backoffice.timeshare.msg.loadProfileError')) }
  finally { profileModal.loading = false }
}

const visitStatusVariant: Record<string, BadgeVariant> = {
  scheduled: 'info', active: 'success', completed: 'neutral', cancelled: 'danger',
}
function visitStatusLabel(s: string) {
  const icons: Record<string, string> = { scheduled: '📅', active: '🏝️', completed: '✅', cancelled: '❌' }
  const labels: Record<string, string> = {
    scheduled: t('backoffice.timeshare.visitStatus.scheduled'), active: t('backoffice.timeshare.visitStatus.active'),
    completed: t('backoffice.timeshare.visitStatus.completed'), cancelled: t('backoffice.timeshare.visitStatus.cancelled'),
  }
  return labels[s] ? `${icons[s]} ${labels[s]}` : s
}

// إرسال استبيان الرضا (واتساب) لصاحب زيارة منتهية — الـ endpoint موجود
// (POST /analytics/reviews/survey-token/timeshare/{id}/send) لكن كان بدون
// أي زر في المشروع كله يستدعيه، يعني الاستبيان كان عمليًا غير قابل
// للاستخدام رغم إن الباك إند والفرونت إند (SurveyView.vue) شغالين بالكامل.
const sendingSurveyId = ref<number | null>(null)
const sentSurveyIds = ref<Set<number>>(new Set())

async function sendSurvey(v: Visit) {
  const ok = await confirm({
    message: t('backoffice.timeshare.confirmSendSurvey'),
    confirmText: t('backoffice.timeshare.yesSend'), cancelText: t('backoffice.timeshare.cancelAction'),
  })
  if (!ok) return
  sendingSurveyId.value = v.id
  try {
    await api.post(`/api/v1/analytics/reviews/survey-token/timeshare/${v.id}/send`, null, {
      params: { branch_id: branchId.value },
    })
    sentSurveyIds.value.add(v.id)
    toast.success(t('backoffice.timeshare.msg.surveySent'))
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.surveyError'))
  } finally {
    sendingSurveyId.value = null
  }
}

// ── Schedule Visit Modal ──────────────────────────────────────────────────
// الـ backend (POST /api/v1/timeshare/visits) يقبل: branch_id, contract_id,
// check_in, check_out, notes (optional). الوحدة تُخصَّص تلقائياً بالـ service.
const scheduleModal = reactive({
  open: false,
  loading: false,
  contractId: undefined as number | undefined,
  checkIn: '',
  checkOut: '',
  notes: '',
  error: '',
})

function openScheduleVisit() {
  // اختر أول عقد نشط في البروفايل الحالي
  const active = profileModal.contracts.find(c => c.status === 'active') ?? profileModal.contracts[0]
  scheduleModal.contractId = active?.id ?? undefined
  scheduleModal.checkIn  = ''
  scheduleModal.checkOut = ''
  scheduleModal.notes    = ''
  scheduleModal.error    = ''
  scheduleModal.open     = true
}

const contractOptions = computed<SelectOption[]>(() =>
  profileModal.contracts.map(c => ({
    value: c.id,
    label: `${c.contract_number ?? '#' + c.id} — ${c.nights_per_year ?? ''}n/yr`,
  })),
)

async function confirmScheduleVisit() {
  if (scheduleModal.contractId == null || !scheduleModal.checkIn || !scheduleModal.checkOut) {
    scheduleModal.error = t('backoffice.timeshare.scheduleVisit.validationError')
    return
  }
  scheduleModal.loading = true
  scheduleModal.error   = ''
  try {
    await api.post('/api/v1/timeshare/visits', {
      branch_id:   branchId.value,
      contract_id: scheduleModal.contractId!,
      check_in:    scheduleModal.checkIn,
      check_out:   scheduleModal.checkOut,
      notes:       scheduleModal.notes || undefined,
    })
    toast.success(t('backoffice.timeshare.scheduleVisit.successToast'))
    scheduleModal.open = false
    // أعد تحميل الزيارات في البروفايل المفتوح
    const visitLists = await Promise.all(
      profileModal.contracts.map(ct =>
        api.get('/api/v1/timeshare/visits', { params: { branch_id: branchId.value, contract_id: ct.id } })
          .then(r => r.data as Visit[]).catch(() => [] as Visit[])),
    )
    profileModal.visits = visitLists.flat().sort((a, b) => b.check_in.localeCompare(a.check_in))
  } catch (e: unknown) {
    scheduleModal.error = (e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.scheduleVisit.errorToast')
  } finally {
    scheduleModal.loading = false
  }
}

// ── Update Visit Status ────────────────────────────────────────────────────
const updatingVisitId = ref<number | null>(null)

async function updateVisitStatus(v: Visit, newStatus: string) {
  const ok = await confirm({
    message: t('backoffice.timeshare.confirmStatusChange', {
      from: visitStatusLabel(v.status),
      to:   visitStatusLabel(newStatus),
    }),
    confirmText: t('common.save'),
    cancelText:  t('common.cancel'),
  })
  if (!ok) return
  updatingVisitId.value = v.id
  try {
    const res = await api.patch(`/api/v1/timeshare/visits/${v.id}`, { status: newStatus })
    // تحديث الزيارة محلياً بدون reload كامل
    const idx = profileModal.visits.findIndex(x => x.id === v.id)
    if (idx !== -1) profileModal.visits[idx] = { ...profileModal.visits[idx], status: (res.data as Visit).status }
    toast.success(t('backoffice.timeshare.scheduleVisit.statusUpdated'))
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.scheduleVisit.statusError'))
  } finally {
    updatingVisitId.value = null
  }
}

// الحالات المسموح بالانتقال إليها من كل حالة
function nextStatuses(current: string): { status: string; label: string }[] {
  const map: Record<string, string[]> = {
    scheduled:  ['active', 'cancelled'],
    active:     ['completed', 'cancelled'],
    completed:  [],
    cancelled:  [],
  }
  return (map[current] ?? []).map(s => ({ status: s, label: visitStatusLabel(s) }))
}

// ── Installments ─────────────────────────────────────────────────────────
const installments = ref<Installment[]>([])
const installSummary = ref({ overdue_total: 0, pending_total: 0 })
const installLoading = ref(false)
const installStatus = ref('overdue')
const installMonth = ref('')
const installSearch = ref('')

// ── Pay Modal ────────────────────────────────────────────────────────────
const payModal = reactive({
  open: false, saving: false, inst_id: 0, customer_name: '', due_amount: 0,
  amount: 0, method: 'cash', receipt_number: '',
})

// ── Maintenance Dues ─────────────────────────────────────────────────────
const maintenanceDues = ref<MaintenanceDue[]>([])
const maintSummary = ref({ overdue_total: 0, pending_total: 0 })
const maintLoading = ref(false)
const maintStatus = ref('overdue')
const maintSearch = ref('')

// ── Maintenance Pay Modal ────────────────────────────────────────────────
const maintPayModal = reactive({
  open: false, saving: false, due_id: 0, customer_name: '', due_amount: 0,
  amount: 0, method: 'cash', receipt_number: '',
})

// ── Import Modal ─────────────────────────────────────────────────────────
const importModal = reactive({ open: false, uploading: false, result: null as ImportResult | null, file: null as File | null })

// ── Visit Requests (بوابة العميل العامة، 2026-08-03) ───────────────────────
interface VisitRequestItem {
  id: number; contract_id: number; preferred_start: string; preferred_end: string
  notes: string | null; status: string; rejection_reason: string | null
  customer_name?: string; customer_phone?: string; contract_number?: string
}
const visitRequests = ref<VisitRequestItem[]>([])
const requestsLoading = ref(false)
const requestsStatus = ref('pending')
const approveModal = reactive({ open: false, request: null as VisitRequestItem | null, check_in: '', check_out: '', saving: false, error: '' })
const rejectModal = reactive({ open: false, request: null as VisitRequestItem | null, reason: '', saving: false, error: '' })

function openApproveModal(r: VisitRequestItem) {
  Object.assign(approveModal, { open: true, request: r, check_in: r.preferred_start, check_out: r.preferred_end, saving: false, error: '' })
}
async function confirmApprove() {
  if (!approveModal.request) return
  approveModal.saving = true
  approveModal.error = ''
  try {
    await api.post(`/api/v1/timeshare/visit-requests/${approveModal.request.id}/approve`, {
      check_in: approveModal.check_in, check_out: approveModal.check_out,
    })
    toast.success(t('backoffice.timeshare.msg.requestApproved'))
    approveModal.open = false
    await loadVisitRequests()
  } catch (e) {
    approveModal.error = (e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.requestApproveError')
  } finally { approveModal.saving = false }
}

function openRejectModal(r: VisitRequestItem) {
  Object.assign(rejectModal, { open: true, request: r, reason: '', saving: false, error: '' })
}
async function confirmReject() {
  if (!rejectModal.request) return
  if (rejectModal.reason.trim().length < 3) { rejectModal.error = t('backoffice.timeshare.reasonTooShort'); return }
  rejectModal.saving = true
  rejectModal.error = ''
  try {
    await api.post(`/api/v1/timeshare/visit-requests/${rejectModal.request.id}/reject`, { reason: rejectModal.reason.trim() })
    toast.success(t('backoffice.timeshare.msg.requestRejected'))
    rejectModal.open = false
    await loadVisitRequests()
  } catch (e) {
    rejectModal.error = (e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.requestRejectError')
  } finally { rejectModal.saving = false }
}

// ── Support Tickets (خدمة عملاء التايم شير المستقلة، 2026-08-03) ───────────
interface TicketReply { id: number; author_type: string; message: string; created_at: string }
interface SupportTicket {
  id: number; contract_id: number; subject: string; status: string
  customer_name?: string; contract_number?: string
  replies: TicketReply[]
}
const supportTickets = ref<SupportTicket[]>([])
const ticketsLoading = ref(false)
const ticketsStatus = ref('open')
const ticketModal = reactive({ open: false, ticket: null as SupportTicket | null, reply: '', sending: false })

async function loadSupportTickets() {
  ticketsLoading.value = true
  try {
    const r = await api.get('/api/v1/timeshare/support-tickets', { params: { branch_id: branchId.value, status: ticketsStatus.value || undefined } })
    supportTickets.value = r.data
  } catch { toast.error(t('backoffice.timeshare.msg.loadTicketsError')) } finally { ticketsLoading.value = false }
}

function openTicketModal(tk: SupportTicket) {
  Object.assign(ticketModal, { open: true, ticket: tk, reply: '', sending: false })
}
async function sendTicketReply() {
  if (!ticketModal.ticket || !ticketModal.reply.trim()) return
  ticketModal.sending = true
  try {
    const r = await api.post(`/api/v1/timeshare/support-tickets/${ticketModal.ticket.id}/reply`, { message: ticketModal.reply.trim() })
    ticketModal.ticket = r.data
    const idx = supportTickets.value.findIndex(x => x.id === r.data.id)
    if (idx !== -1) supportTickets.value[idx] = r.data
    ticketModal.reply = ''
  } catch (e) { toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.replyError')) }
  finally { ticketModal.sending = false }
}
async function updateTicketStatus(tk: SupportTicket, status: string) {
  try {
    const r = await api.patch(`/api/v1/timeshare/support-tickets/${tk.id}`, { status })
    const idx = supportTickets.value.findIndex(x => x.id === tk.id)
    if (idx !== -1) supportTickets.value[idx] = r.data
    if (ticketModal.ticket?.id === tk.id) ticketModal.ticket = r.data
    toast.success(t('backoffice.timeshare.msg.ticketStatusUpdated'))
  } catch (e) { toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.ticketStatusError')) }
}

// ── Timeshare Staff (طلب Mohamed 2026-08-03: مدير التايم شير بيدير
// موظفينه بنفسه، منعزل تمامًا عن شاشة الموظفين العامة) ─────────────────────
interface StaffMember { id: number; email: string; full_name: string; phone: string | null; is_active: boolean; must_change_password: boolean }
const timeshareStaff = ref<StaffMember[]>([])
const staffLoading = ref(false)
const newStaffModal = reactive({
  open: false, saving: false, email: '', full_name: '', phone: '', error: '',
  result: null as { email: string; temporary_password: string } | null,
})

async function loadTimeshareStaff() {
  if (!auth.hasRole('timeshare_admin')) return
  staffLoading.value = true
  try {
    const r = await api.get('/api/v1/timeshare/staff', { params: { branch_id: branchId.value } })
    timeshareStaff.value = r.data
  } catch { toast.error(t('backoffice.timeshare.msg.loadStaffError')) } finally { staffLoading.value = false }
}

function openNewStaffModal() {
  Object.assign(newStaffModal, { open: true, saving: false, email: '', full_name: '', phone: '', error: '', result: null })
}
async function createStaff() {
  if (!newStaffModal.email.trim() || !newStaffModal.full_name.trim()) {
    newStaffModal.error = t('backoffice.timeshare.staffFormRequired')
    return
  }
  newStaffModal.saving = true
  newStaffModal.error = ''
  try {
    const r = await api.post('/api/v1/timeshare/staff', {
      branch_id: branchId.value, email: newStaffModal.email.trim(),
      full_name: newStaffModal.full_name.trim(), phone: newStaffModal.phone.trim() || undefined,
      preferred_language: locale.value === 'en' ? 'en' : 'ar',
    })
    newStaffModal.result = r.data
    await loadTimeshareStaff()
  } catch (e) {
    newStaffModal.error = (e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.createStaffError')
  } finally { newStaffModal.saving = false }
}
async function toggleStaffActive(s: StaffMember) {
  try {
    const r = await api.patch(`/api/v1/timeshare/staff/${s.id}`, { is_active: !s.is_active })
    const idx = timeshareStaff.value.findIndex(x => x.id === s.id)
    if (idx !== -1) timeshareStaff.value[idx] = r.data
    toast.success(t('backoffice.timeshare.msg.staffStatusUpdated'))
  } catch (e) { toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.staffStatusError')) }
}

// ── تقارير جاهزة بدون زرار تحميل (طلب Mohamed 2026-08-03) — الـendpoints
// كانت موجودة في الباك إند من زمان، بس مفيش أي UI بينده عليها. نفس نمط
// SalesDashboardView.vue's exportExcel بالظبط (blob → object URL → <a download>).
// بيستخدم installMonth (فلتر الشهر الموجود بالفعل في تاب الأقساط) بدل ref
// منفصل — لو فاضي، الشهر الحالي.
const exportingMonthly = ref(false)
async function downloadMonthlyReport() {
  const month = installMonth.value || new Date().toISOString().slice(0, 7)
  exportingMonthly.value = true
  try {
    const res = await api.get('/api/v1/timeshare/installments/monthly-report', {
      params: { branch_id: branchId.value, month },
      responseType: 'blob',
    })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `timeshare-collection-${month}.xlsx`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 5000)
  } catch { toast.error(t('backoffice.timeshare.msg.reportError')) } finally { exportingMonthly.value = false }
}

const downloadingPdfId = ref<number | null>(null)
async function downloadContractPdf(c: Contract) {
  downloadingPdfId.value = c.id
  try {
    const res = await api.get(`/api/v1/timeshare/contracts/${c.id}/pdf`, { responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `timeshare-${c.contract_number}.pdf`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 5000)
  } catch { toast.error(t('backoffice.timeshare.msg.pdfError')) } finally { downloadingPdfId.value = null }
}

const fmt = (v: number | string | null | undefined) => formatMoney(v, 'EGP')
const formatDateValue = (d?: string) => {
  if (!d) return '—'
  try { return formatDate(d, { day: 'numeric', month: 'short', year: 'numeric' }) }
  catch { return d }
}

const filteredClients = computed(() => {
  let list = allClients.value
  if (clientSearch.value) {
    const q = clientSearch.value.toLowerCase()
    list = list.filter(c => c.customer_name?.toLowerCase().includes(q) || c.customer_phone?.includes(q) || c.contract_number?.toLowerCase().includes(q))
  }
  if (clientStatusFilter.value) list = list.filter(c => c.status === clientStatusFilter.value)
  if (clientRoomFilter.value) list = list.filter(c => c.room_type === clientRoomFilter.value)
  return list
})

// ── Loaders ──────────────────────────────────────────────────────────────
async function loadSummary() {
  try { const r = await api.get('/api/v1/timeshare/cs-summary', { params: { branch_id: branchId.value } }); summary.value = r.data }
  catch (e) { toast.error(t('backoffice.timeshare.msg.loadSummaryError')) }
}

async function loadVisitRequests() {
  requestsLoading.value = true
  try {
    const r = await api.get('/api/v1/timeshare/visit-requests', { params: { branch_id: branchId.value, status: requestsStatus.value || undefined } })
    visitRequests.value = r.data
  } catch { toast.error(t('backoffice.timeshare.msg.loadRequestsError')) } finally { requestsLoading.value = false }
}

async function loadCalendar() {
  calLoading.value = true
  try {
    const r = await api.get('/api/v1/timeshare/calendar', { params: { branch_id: branchId.value, year: calYear.value } })
    calendar.value = r.data
  } catch (e) { toast.error(t('backoffice.timeshare.msg.loadCalendarError')) } finally { calLoading.value = false }
}

// ── Print calendar (لعرض تقديمي في اجتماعات المبيعات) ──────────────────────
// طباعة/تصدير PDF من المتصفح مباشرة — نفس نمط QRGeneratorView.printSelected،
// لأن كالندر 52 أسبوع أصلاً layout مرئي (شبكة)، مش بيانات صفوف تصلح لملف Excel
function escapeHtml(s: string): string {
  const map: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }
  return s.replace(/[&<>"']/g, (ch) => map[ch])
}

function calContractPrintClass(c: CalendarContract): string {
  if (c.rci_included) return 'rci'
  const m: Record<string, string> = { '2R': 'r2', '4R': 'r4', '6R': 'r6' }
  return m[c.room_type] || 'other'
}

function printCalendarView() {
  if (!calendar.value.calendar.length) { toast.error(t('backoffice.timeshare.msg.noCalendarData')); return }

  const dir = locale.value === 'ar' ? 'rtl' : 'ltr'
  const exportedAt = formatDate(new Date(), { dateStyle: 'medium', timeStyle: 'short' } as Intl.DateTimeFormatOptions)
  const exportedBy = auth.user?.full_name || auth.user?.username || '—'

  const monthsHtml = calendar.value.calendar.map(month => `
    <div class="month-card">
      <div class="month-header">${escapeHtml(month.month_name)} ${calYear.value}</div>
      <div class="weeks">
        ${month.weeks.map(week => `
          <div class="week-row ${week.is_current ? 'current' : ''} ${week.is_past && !week.is_current ? 'past' : ''}">
            <span class="week-no">${week.week}</span>
            <span class="week-date">${escapeHtml(week.start_date?.slice(5) ?? '')}</span>
            <span class="week-contracts">
              ${week.contracts.length
                ? week.contracts.map((c: CalendarContract) => `<span class="tag ${calContractPrintClass(c)}">${escapeHtml((c.customer_name ?? '').split(' ').slice(0, 2).join(' '))}${c.rci_included ? ' ✦' : ''}</span>`).join('')
                : '<span class="empty">—</span>'}
            </span>
          </div>
        `).join('')}
      </div>
    </div>
  `).join('')

  const html = `<!DOCTYPE html>
<html dir="${dir}" lang="${locale.value}">
<head>
<meta charset="UTF-8">
<title>${escapeHtml(t('backoffice.timeshare.calendarPrintTitle', { year: calYear.value }))}</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: 'Cairo', 'Segoe UI', sans-serif; margin: 0; padding: 24px; color: #1a1a1a; }
  .header { text-align: center; margin-bottom: 20px; }
  .header h1 { font-size: 20px; margin: 0 0 4px; }
  .header .meta { font-size: 11px; color: #666; }
  .legend { display: flex; gap: 14px; justify-content: center; margin-bottom: 18px; font-size: 11px; flex-wrap: wrap; }
  .legend span { display: inline-flex; align-items: center; gap: 4px; }
  .swatch { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
  .month-card { border: 1px solid #ddd; border-radius: 10px; overflow: hidden; page-break-inside: avoid; }
  .month-header { background: #f5f5f4; padding: 6px 10px; font-weight: 700; font-size: 12px; border-bottom: 1px solid #eee; }
  .week-row { display: flex; align-items: center; gap: 6px; padding: 3px 8px; border-bottom: 1px solid #f3f3f3; font-size: 9px; }
  .week-row.current { background: #fffbeb; }
  .week-row.past { opacity: 0.45; }
  .week-no { width: 16px; text-align: center; color: #999; font-weight: 700; }
  .week-date { width: 40px; color: #aaa; }
  .week-contracts { flex: 1; display: flex; flex-wrap: wrap; gap: 3px; }
  .tag { padding: 1px 5px; border-radius: 6px; font-weight: 700; border: 1px solid; }
  .tag.rci { background: #f3e8ff; color: #7e22ce; border-color: #e9d5ff; }
  .tag.r2 { background: #e0f2fe; color: #0369a1; border-color: #bae6fd; }
  .tag.r4 { background: #fef3c7; color: #b45309; border-color: #fde68a; }
  .tag.r6 { background: #d1fae5; color: #047857; border-color: #a7f3d0; }
  .tag.other { background: #f5f5f4; color: #78716c; border-color: #e7e5e4; }
  .empty { color: #d6d3d1; }
  @media print {
    @page { size: A4 landscape; margin: 12mm; }
    .no-print { display: none; }
  }
</style>
</head>
<body>
  <div class="header">
    <h1>📅 ${escapeHtml(t('backoffice.timeshare.calendarPrintTitle', { year: calYear.value }))}</h1>
    <div class="meta">
      ${escapeHtml(t('backoffice.timeshare.bookedWeeksPrint', { count: calendar.value.total_booked_weeks || 0 }))} ·
      ${escapeHtml(t('backoffice.timeshare.exportedByPrint', { name: exportedBy }))} · ${escapeHtml(t('backoffice.timeshare.exportedAtPrint', { date: exportedAt }))}
    </div>
  </div>
  <div class="legend">
    <span><span class="swatch" style="background:#bae6fd"></span> 2R</span>
    <span><span class="swatch" style="background:#fde68a"></span> 4R</span>
    <span><span class="swatch" style="background:#a7f3d0"></span> 6R</span>
    <span><span class="swatch" style="background:#e9d5ff"></span> RCI ✦</span>
  </div>
  <div class="grid">
    ${monthsHtml}
  </div>
  <div class="no-print" style="text-align:center;margin-top:20px;color:#999;font-size:12px;">${escapeHtml(t('backoffice.timeshare.printHint'))}</div>
</body>
</html>`

  const win = window.open('', '_blank')
  if (!win) { toast.error(t('backoffice.timeshare.msg.popupBlocked')); return }
  win.document.write(html)
  win.document.close()
  win.focus()
  setTimeout(() => win.print(), 500)
}

async function loadClients() {
  clientsLoading.value = true
  try {
    const clients: Contract[] = []
    let page = 1
    const size = 100
    while (true) {
      const response = await api.get('/api/v1/timeshare/contracts', {
        params: { branch_id: branchId.value, page, size },
      })
      const pageItems: Contract[] = response.data?.items ?? []
      clients.push(...pageItems)
      if (clients.length >= Number(response.data?.total ?? 0) || pageItems.length < size) break
      page += 1
    }
    allClients.value = clients
  } catch (e) { toast.error(t('backoffice.timeshare.msg.loadClientsError')) } finally { clientsLoading.value = false }
}

async function loadInstallments() {
  installLoading.value = true
  try {
    const params: Record<string, string | number | undefined> = { branch_id: branchId.value ?? undefined, limit: 300 }
    if (installStatus.value) params.status = installStatus.value
    if (installMonth.value) params.month = installMonth.value
    if (installSearch.value) params.search = installSearch.value
    const r = await api.get('/api/v1/timeshare/installments', { params })
    installments.value = r.data.installments ?? []
    installSummary.value = r.data.summary ?? { overdue_total: 0, pending_total: 0 }
  } catch (e) { toast.error(t('backoffice.timeshare.msg.loadInstallmentsError')) } finally { installLoading.value = false }
}

async function loadMaintenanceDues() {
  maintLoading.value = true
  try {
    const params: Record<string, string | number | undefined> = { branch_id: branchId.value ?? undefined, limit: 300 }
    if (maintStatus.value) params.status = maintStatus.value
    if (maintSearch.value) params.search = maintSearch.value
    const r = await api.get('/api/v1/timeshare/maintenance-dues', { params })
    maintenanceDues.value = r.data.maintenance_dues ?? []
    maintSummary.value = r.data.summary ?? { overdue_total: 0, pending_total: 0 }
  } catch (e) { toast.error(t('backoffice.timeshare.msg.loadMaintenanceDuesError')) } finally { maintLoading.value = false }
}

// 2026-08-04: التوليد التلقائي (توقيع عقد جديد + 1 يناير سنويًا) بيغطي
// الحالة العادية بالكامل — الزرار ده أداة استرجاع لحالات استثنائية بس
// (مثلاً maintenance_fee اتغيّر بعد التوليد وعايز تعيد التوليد لسنة قديمة).
// نفس endpoint الـCelery task بالظبط، idempotent (بيتخطى أي عقد عنده
// مستحق للسنة دي بالفعل).
const generatingDues = ref(false)
async function generateMaintenanceDues() {
  const fee_year = new Date().getFullYear()
  const ok = await confirm({
    message: t('backoffice.timeshare.confirmGenerateDues', { year: fee_year }),
    confirmText: t('backoffice.timeshare.yesGenerate'),
  })
  if (!ok) return
  generatingDues.value = true
  try {
    const r = await api.post('/api/v1/timeshare/maintenance-dues/generate', null, {
      params: { branch_id: branchId.value, fee_year },
    })
    toast.success(t('backoffice.timeshare.msg.duesGenerated', { count: r.data.created }))
    await loadMaintenanceDues()
  } catch (e) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.duesGenerateError'))
  } finally { generatingDues.value = false }
}

async function refreshAll() {
  loading.value = true
  await Promise.all([
    loadSummary(), loadCalendar(), loadClients(), loadInstallments(), loadMaintenanceDues(), loadUnits(), loadWaitlist(),
    loadVisitRequests(), loadSupportTickets(), loadTimeshareStaff(),
  ])
  loading.value = false
}

// ── Pay ──────────────────────────────────────────────────────────────────
function openPayModal(inst: Installment) {
  Object.assign(payModal, {
    open: true, saving: false, inst_id: inst.id,
    customer_name: inst.customer_name ?? '',
    due_amount: inst.amount - inst.paid_amount,
    amount: inst.amount - inst.paid_amount, method: 'cash', receipt_number: '',
  })
}

function openPayModalForContract(c: Contract) {
  const next = c.installments_list?.find(i => i.status !== 'paid')
  if (!next) return
  openPayModal({ ...next, customer_name: c.customer_name })
}

async function submitPayment() {
  if (!payModal.amount || payModal.saving) return
  payModal.saving = true
  try {
    await api.post(`/api/v1/timeshare/installments/${payModal.inst_id}/pay`, {
      paid_amount: payModal.amount, payment_method: payModal.method,
      receipt_number: payModal.receipt_number || undefined,
    })
    payModal.open = false
    toast.success(t('backoffice.timeshare.msg.paymentRecorded'))
    await Promise.all([loadSummary(), loadInstallments(), loadClients()])
  } catch (e: unknown) { toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.paymentError')) }
  finally { payModal.saving = false }
}

// ── Maintenance Pay ──────────────────────────────────────────────────────
function openMaintenancePayModal(due: MaintenanceDue) {
  Object.assign(maintPayModal, {
    open: true, saving: false, due_id: due.id,
    customer_name: due.customer_name ?? '',
    due_amount: due.amount - due.paid_amount,
    amount: due.amount - due.paid_amount, method: 'cash', receipt_number: '',
  })
}

function openMaintenancePayModalForContract(c: Contract) {
  const next = c.maintenance_dues_list?.find(d => d.status !== 'paid')
  if (!next) return
  openMaintenancePayModal({ ...next, customer_name: c.customer_name })
}

async function submitMaintenancePayment() {
  if (!maintPayModal.amount || maintPayModal.saving) return
  maintPayModal.saving = true
  try {
    await api.post(`/api/v1/timeshare/maintenance-dues/${maintPayModal.due_id}/pay`, {
      paid_amount: maintPayModal.amount, payment_method: maintPayModal.method,
      receipt_number: maintPayModal.receipt_number || undefined,
    })
    maintPayModal.open = false
    toast.success(t('backoffice.timeshare.msg.paymentRecorded'))
    await Promise.all([loadSummary(), loadMaintenanceDues(), loadClients()])
  } catch (e: unknown) { toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.paymentError')) }
  finally { maintPayModal.saving = false }
}

// ── Status / Cancel ──────────────────────────────────────────────────────
const statusSaving = ref<number | null>(null)
async function toggleStatus(c: Contract) {
  const next = c.status === 'active' ? 'suspended' : 'active'
  statusSaving.value = c.id
  try {
    await api.patch(`/api/v1/timeshare/contracts/${c.id}`, { status: next })
    c.status = next
    toast.success(next === 'active' ? t('backoffice.timeshare.msg.contractActivated') : t('backoffice.timeshare.msg.contractSuspended'))
    await loadSummary()
  } catch (e: unknown) { toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.statusChangeError')) }
  finally { statusSaving.value = null }
}

async function cancelContract(c: Contract) {
  const ok = await confirm({
    message: t('backoffice.timeshare.confirmCancelContract', { name: c.customer_name }),
    danger: true, confirmText: t('backoffice.timeshare.yesCancel'), cancelText: t('backoffice.timeshare.cancelAction'),
  })
  if (!ok) return
  try {
    await api.post(`/api/v1/timeshare/contracts/${c.id}/cancel`, { cancel_amount: 0 })
    c.status = 'cancelled'
    toast.success(t('backoffice.timeshare.msg.contractCancelled'))
    await loadSummary()
  } catch (e: unknown) { toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.cancelError')) }
}

// ── #10: نقل وحدة ────────────────────────────────────────────────────────
// مقصور على نفس room_type بالتصميم (راجع services.transfer_unit — تغيير
// النوع "ترقية" قرار تسعير منفصل)، فقائمة الوحدات المرشّحة هنا بتتفلتر
// بنفس نوع العقد فقط.
const transferModal = reactive({ open: false, contract: null as Contract | null, new_unit_id: '' as number | '', reason: '', saving: false })

function openTransferModal(c: Contract) {
  transferModal.contract = c
  transferModal.new_unit_id = ''
  transferModal.reason = ''
  transferModal.open = true
}

const transferCandidateUnits = computed(() => {
  if (!transferModal.contract) return []
  return units.value.filter(u =>
    u.unit_type === transferModal.contract!.room_type &&
    u.id !== transferModal.contract!.unit_id &&
    u.status !== 'maintenance',
  )
})

async function saveTransfer() {
  if (!transferModal.contract) return
  if (!transferModal.new_unit_id) { toast.error(t('backoffice.timeshare.msg.selectNewUnit')); return }
  if (!transferModal.reason.trim() || transferModal.reason.trim().length < 3) {
    toast.error(t('backoffice.timeshare.msg.transferReasonRequired')); return
  }
  transferModal.saving = true
  try {
    const { data } = await api.post(`/api/v1/timeshare/contracts/${transferModal.contract.id}/transfer-unit`, {
      new_unit_id: transferModal.new_unit_id, reason: transferModal.reason,
    })
    transferModal.contract.unit_id = data.unit_id
    toast.success(t('backoffice.timeshare.msg.unitTransferred'))
    transferModal.open = false
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.transferError'))
  } finally {
    transferModal.saving = false
  }
}

// ── Excel Import ─────────────────────────────────────────────────────────
function onFilePicked(e: Event) {
  const target = e.target as HTMLInputElement
  importModal.file = target.files?.[0] ?? null
}

async function submitImport() {
  if (!importModal.file || importModal.uploading) return
  importModal.uploading = true
  try {
    const form = new FormData()
    form.append('file', importModal.file)
    const r = await api.post('/api/v1/timeshare/contracts/import-excel', form, {
      headers: { 'Content-Type': 'multipart/form-data' }, params: { branch_id: branchId.value },
    })
    importModal.result = r.data
    await Promise.all([loadClients(), loadSummary()])
  } catch (e: unknown) {
    const msg = (e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.importError')
    importModal.result = { error: msg }
    toast.error(msg)
  } finally { importModal.uploading = false }
}

// ── Badges ───────────────────────────────────────────────────────────────
type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

function roomTypeBadge(type: string) {
  const m: Record<string, string> = {
    '2R': 'bg-sky-100 text-sky-700 dark:bg-sky-950/60 dark:text-sky-300',
    '4R': 'bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300',
    '6R': 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300',
  }
  return `text-xs px-2 py-1 rounded-full font-bold ${m[type] || 'bg-stone-100 dark:bg-gray-700 text-stone-600 dark:text-stone-300'}`
}
const contractStatusVariant: Record<string, BadgeVariant> = {
  active: 'success', suspended: 'warning', cancelled: 'danger', expired: 'neutral',
}
function statusLabel(s: string) {
  const icons: Record<string, string> = { active: '✅', suspended: '⏸️', cancelled: '❌', expired: '⌛' }
  const labels: Record<string, string> = {
    active: t('backoffice.timeshare.contractStatus.active'), suspended: t('backoffice.timeshare.contractStatus.suspended'),
    cancelled: t('backoffice.timeshare.contractStatus.cancelled'), expired: t('backoffice.timeshare.contractStatus.expired'),
  }
  return labels[s] ? `${icons[s]} ${labels[s]}` : s
}
const payStatusVariant: Record<string, BadgeVariant> = {
  paid: 'success', pending: 'warning', overdue: 'danger', partial: 'info',
}
function payLabel(s: string) {
  const icons: Record<string, string> = { paid: '✅', pending: '⏳', overdue: '🔴', partial: '🔵' }
  const labels: Record<string, string> = {
    paid: t('backoffice.timeshare.payStatus.paid'), pending: t('backoffice.timeshare.payStatus.pending'),
    overdue: t('backoffice.timeshare.payStatus.overdue'), partial: t('backoffice.timeshare.payStatus.partial'),
  }
  return labels[s] ? `${icons[s]} ${labels[s]}` : s
}
function calContractClass(c: CalendarContract) {
  if (c.rci_included) return 'bg-purple-100 text-purple-700 border-purple-200 dark:bg-purple-950/60 dark:text-purple-300 dark:border-purple-800'
  const m: Record<string, string> = {
    '2R': 'bg-sky-100 text-sky-700 border-sky-200 dark:bg-sky-950/60 dark:text-sky-300 dark:border-sky-800',
    '4R': 'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-950/60 dark:text-amber-300 dark:border-amber-800',
    '6R': 'bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-950/60 dark:text-emerald-300 dark:border-emerald-800',
  }
  return m[c.room_type] || 'bg-stone-100 dark:bg-gray-700 text-stone-600 dark:text-stone-300 border-stone-200 dark:border-border'
}

onMounted(refreshAll)
</script>

<template>
  <div class="space-y-5 pb-6">
    <div class="flex items-start justify-between flex-wrap gap-4">
      <div>
        <h2 class="text-2xl font-black text-gray-950 dark:text-gray-100">{{ t('backoffice.timeshare.title') }}</h2>
        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">{{ t('backoffice.timeshare.workspaceHint') }}</p>
      </div>
      <div class="flex items-center gap-2">
        <AppButton
          v-if="auth.hasRole('timeshare_admin')"
          variant="outline"
          @click="importModal.open = true; importModal.result = null"
        >
          <AppIcon name="upload" size="sm" /> {{ t('backoffice.timeshare.importExcel') }}
        </AppButton>
        <AppButton variant="outline" :loading="loading" @click="refreshAll">
          <AppIcon name="refresh" size="sm" /> {{ t('backoffice.timeshare.refresh') }}
        </AppButton>
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex gap-1 bg-stone-100 dark:bg-gray-800 p-1.5 rounded-2xl overflow-x-auto" role="tablist" :aria-label="t('backoffice.timeshare.tabsLabel')">
      <button v-for="tab in TABS" :key="tab.id" @click="activeTab = tab.id"
        type="button" role="tab" :aria-selected="activeTab === tab.id"
        :class="['min-h-[44px] px-4 py-2 rounded-xl text-sm font-bold whitespace-nowrap transition-all', activeTab === tab.id ? 'bg-white dark:bg-surface shadow-sm text-gray-950 dark:text-gray-100' : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white']">
        {{ tab.icon }} {{ tab.label }}
        <span v-if="('badge' in tab) && (tab.badge ?? 0) > 0"
          class="ms-1.5 inline-flex min-w-[18px] items-center justify-center rounded-full bg-red-600 px-1.5 py-0.5 text-[10px] font-black leading-none text-white">
          {{ tab.badge }}
        </span>
      </button>
    </div>

    <!-- ══ DASHBOARD ══ -->
    <div v-if="activeTab === 'dashboard'" class="space-y-5">
      <div class="grid grid-cols-2 lg:grid-cols-5 gap-3">
        <AppCard padding="md">
          <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase tracking-wide mb-2">{{ t('backoffice.timeshare.activeContracts') }}</p>
          <p class="text-2xl font-black text-gray-900 dark:text-gray-100">{{ summary.active_contracts || 0 }}</p>
        </AppCard>
        <AppCard padding="md">
          <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase tracking-wide mb-2">{{ t('backoffice.timeshare.occupancyRate') }}</p>
          <p class="text-2xl font-black text-sky-600 dark:text-sky-300">{{ summary.occupancy_rate_pct ?? 0 }}%</p>
          <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">{{ t('backoffice.timeshare.occupancyOfTotal', { occupied: summary.occupied_units || 0, total: summary.total_units || 0 }) }}</p>
        </AppCard>
        <AppCard padding="md">
          <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase tracking-wide mb-2">{{ t('backoffice.timeshare.collectionRate') }}</p>
          <p :class="['text-2xl font-black', (summary.collection_rate_pct||0) >= 50 ? 'text-green-600 dark:text-green-300' : 'text-amber-500 dark:text-amber-300']">
            {{ summary.collection_rate_pct || 0 }}%
          </p>
          <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">{{ t('backoffice.timeshare.ofTotal', { collected: fmt(summary.total_collected), total: fmt(summary.total_value) }) }}</p>
        </AppCard>
        <AppCard padding="md">
          <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase tracking-wide mb-2">{{ t('backoffice.timeshare.overdueAmounts') }}</p>
          <p class="text-2xl font-black text-red-500">{{ fmt(summary.total_overdue) }}</p>
          <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">{{ t('backoffice.timeshare.overdueContractsCount', { count: summary.overdue_contracts_count || 0 }) }}</p>
        </AppCard>
        <AppCard padding="md">
          <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase tracking-wide mb-2">{{ t('backoffice.timeshare.dueThisMonth') }}</p>
          <p class="text-2xl font-black text-amber-500">{{ fmt(summary.this_month_due) }}</p>
        </AppCard>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <AppCard padding="md">
          <div class="flex items-center justify-between mb-4">
            <p class="font-black text-sm text-gray-900 dark:text-gray-100">📅 {{ t('backoffice.timeshare.upcomingVisits') }}</p>
            <AppBadge variant="info" size="sm">{{ summary.upcoming_visits?.length || 0 }}</AppBadge>
          </div>
          <EmptyState v-if="!summary.upcoming_visits?.length" icon="📅" :title="t('backoffice.timeshare.noUpcomingVisits')" />
          <div v-else class="space-y-2">
            <div v-for="v in summary.upcoming_visits" :key="v.id" class="flex items-center justify-between gap-3 p-3 rounded-xl bg-stone-50 dark:bg-gray-800/60 border border-stone-100 dark:border-border/50">
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-1 flex-wrap">
                  <span class="font-bold text-xs text-gray-900 dark:text-gray-100">{{ v.customer_name }}</span>
                  <span v-if="v.room_type" :class="roomTypeBadge(v.room_type)">{{ v.room_type }}</span>
                </div>
                <div class="text-xs text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.weekNumber', { week: v.week_number }) }} · {{ v.visit_start ? formatDateValue(v.visit_start) : '—' }}</div>
              </div>
              <div class="text-end flex-shrink-0">
                <div :class="['text-sm font-black', v.days_until === 0 ? 'text-red-500 dark:text-red-300' : v.days_until <= 7 ? 'text-amber-500 dark:text-amber-300' : 'text-green-600 dark:text-green-300']">
                  {{ v.days_until === 0 ? t('backoffice.timeshare.today') : v.days_until === 1 ? t('backoffice.timeshare.tomorrow') : t('backoffice.timeshare.inDays', { days: v.days_until }) }}
                </div>
                <div v-if="v.customer_phone" class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ v.customer_phone }}</div>
              </div>
            </div>
          </div>
        </AppCard>

        <AppCard padding="md">
          <div class="flex items-center justify-between mb-4">
            <p class="font-black text-sm text-gray-900 dark:text-gray-100">🔴 {{ t('backoffice.timeshare.overdueClients') }}</p>
            <AppBadge variant="danger" size="sm">{{ summary.overdue_clients?.length || 0 }}</AppBadge>
          </div>
          <EmptyState v-if="!summary.overdue_clients?.length" icon="🎉" :title="t('backoffice.timeshare.noOverdue')" />
          <div v-else class="space-y-2">
            <div v-for="c in summary.overdue_clients" :key="c.id" class="flex items-center justify-between gap-3 p-3 rounded-xl bg-red-50 dark:bg-red-950/30 border border-red-100 dark:border-red-900/60">
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-1 flex-wrap">
                  <span class="font-bold text-xs text-gray-900 dark:text-gray-100">{{ c.customer_name }}</span>
                  <span :class="roomTypeBadge(c.room_type)">{{ c.room_type }}</span>
                </div>
                <div class="text-xs text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.pendingInstallmentCount', { count: c.pending_count }) }}<span v-if="c.next_due"> · {{ t('backoffice.timeshare.dueOn', { date: formatDateValue(c.next_due) }) }}</span></div>
              </div>
              <div class="text-end flex-shrink-0">
                <div class="text-sm font-black text-red-500">{{ fmt(c.overdue_amount) }}</div>
                <a v-if="c.customer_phone" :href="`tel:${c.customer_phone}`" class="inline-flex min-h-[44px] items-center text-xs text-gray-500 dark:text-gray-400 hover:text-amber-600 dark:hover:text-amber-300">📞 {{ c.customer_phone }}</a>
              </div>
            </div>
          </div>
        </AppCard>
      </div>
    </div>

    <!-- ══ CALENDAR ══ -->
    <div v-if="activeTab === 'calendar'" class="space-y-4">
      <div class="flex items-center justify-between flex-wrap gap-3">
        <div class="flex items-center gap-3">
          <button type="button" :aria-label="t('backoffice.timeshare.previousYear')" @click="calYear--; loadCalendar()" class="w-11 h-11 rounded-xl bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 hover:bg-stone-50 dark:hover:bg-gray-800 text-lg font-bold">−</button>
          <h3 class="text-lg font-black text-gray-900 dark:text-gray-100">{{ calYear }}</h3>
          <button type="button" :aria-label="t('backoffice.timeshare.nextYear')" @click="calYear++; loadCalendar()" class="w-11 h-11 rounded-xl bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 hover:bg-stone-50 dark:hover:bg-gray-800 text-lg font-bold">＋</button>
        </div>
        <div class="flex items-center gap-3 flex-wrap">
          <span class="text-sm text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.bookedWeeks') }}: <span class="text-amber-600 dark:text-amber-300 font-bold">{{ calendar.total_booked_weeks || 0 }}</span></span>
          <AppButton variant="outline" @click="printCalendarView" :title="t('backoffice.timeshare.printCalendarHint')">
            <AppIcon name="print" size="sm" /> {{ t('backoffice.timeshare.printPdf') }}
          </AppButton>
        </div>
      </div>

      <LoadingState v-if="calLoading" :label="t('backoffice.timeshare.loadingCalendar')" />
      <EmptyState v-else-if="!calendar.calendar.length" icon="📅" :title="t('backoffice.timeshare.noCalendarData')" />
      <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <div v-for="month in calendar.calendar" :key="month.month" class="bg-white dark:bg-surface rounded-2xl border border-stone-200 dark:border-border overflow-hidden shadow-sm">
          <div class="px-4 py-2.5 border-b border-stone-100 dark:border-border/50 bg-stone-50 dark:bg-gray-800/60">
            <p class="font-bold text-xs text-gray-700 dark:text-gray-300">{{ month.month_name }} {{ calYear }}</p>
          </div>
          <div class="divide-y divide-stone-100 dark:divide-border">
            <div v-for="week in month.weeks" :key="week.week"
              :class="['flex items-center gap-2 px-3 py-2.5', week.is_current ? 'bg-amber-50 dark:bg-amber-950/30 border-e-2 border-amber-400' : '', week.is_past && !week.is_current ? 'opacity-55' : '']">
              <div class="flex-shrink-0 w-8 text-center">
                <span :class="['text-xs font-bold rounded-full px-2 py-1', week.is_current ? 'bg-amber-500 text-white' : 'text-gray-500 dark:text-gray-400']">{{ week.week }}</span>
              </div>
              <div class="flex-shrink-0 text-xs text-gray-500 dark:text-gray-400 w-20">{{ week.start_date?.slice(5) }} →</div>
              <div class="flex-1 flex flex-wrap gap-1">
                <span v-if="!week.contracts.length" class="text-xs text-gray-400 dark:text-gray-400">—</span>
                <span v-for="c in week.contracts" :key="c.id" :class="['text-xs px-2 py-1 rounded-lg font-bold border', calContractClass(c)]">
                  {{ c.customer_name.split(' ').slice(0, 2).join(' ') }}
                  <span v-if="c.rci_included" class="ms-1">✦</span>
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ══ CLIENTS ══ -->
    <div v-if="activeTab === 'clients'" class="space-y-4">
      <div class="flex flex-wrap gap-3">
        <div class="flex-1 min-w-64">
          <SearchInput v-model="clientSearch" :placeholder="t('backoffice.timeshare.searchClientsPlaceholder')" :clear-label="t('backoffice.timeshare.clearClientSearch')" />
        </div>
        <select v-model="clientStatusFilter" :aria-label="t('backoffice.timeshare.filterByStatus')" class="min-h-[44px] bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2.5 outline-none">
          <option value="">{{ t('backoffice.timeshare.allStatuses') }}</option>
          <option value="active">{{ t('backoffice.timeshare.contractStatus.active') }}</option>
          <option value="suspended">{{ t('backoffice.timeshare.contractStatus.suspended') }}</option>
          <option value="cancelled">{{ t('backoffice.timeshare.contractStatus.cancelled') }}</option>
        </select>
        <select v-model="clientRoomFilter" :aria-label="t('backoffice.timeshare.filterByRoomType')" class="min-h-[44px] bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2.5 outline-none">
          <option value="">{{ t('backoffice.timeshare.allTypes') }}</option>
          <option value="2R">2R</option><option value="4R">4R</option><option value="6R">6R</option>
        </select>
      </div>

      <LoadingState v-if="clientsLoading" :label="t('backoffice.timeshare.loadingClients')" />
      <div v-else class="space-y-2">
        <EmptyState v-if="!filteredClients.length" icon="👤" :title="t('backoffice.timeshare.noResults')" />
        <div v-for="c in filteredClients" :key="c.id"
          class="bg-white dark:bg-surface rounded-2xl border overflow-hidden transition-all shadow-sm"
          :class="expandedClient === c.id ? 'border-primary-300' : 'border-stone-200 dark:border-border hover:border-stone-300'">

          <div
            class="p-4 cursor-pointer flex items-center gap-4 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-primary-500"
            role="button"
            tabindex="0"
            :aria-expanded="expandedClient === c.id"
            @click="expandedClient = expandedClient === c.id ? null : c.id"
            @keydown.enter="expandedClient = expandedClient === c.id ? null : c.id"
            @keydown.space.prevent="expandedClient = expandedClient === c.id ? null : c.id"
          >
            <div class="w-9 h-9 rounded-xl flex-shrink-0 flex items-center justify-center text-sm font-black" :class="roomTypeBadge(c.room_type)">
              {{ c.customer_name?.charAt(0) || '?' }}
            </div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-bold text-sm text-gray-900 dark:text-gray-100">{{ c.customer_name }}</span>
                <span :class="roomTypeBadge(c.room_type)">{{ c.room_type }}</span>
                <span v-if="c.rci_included" class="text-xs px-2 py-1 rounded-full bg-purple-100 text-purple-700 dark:bg-purple-950/60 dark:text-purple-300 font-bold">RCI</span>
                <AppBadge size="sm" :variant="contractStatusVariant[c.status] ?? 'neutral'">{{ statusLabel(c.status) }}</AppBadge>
              </div>
              <div class="text-xs text-gray-500 dark:text-gray-400 mt-1 flex flex-wrap gap-3">
                <span v-if="c.customer_phone">📞 {{ c.customer_phone }}</span>
                <span>{{ t('backoffice.timeshare.weekNumber', { week: c.week_number || '—' }) }}</span>
                <span>{{ c.contract_number }}</span>
              </div>
            </div>
            <div class="text-end flex-shrink-0 hidden sm:block">
              <div class="text-sm font-black text-green-600 dark:text-green-300">{{ fmt(c.total_value) }}</div>
            </div>
            <button @click.stop="openProfile(c)"
              class="flex-shrink-0 min-h-[44px] px-3 py-2 rounded-xl bg-primary-50 text-primary-700 dark:bg-primary-950/40 dark:text-primary-300 text-xs font-bold border border-primary-200 dark:border-primary-800 hover:bg-primary-100 dark:hover:bg-primary-950/60">
              👤 {{ t('backoffice.timeshare.fullProfile') }}
            </button>
            <div class="text-gray-500 dark:text-gray-400 text-xs flex-shrink-0">{{ expandedClient === c.id ? '▲' : '▼' }}</div>
          </div>

          <div v-if="expandedClient === c.id" class="border-t border-stone-100 dark:border-border/50 p-4 space-y-4">
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
              <div class="space-y-1.5">
                <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-2">{{ t('backoffice.timeshare.contractData') }}</p>
                <div class="flex justify-between gap-3"><span class="text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.contractDuration') }}</span><span>{{ formatDateValue(c.start_date) }} — {{ formatDateValue(c.end_date ?? undefined) }}</span></div>
                <div class="flex justify-between gap-3"><span class="text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.nightsPerYear') }}</span><span class="font-bold text-amber-600 dark:text-amber-300">{{ c.nights_per_year }}</span></div>
                <div v-if="c.nationality" class="flex justify-between gap-3"><span class="text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.nationality') }}</span><span>{{ c.nationality }}</span></div>
                <div v-if="c.maintenance_fee > 0" class="flex justify-between gap-3"><span class="text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.annualMaintenance') }}</span><span class="text-amber-600 dark:text-amber-300">{{ fmt(c.maintenance_fee) }}</span></div>
              </div>
              <div class="space-y-1.5">
                <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-2">{{ t('backoffice.timeshare.financialStatus') }}</p>
                <div class="flex justify-between gap-3"><span class="text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.contractValue') }}</span><span class="font-bold text-green-600 dark:text-green-300">{{ fmt(c.total_value) }}</span></div>
                <div class="flex justify-between gap-3"><span class="text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.downPayment') }}</span><span>{{ fmt(c.down_payment) }}</span></div>
                <div class="flex justify-between gap-3"><span class="text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.installmentCount') }}</span><span>{{ c.installments }}</span></div>
              </div>
            </div>

            <div>
              <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-2">{{ t('backoffice.timeshare.installmentSchedule') }}</p>
              <div v-if="c.installments_list?.length" class="overflow-x-auto">
                <table class="w-full min-w-[520px] text-xs">
                  <thead><tr class="text-gray-500 dark:text-gray-400 border-b border-stone-100 dark:border-border/50">
                    <th class="text-start py-2 ps-1">#</th><th class="text-start py-2">{{ t('backoffice.timeshare.column.dueDate') }}</th>
                    <th class="text-start py-2">{{ t('backoffice.timeshare.column.amount') }}</th><th class="text-start py-2">{{ t('backoffice.timeshare.column.status') }}</th><th></th>
                  </tr></thead>
                  <tbody class="divide-y divide-stone-100">
                    <tr v-for="(p, i) in c.installments_list" :key="p.id">
                      <td class="py-2 ps-1 text-gray-500 dark:text-gray-400">{{ i + 1 }}</td>
                      <td class="py-2 text-gray-600 dark:text-gray-300">{{ formatDateValue(p.due_date) }}</td>
                      <td class="py-1.5 font-bold">{{ fmt(p.amount) }}</td>
                      <td class="py-1.5"><AppBadge size="sm" :variant="payStatusVariant[p.status] ?? 'neutral'">{{ payLabel(p.status) }}</AppBadge></td>
                      <td class="py-1.5">
                        <button v-if="p.status !== 'paid'" @click="openPayModal({ ...p, customer_name: c.customer_name })"
                          class="min-h-[44px] px-3 py-2 rounded-lg bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300 text-xs font-bold border border-green-200 dark:border-green-800 hover:bg-green-100 dark:hover:bg-green-950/60">{{ t('backoffice.timeshare.pay') }}</button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div v-if="c.maintenance_dues_list?.length">
              <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-2">{{ t('backoffice.timeshare.maintenanceDuesSchedule') }}</p>
              <div class="overflow-x-auto">
                <table class="w-full min-w-[520px] text-xs">
                  <thead><tr class="text-gray-500 dark:text-gray-400 border-b border-stone-100 dark:border-border/50">
                    <th class="text-start py-2 ps-1">{{ t('backoffice.timeshare.column.year') }}</th><th class="text-start py-2">{{ t('backoffice.timeshare.column.dueDate') }}</th>
                    <th class="text-start py-2">{{ t('backoffice.timeshare.column.amount') }}</th><th class="text-start py-2">{{ t('backoffice.timeshare.column.status') }}</th><th></th>
                  </tr></thead>
                  <tbody class="divide-y divide-stone-100">
                    <tr v-for="d in c.maintenance_dues_list" :key="d.id">
                      <td class="py-2 ps-1 text-gray-500 dark:text-gray-400">{{ d.fee_year }}</td>
                      <td class="py-2 text-gray-600 dark:text-gray-300">{{ formatDateValue(d.due_date) }}</td>
                      <td class="py-1.5 font-bold">{{ fmt(d.amount) }}</td>
                      <td class="py-1.5"><AppBadge size="sm" :variant="payStatusVariant[d.status] ?? 'neutral'">{{ payLabel(d.status) }}</AppBadge></td>
                      <td class="py-1.5">
                        <button v-if="d.status !== 'paid'" @click="openMaintenancePayModal({ ...d, customer_name: c.customer_name })"
                          class="min-h-[44px] px-3 py-2 rounded-lg bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300 text-xs font-bold border border-green-200 dark:border-green-800 hover:bg-green-100 dark:hover:bg-green-950/60">{{ t('backoffice.timeshare.pay') }}</button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div class="flex flex-wrap gap-2 pt-2 border-t border-stone-100 dark:border-border/50">
              <button @click="openPayModalForContract(c)" class="min-h-[44px] px-4 py-2 rounded-xl bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300 text-sm font-bold border border-green-200 dark:border-green-800 hover:bg-green-100 dark:hover:bg-green-950/60">💰 {{ t('backoffice.timeshare.recordPayment') }}</button>
              <button v-if="c.maintenance_dues_list?.some(d => d.status !== 'paid')" @click="openMaintenancePayModalForContract(c)" class="min-h-[44px] px-4 py-2 rounded-xl bg-teal-50 text-teal-700 dark:bg-teal-950/40 dark:text-teal-300 text-sm font-bold border border-teal-200 dark:border-teal-800 hover:bg-teal-100 dark:hover:bg-teal-950/60">🛠️ {{ t('backoffice.timeshare.recordMaintenancePayment') }}</button>
              <a v-if="c.customer_phone" :href="`tel:${c.customer_phone}`" class="min-h-[44px] inline-flex items-center px-4 py-2 rounded-xl bg-sky-50 text-sky-700 dark:bg-sky-950/40 dark:text-sky-300 text-sm font-bold border border-sky-200 dark:border-sky-800 hover:bg-sky-100 dark:hover:bg-sky-950/60">📞 {{ t('backoffice.timeshare.call') }}</a>
              <button @click="downloadContractPdf(c)" :disabled="downloadingPdfId === c.id"
                class="min-h-[44px] px-4 py-2 rounded-xl bg-stone-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300 text-sm font-bold border border-stone-200 dark:border-border hover:bg-stone-200 dark:hover:bg-gray-700 disabled:opacity-40">📄 {{ downloadingPdfId === c.id ? t('backoffice.timeshare.saving') : t('backoffice.timeshare.downloadPdf') }}</button>
              <button v-if="auth.hasRole('timeshare_admin') && c.status === 'active'" @click="toggleStatus(c)" :disabled="statusSaving === c.id"
                class="min-h-[44px] px-4 py-2 rounded-xl bg-yellow-50 text-yellow-700 dark:bg-yellow-950/40 dark:text-yellow-300 text-sm font-bold border border-yellow-200 dark:border-yellow-800 hover:bg-yellow-100 dark:hover:bg-yellow-950/60 disabled:opacity-40">⏸️ {{ t('backoffice.timeshare.suspend') }}</button>
              <button v-else-if="auth.hasRole('timeshare_admin') && c.status === 'suspended'" @click="toggleStatus(c)" :disabled="statusSaving === c.id"
                class="min-h-[44px] px-4 py-2 rounded-xl bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300 text-sm font-bold border border-green-200 dark:border-green-800 hover:bg-green-100 dark:hover:bg-green-950/60 disabled:opacity-40">▶️ {{ t('backoffice.timeshare.activate') }}</button>
              <button v-if="auth.hasRole('timeshare_admin') && c.unit_id && !['cancelled','expired'].includes(c.status)" @click="openTransferModal(c)"
                class="min-h-[44px] px-4 py-2 rounded-xl bg-violet-50 text-violet-700 dark:bg-violet-950/40 dark:text-violet-300 text-sm font-bold border border-violet-200 dark:border-violet-800 hover:bg-violet-100 dark:hover:bg-violet-950/60">🔑 {{ t('backoffice.timeshare.transferUnit') }}</button>
              <button v-if="!['cancelled','expired'].includes(c.status)" @click="openNewWaitlistModal(c)"
                class="min-h-[44px] px-4 py-2 rounded-xl bg-indigo-50 text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300 text-sm font-bold border border-indigo-200 dark:border-indigo-800 hover:bg-indigo-100 dark:hover:bg-indigo-950/60">⏳ {{ t('backoffice.timeshare.joinWaitlist') }}</button>
              <AppButton v-if="auth.hasRole('timeshare_admin') && c.status !== 'cancelled'" variant="danger" class="min-h-[44px]" @click="cancelContract(c)">🗑️ {{ t('backoffice.timeshare.cancelAction') }}</AppButton>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ══ INSTALLMENTS ══ -->
    <div v-if="activeTab === 'installments'" class="space-y-4">
      <div class="flex flex-wrap gap-3">
        <div class="min-h-[44px] inline-flex items-center px-4 py-2 rounded-xl bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 text-sm font-bold text-red-700 dark:text-red-300">🔴 {{ t('backoffice.timeshare.overdueColon', { amount: fmt(installSummary.overdue_total) }) }}</div>
        <div class="min-h-[44px] inline-flex items-center px-4 py-2 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 text-sm font-bold text-amber-700 dark:text-amber-300">⏳ {{ t('backoffice.timeshare.pendingColon', { amount: fmt(installSummary.pending_total) }) }}</div>
      </div>
      <div class="flex flex-wrap gap-3">
        <input v-model="installSearch" @keyup.enter="loadInstallments" :placeholder="t('backoffice.timeshare.searchByCustomerName')"
          class="min-h-[44px] flex-1 min-w-48 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 text-sm rounded-xl px-4 py-2 outline-none" />
        <select v-model="installStatus" :aria-label="t('backoffice.timeshare.filterByStatus')" @change="loadInstallments" class="min-h-[44px] bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2">
          <option value="">{{ t('backoffice.timeshare.allStatuses') }}</option><option value="overdue">🔴 {{ t('backoffice.timeshare.payStatus.overdue') }}</option>
          <option value="pending">⏳ {{ t('backoffice.timeshare.payStatus.pending') }}</option><option value="paid">✅ {{ t('backoffice.timeshare.payStatus.paid') }}</option><option value="partial">🔵 {{ t('backoffice.timeshare.payStatus.partial') }}</option>
        </select>
        <input v-model="installMonth" :aria-label="t('backoffice.timeshare.filterByMonth')" @change="loadInstallments" type="month" class="min-h-[44px] bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2" />
        <button v-if="auth.hasRole('timeshare_admin')" @click="downloadMonthlyReport" :disabled="exportingMonthly"
          class="min-h-[44px] px-4 py-2 rounded-xl bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 text-sm font-bold border border-emerald-200 dark:border-emerald-800 hover:bg-emerald-100 disabled:opacity-50">
          📊 {{ exportingMonthly ? t('backoffice.timeshare.saving') : t('backoffice.timeshare.downloadMonthlyReport') }}
        </button>
      </div>

      <LoadingState v-if="installLoading" :label="t('backoffice.timeshare.loadingInstallments')" />
      <AppCard v-else padding="none">
        <EmptyState v-if="!installments.length" icon="💰" :title="t('backoffice.timeshare.noResults')" />
        <div v-else class="overflow-x-auto">
        <table class="w-full min-w-[720px] text-sm">
          <thead class="bg-stone-50 dark:bg-gray-800/60"><tr>
            <th class="text-start px-4 py-3 text-gray-500 dark:text-gray-400 font-bold">{{ t('backoffice.timeshare.column.customer') }}</th>
            <th class="text-start px-4 py-3 text-gray-500 dark:text-gray-400 font-bold">{{ t('backoffice.timeshare.column.dueDate') }}</th>
            <th class="text-start px-4 py-3 text-gray-500 dark:text-gray-400 font-bold">{{ t('backoffice.timeshare.column.amount') }}</th>
            <th class="text-start px-4 py-3 text-gray-500 dark:text-gray-400 font-bold">{{ t('backoffice.timeshare.column.status') }}</th>
            <th class="px-4 py-3"></th>
          </tr></thead>
          <tbody class="divide-y divide-stone-100 dark:divide-border">
            <tr v-for="p in installments" :key="p.id" :class="p.status === 'overdue' ? 'bg-red-50/50 dark:bg-red-950/20' : ''">
              <td class="px-4 py-3">
                <div class="font-bold text-gray-900 dark:text-gray-100">{{ p.customer_name }}</div>
                <div class="text-xs text-gray-500 dark:text-gray-400">{{ p.customer_phone }}</div>
              </td>
              <td class="px-4 py-3"><span :class="p.status === 'overdue' ? 'text-red-600 dark:text-red-300 font-bold' : 'text-gray-600 dark:text-gray-300'">{{ formatDateValue(p.due_date) }}</span></td>
              <td class="px-4 py-3 font-bold">{{ fmt(p.amount) }}</td>
              <td class="px-4 py-3"><AppBadge size="sm" :variant="payStatusVariant[p.status] ?? 'neutral'">{{ payLabel(p.status) }}</AppBadge></td>
              <td class="px-4 py-3">
                <button v-if="p.status !== 'paid'" @click="openPayModal(p)"
                  class="min-h-[44px] px-3 py-2 rounded-xl bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300 text-xs font-bold border border-green-200 dark:border-green-800 hover:bg-green-100">💰 {{ t('backoffice.timeshare.pay') }}</button>
              </td>
            </tr>
          </tbody>
        </table>
        </div>
      </AppCard>
    </div>

    <!-- ══ MAINTENANCE DUES ══ -->
    <div v-if="activeTab === 'maintenance'" class="space-y-4">
      <div class="flex flex-wrap gap-3">
        <div class="min-h-[44px] inline-flex items-center px-4 py-2 rounded-xl bg-red-50 dark:bg-red-950/30 border border-red-200 dark:border-red-900 text-sm font-bold text-red-700 dark:text-red-300">🔴 {{ t('backoffice.timeshare.overdueColon', { amount: fmt(maintSummary.overdue_total) }) }}</div>
        <div class="min-h-[44px] inline-flex items-center px-4 py-2 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 text-sm font-bold text-amber-700 dark:text-amber-300">⏳ {{ t('backoffice.timeshare.pendingColon', { amount: fmt(maintSummary.pending_total) }) }}</div>
      </div>
      <div class="flex flex-wrap gap-3">
        <input v-model="maintSearch" @keyup.enter="loadMaintenanceDues" :placeholder="t('backoffice.timeshare.searchByCustomerName')"
          class="min-h-[44px] flex-1 min-w-48 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 text-sm rounded-xl px-4 py-2 outline-none" />
        <select v-model="maintStatus" :aria-label="t('backoffice.timeshare.filterByStatus')" @change="loadMaintenanceDues" class="min-h-[44px] bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2">
          <option value="">{{ t('backoffice.timeshare.allStatuses') }}</option><option value="overdue">🔴 {{ t('backoffice.timeshare.payStatus.overdue') }}</option>
          <option value="pending">⏳ {{ t('backoffice.timeshare.payStatus.pending') }}</option><option value="paid">✅ {{ t('backoffice.timeshare.payStatus.paid') }}</option><option value="partial">🔵 {{ t('backoffice.timeshare.payStatus.partial') }}</option>
        </select>
        <button v-if="auth.hasRole('timeshare_admin')" @click="generateMaintenanceDues" :disabled="generatingDues"
          class="min-h-[44px] px-4 py-2 rounded-xl bg-teal-50 text-teal-700 dark:bg-teal-950/40 dark:text-teal-300 text-sm font-bold border border-teal-200 dark:border-teal-800 hover:bg-teal-100 dark:hover:bg-teal-950/60 disabled:opacity-50">
          🛠️ {{ generatingDues ? t('backoffice.timeshare.saving') : t('backoffice.timeshare.generateDues') }}
        </button>
      </div>

      <LoadingState v-if="maintLoading" :label="t('backoffice.timeshare.loadingMaintenanceDues')" />
      <AppCard v-else padding="none">
        <EmptyState v-if="!maintenanceDues.length" icon="🛠️" :title="t('backoffice.timeshare.noResults')" />
        <div v-else class="overflow-x-auto">
        <table class="w-full min-w-[720px] text-sm">
          <thead class="bg-stone-50 dark:bg-gray-800/60"><tr>
            <th class="text-start px-4 py-3 text-gray-500 dark:text-gray-400 font-bold">{{ t('backoffice.timeshare.column.customer') }}</th>
            <th class="text-start px-4 py-3 text-gray-500 dark:text-gray-400 font-bold">{{ t('backoffice.timeshare.column.year') }}</th>
            <th class="text-start px-4 py-3 text-gray-500 dark:text-gray-400 font-bold">{{ t('backoffice.timeshare.column.dueDate') }}</th>
            <th class="text-start px-4 py-3 text-gray-500 dark:text-gray-400 font-bold">{{ t('backoffice.timeshare.column.amount') }}</th>
            <th class="text-start px-4 py-3 text-gray-500 dark:text-gray-400 font-bold">{{ t('backoffice.timeshare.column.status') }}</th>
            <th class="px-4 py-3"></th>
          </tr></thead>
          <tbody class="divide-y divide-stone-100 dark:divide-border">
            <tr v-for="d in maintenanceDues" :key="d.id" :class="d.status === 'overdue' ? 'bg-red-50/50 dark:bg-red-950/20' : ''">
              <td class="px-4 py-3">
                <div class="font-bold text-gray-900 dark:text-gray-100">{{ d.customer_name }}</div>
                <div class="text-xs text-gray-500 dark:text-gray-400">{{ d.customer_phone }}</div>
              </td>
              <td class="px-4 py-3 text-gray-600 dark:text-gray-300">{{ d.fee_year }}</td>
              <td class="px-4 py-3"><span :class="d.status === 'overdue' ? 'text-red-600 dark:text-red-300 font-bold' : 'text-gray-600 dark:text-gray-300'">{{ formatDateValue(d.due_date) }}</span></td>
              <td class="px-4 py-3 font-bold">{{ fmt(d.amount) }}</td>
              <td class="px-4 py-3"><AppBadge size="sm" :variant="payStatusVariant[d.status] ?? 'neutral'">{{ payLabel(d.status) }}</AppBadge></td>
              <td class="px-4 py-3">
                <button v-if="d.status !== 'paid'" @click="openMaintenancePayModal(d)"
                  class="min-h-[44px] px-3 py-2 rounded-xl bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300 text-xs font-bold border border-green-200 dark:border-green-800 hover:bg-green-100">💰 {{ t('backoffice.timeshare.pay') }}</button>
              </td>
            </tr>
          </tbody>
        </table>
        </div>
      </AppCard>
    </div>

    <!-- ══ VISIT REQUESTS (بوابة العميل العامة، 2026-08-03) ══ -->
    <div v-if="activeTab === 'requests'" class="space-y-4">
      <select v-model="requestsStatus" @change="loadVisitRequests" class="min-h-[44px] bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2">
        <option value="pending">⏳ {{ t('backoffice.timeshare.requestStatus.pending') }}</option>
        <option value="approved">✅ {{ t('backoffice.timeshare.requestStatus.approved') }}</option>
        <option value="rejected">❌ {{ t('backoffice.timeshare.requestStatus.rejected') }}</option>
        <option value="">{{ t('backoffice.timeshare.allStatuses') }}</option>
      </select>

      <LoadingState v-if="requestsLoading" :label="t('backoffice.timeshare.loadingRequests')" />
      <AppCard v-else padding="none">
        <EmptyState v-if="!visitRequests.length" icon="📝" :title="t('backoffice.timeshare.noResults')" />
        <div v-else class="divide-y divide-stone-100 dark:divide-border">
          <div v-for="r in visitRequests" :key="r.id" class="p-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div class="font-bold text-gray-900 dark:text-gray-100">{{ r.customer_name }} — {{ r.contract_number }}</div>
              <div class="text-sm text-gray-600 dark:text-gray-300">{{ formatDateValue(r.preferred_start) }} → {{ formatDateValue(r.preferred_end) }}</div>
              <div v-if="r.notes" class="text-xs text-gray-500 dark:text-gray-400 mt-1">💬 {{ r.notes }}</div>
              <div v-if="r.rejection_reason" class="text-xs text-red-600 dark:text-red-300 mt-1">✋ {{ r.rejection_reason }}</div>
            </div>
            <div class="flex items-center gap-2">
              <AppBadge size="sm" :variant="r.status === 'pending' ? 'warning' : r.status === 'approved' ? 'success' : 'neutral'">{{ t(`backoffice.timeshare.requestStatus.${r.status}`) }}</AppBadge>
              <template v-if="r.status === 'pending' && auth.hasRole('timeshare_admin')">
                <button @click="openApproveModal(r)" class="min-h-[44px] px-3 py-2 rounded-xl bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300 text-xs font-bold border border-green-200 dark:border-green-800 hover:bg-green-100">✅ {{ t('backoffice.timeshare.approve') }}</button>
                <button @click="openRejectModal(r)" class="min-h-[44px] px-3 py-2 rounded-xl bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300 text-xs font-bold border border-red-200 dark:border-red-800 hover:bg-red-100">❌ {{ t('backoffice.timeshare.reject') }}</button>
              </template>
            </div>
          </div>
        </div>
      </AppCard>
    </div>

    <!-- ══ SUPPORT TICKETS (خدمة عملاء التايم شير المستقلة، 2026-08-03) ══ -->
    <div v-if="activeTab === 'support'" class="space-y-4">
      <select v-model="ticketsStatus" @change="loadSupportTickets" class="min-h-[44px] bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2">
        <option value="open">🟡 {{ t('backoffice.timeshare.ticketStatus.open') }}</option>
        <option value="in_progress">🔵 {{ t('backoffice.timeshare.ticketStatus.in_progress') }}</option>
        <option value="resolved">✅ {{ t('backoffice.timeshare.ticketStatus.resolved') }}</option>
        <option value="closed">⚪ {{ t('backoffice.timeshare.ticketStatus.closed') }}</option>
        <option value="">{{ t('backoffice.timeshare.allStatuses') }}</option>
      </select>

      <LoadingState v-if="ticketsLoading" :label="t('backoffice.timeshare.loadingTickets')" />
      <AppCard v-else padding="none">
        <EmptyState v-if="!supportTickets.length" icon="💬" :title="t('backoffice.timeshare.noResults')" />
        <div v-else class="divide-y divide-stone-100 dark:divide-border">
          <button v-for="tk in supportTickets" :key="tk.id" type="button" @click="openTicketModal(tk)"
            class="w-full text-start p-4 flex items-center justify-between gap-3 hover:bg-stone-50 dark:hover:bg-gray-800/40">
            <div>
              <div class="font-bold text-gray-900 dark:text-gray-100">{{ tk.subject }}</div>
              <div class="text-sm text-gray-600 dark:text-gray-300">{{ tk.customer_name }} — {{ tk.contract_number }}</div>
            </div>
            <AppBadge size="sm" :variant="tk.status === 'open' ? 'warning' : tk.status === 'resolved' || tk.status === 'closed' ? 'success' : 'info'">{{ t(`backoffice.timeshare.ticketStatus.${tk.status}`) }}</AppBadge>
          </button>
        </div>
      </AppCard>
    </div>

    <!-- ══ TIMESHARE STAFF (طلب Mohamed: مدير التايم شير بيدير موظفينه بنفسه، 2026-08-03) ══ -->
    <div v-if="activeTab === 'staff' && auth.hasRole('timeshare_admin')" class="space-y-4">
      <AppButton @click="openNewStaffModal">➕ {{ t('backoffice.timeshare.newStaff') }}</AppButton>

      <LoadingState v-if="staffLoading" :label="t('backoffice.timeshare.loadingStaff')" />
      <AppCard v-else padding="none">
        <EmptyState v-if="!timeshareStaff.length" icon="🧑‍💼" :title="t('backoffice.timeshare.noResults')" />
        <div v-else class="divide-y divide-stone-100 dark:divide-border">
          <div v-for="s in timeshareStaff" :key="s.id" class="p-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div class="font-bold text-gray-900 dark:text-gray-100">{{ s.full_name }}</div>
              <div class="text-sm text-gray-600 dark:text-gray-300">{{ s.email }}{{ s.phone ? ` — ${s.phone}` : '' }}</div>
            </div>
            <div class="flex items-center gap-2">
              <AppBadge size="sm" :variant="s.is_active ? 'success' : 'neutral'">{{ s.is_active ? t('backoffice.timeshare.staffActive') : t('backoffice.timeshare.staffInactive') }}</AppBadge>
              <button @click="toggleStaffActive(s)"
                class="min-h-[44px] px-3 py-2 rounded-xl text-xs font-bold border"
                :class="s.is_active ? 'bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300 border-red-200 dark:border-red-800 hover:bg-red-100' : 'bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300 border-green-200 dark:border-green-800 hover:bg-green-100'">
                {{ s.is_active ? t('backoffice.timeshare.deactivate') : t('backoffice.timeshare.activate') }}
              </button>
            </div>
          </div>
        </div>
      </AppCard>
    </div>

    <div v-if="activeTab === 'waitlist'" class="space-y-4">
      <LoadingState v-if="waitlistLoading" :label="t('backoffice.timeshare.loadingWaitlist')" />
      <AppCard v-else padding="none">
        <EmptyState v-if="!waitlist.length" icon="⏳" :title="t('backoffice.timeshare.noResults')" />
        <div v-else class="divide-y divide-stone-100 dark:divide-border">
          <div v-for="entry in waitlist" :key="entry.id" class="p-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div class="font-bold text-gray-900 dark:text-gray-100">
                {{ contractById[entry.contract_id]?.customer_name ?? `#${entry.contract_id}` }}
                <span class="text-sm font-normal text-gray-500 dark:text-gray-400">— {{ contractById[entry.contract_id]?.contract_number }}</span>
              </div>
              <div class="text-sm text-gray-600 dark:text-gray-300">{{ formatDateValue(entry.requested_start) }} — {{ formatDateValue(entry.requested_end) }}</div>
              <div v-if="entry.status === 'notified' && entry.expires_at" class="text-xs text-amber-600 dark:text-amber-400">
                {{ t('backoffice.timeshare.waitlistExpiresAt', { date: formatDateValue(entry.expires_at) }) }}
              </div>
            </div>
            <div class="flex items-center gap-2">
              <AppBadge size="sm" :variant="entry.status === 'notified' ? 'warning' : 'info'">
                {{ t(`backoffice.timeshare.waitlistStatus.${entry.status}`, entry.status) }}
              </AppBadge>
              <template v-if="auth.hasRole('timeshare_admin')">
                <button @click="updateWaitlistStatus(entry, 'confirmed')" :disabled="updatingWaitlistId === entry.id"
                  class="min-h-[44px] px-3 py-2 rounded-xl text-xs font-bold border bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300 border-green-200 dark:border-green-800 hover:bg-green-100 disabled:opacity-40">
                  ✅ {{ t('backoffice.timeshare.waitlistConfirm') }}
                </button>
                <button @click="updateWaitlistStatus(entry, 'cancelled')" :disabled="updatingWaitlistId === entry.id"
                  class="min-h-[44px] px-3 py-2 rounded-xl text-xs font-bold border bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300 border-red-200 dark:border-red-800 hover:bg-red-100 disabled:opacity-40">
                  ❌ {{ t('backoffice.timeshare.waitlistCancel') }}
                </button>
              </template>
            </div>
          </div>
        </div>
      </AppCard>
    </div>

    <!-- ══ NEW WAITLIST ENTRY MODAL ══ -->
    <AppModal :open="newWaitlistModal" :title="`⏳ ${t('backoffice.timeshare.joinWaitlist')}`" size="sm" @close="newWaitlistModal = false">
      <div v-if="newWaitlistContract" class="space-y-3">
        <p class="text-sm text-gray-600 dark:text-gray-300">{{ newWaitlistContract.customer_name }} — {{ newWaitlistContract.contract_number }}</p>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.timeshare.scheduleVisit.checkIn') }}
          <input v-model="newWaitlistForm.requested_start" type="date" class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.timeshare.scheduleVisit.checkOut') }}
          <input v-model="newWaitlistForm.requested_end" type="date" class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>
        <AppButton class="w-full min-h-[44px]" :disabled="savingWaitlist" @click="submitNewWaitlist">{{ savingWaitlist ? t('backoffice.timeshare.saving') : t('backoffice.timeshare.save') }}</AppButton>
      </div>
    </AppModal>

    <div v-if="activeTab === 'units' && auth.hasRole('timeshare_admin')" class="space-y-4">
      <AppButton @click="openNewUnitModal">➕ {{ t('backoffice.timeshare.newUnit') }}</AppButton>

      <AppCard padding="none">
        <EmptyState v-if="!units.length" icon="🏘️" :title="t('backoffice.timeshare.noResults')" />
        <div v-else class="divide-y divide-stone-100 dark:divide-border">
          <div v-for="u in units" :key="u.id" class="p-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <div class="font-bold text-gray-900 dark:text-gray-100">{{ u.unit_number }} <span class="text-sm font-normal text-gray-500 dark:text-gray-400">({{ u.unit_type }})</span></div>
              <div v-if="u.notes" class="text-sm text-gray-500 dark:text-gray-400">{{ u.notes }}</div>
            </div>
            <div class="flex items-center gap-2">
              <AppBadge size="sm" :variant="u.status === 'available' ? 'success' : u.status === 'maintenance' ? 'warning' : 'info'">
                {{ t(`backoffice.timeshare.unitStatus.${u.status}`, u.status) }}
              </AppBadge>
              <button v-if="u.status !== 'occupied'" @click="toggleUnitMaintenance(u)" :disabled="togglingUnitId === u.id"
                class="min-h-[44px] px-3 py-2 rounded-xl text-xs font-bold border disabled:opacity-40"
                :class="u.status === 'maintenance' ? 'bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300 border-green-200 dark:border-green-800 hover:bg-green-100' : 'bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300 border-amber-200 dark:border-amber-800 hover:bg-amber-100'">
                {{ u.status === 'maintenance' ? t('backoffice.timeshare.markAvailable') : t('backoffice.timeshare.markMaintenance') }}
              </button>
            </div>
          </div>
        </div>
      </AppCard>
    </div>

    <!-- ══ NEW UNIT MODAL ══ -->
    <AppModal :open="newUnitModal" :title="`🏘️ ${t('backoffice.timeshare.newUnit')}`" size="sm" @close="newUnitModal = false">
      <div class="space-y-3">
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.timeshare.unitNumber') }}
          <input v-model="newUnitForm.unit_number" type="text" class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.timeshare.unitType') }}
          <select v-model="newUnitForm.unit_type" class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2">
            <option value="2R">2R</option>
            <option value="4R">4R</option>
            <option value="6R">6R</option>
          </select>
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.timeshare.unitNotesOptional') }}
          <textarea v-model="newUnitForm.notes" rows="2" class="w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm resize-none" />
        </label>
        <AppButton class="w-full min-h-[44px]" :disabled="savingUnit" @click="submitNewUnit">{{ savingUnit ? t('backoffice.timeshare.saving') : t('backoffice.timeshare.save') }}</AppButton>
      </div>
    </AppModal>

    <!-- ══ APPROVE VISIT REQUEST MODAL ══ -->
    <AppModal :open="approveModal.open" :title="`✅ ${t('backoffice.timeshare.approveRequestTitle')}`" size="sm" @close="approveModal.open = false">
      <div v-if="approveModal.request" class="space-y-3">
        <p class="text-sm text-gray-600 dark:text-gray-300">{{ approveModal.request.customer_name }} — {{ approveModal.request.contract_number }}</p>
        <p class="text-xs text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.approveRequestHint') }}</p>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.timeshare.scheduleVisit.checkIn') }}
          <input v-model="approveModal.check_in" type="date" class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.timeshare.scheduleVisit.checkOut') }}
          <input v-model="approveModal.check_out" type="date" class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>
        <p v-if="approveModal.error" class="text-sm text-red-600 dark:text-red-400">{{ approveModal.error }}</p>
        <AppButton class="w-full min-h-[44px]" :disabled="approveModal.saving" @click="confirmApprove">{{ approveModal.saving ? t('backoffice.timeshare.saving') : t('backoffice.timeshare.confirmApprove') }}</AppButton>
      </div>
    </AppModal>

    <!-- ══ REJECT VISIT REQUEST MODAL ══ -->
    <AppModal :open="rejectModal.open" :title="`❌ ${t('backoffice.timeshare.rejectRequestTitle')}`" size="sm" @close="rejectModal.open = false">
      <div v-if="rejectModal.request" class="space-y-3">
        <p class="text-sm text-gray-600 dark:text-gray-300">{{ rejectModal.request.customer_name }} — {{ rejectModal.request.contract_number }}</p>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.timeshare.rejectionReason') }}
          <textarea v-model="rejectModal.reason" rows="3" class="w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm resize-none" />
        </label>
        <p v-if="rejectModal.error" class="text-sm text-red-600 dark:text-red-400">{{ rejectModal.error }}</p>
        <AppButton variant="danger" class="w-full min-h-[44px]" :disabled="rejectModal.saving" @click="confirmReject">{{ rejectModal.saving ? t('backoffice.timeshare.saving') : t('backoffice.timeshare.confirmReject') }}</AppButton>
      </div>
    </AppModal>

    <!-- ══ SUPPORT TICKET MODAL ══ -->
    <AppModal :open="ticketModal.open" :title="ticketModal.ticket?.subject ?? ''" size="md" @close="ticketModal.open = false">
      <div v-if="ticketModal.ticket" class="space-y-4">
        <div class="flex items-center gap-2">
          <select :value="ticketModal.ticket.status" @change="updateTicketStatus(ticketModal.ticket, ($event.target as HTMLSelectElement).value)"
            class="min-h-[44px] bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2">
            <option value="open">🟡 {{ t('backoffice.timeshare.ticketStatus.open') }}</option>
            <option value="in_progress">🔵 {{ t('backoffice.timeshare.ticketStatus.in_progress') }}</option>
            <option value="resolved">✅ {{ t('backoffice.timeshare.ticketStatus.resolved') }}</option>
            <option value="closed">⚪ {{ t('backoffice.timeshare.ticketStatus.closed') }}</option>
          </select>
        </div>
        <div class="space-y-2 max-h-72 overflow-y-auto">
          <div v-for="rep in ticketModal.ticket.replies" :key="rep.id"
            :class="['max-w-[80%] rounded-2xl px-4 py-2 text-sm', rep.author_type === 'owner' ? 'bg-stone-100 dark:bg-gray-800' : 'bg-blue-50 dark:bg-blue-950/40 ms-auto']">
            <div class="text-xs font-bold text-gray-500 dark:text-gray-400 mb-1">{{ rep.author_type === 'owner' ? t('backoffice.timeshare.ticketFromOwner') : t('backoffice.timeshare.ticketFromStaff') }}</div>
            {{ rep.message }}
          </div>
        </div>
        <div v-if="ticketModal.ticket.status !== 'closed'" class="flex gap-2">
          <textarea v-model="ticketModal.reply" rows="2" :placeholder="t('backoffice.timeshare.ticketReplyPlaceholder')"
            class="flex-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm resize-none" />
          <AppButton :disabled="ticketModal.sending || !ticketModal.reply.trim()" @click="sendTicketReply">{{ t('backoffice.timeshare.send') }}</AppButton>
        </div>
      </div>
    </AppModal>

    <!-- ══ NEW TIMESHARE STAFF MODAL ══ -->
    <AppModal :open="newStaffModal.open" :title="`➕ ${t('backoffice.timeshare.newStaff')}`" size="sm" @close="newStaffModal.open = false">
      <div v-if="!newStaffModal.result" class="space-y-3">
        <AppInput v-model="newStaffModal.full_name" :label="t('backoffice.timeshare.staffFullName')" />
        <AppInput v-model="newStaffModal.email" type="email" :label="t('backoffice.timeshare.staffEmail')" />
        <AppInput v-model="newStaffModal.phone" :label="t('backoffice.timeshare.staffPhone')" />
        <p v-if="newStaffModal.error" class="text-sm text-red-600 dark:text-red-400">{{ newStaffModal.error }}</p>
        <AppButton class="w-full min-h-[44px]" :disabled="newStaffModal.saving" @click="createStaff">{{ newStaffModal.saving ? t('backoffice.timeshare.saving') : t('backoffice.timeshare.createStaff') }}</AppButton>
      </div>
      <div v-else class="space-y-3">
        <div class="rounded-2xl bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 p-4 text-sm text-amber-800 dark:text-amber-200">
          {{ t('backoffice.timeshare.staffCredentialsWarning') }}
        </div>
        <p class="text-sm"><span class="font-bold">{{ t('backoffice.timeshare.staffEmail') }}:</span> {{ newStaffModal.result.email }}</p>
        <p class="text-sm"><span class="font-bold">{{ t('backoffice.timeshare.staffTempPassword') }}:</span> <code class="bg-stone-100 dark:bg-gray-800 px-2 py-1 rounded-lg">{{ newStaffModal.result.temporary_password }}</code></p>
        <AppButton class="w-full min-h-[44px]" @click="newStaffModal.open = false">{{ t('backoffice.timeshare.done') }}</AppButton>
      </div>
    </AppModal>

    <!-- ══ TRANSFER UNIT MODAL (#10) ══ -->
    <AppModal :open="transferModal.open" :title="`🔑 ${t('backoffice.timeshare.transferUnit')}`" size="sm" @close="transferModal.open = false">
      <div v-if="transferModal.contract" class="space-y-3">
        <p class="text-sm text-gray-600 dark:text-gray-300">
          {{ transferModal.contract.customer_name }} — {{ t('backoffice.timeshare.currentUnit') }}:
          <span class="font-bold">{{ transferModal.contract.unit_id ? (unitNumberById[transferModal.contract.unit_id] ?? `#${transferModal.contract.unit_id}`) : '—' }}</span>
        </p>
        <select v-model="transferModal.new_unit_id" class="min-h-[44px] w-full bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm">
          <option value="">{{ t('backoffice.timeshare.selectNewUnitOfType', { type: transferModal.contract.room_type }) }}</option>
          <option v-for="u in transferCandidateUnits" :key="u.id" :value="u.id" :disabled="u.status === 'maintenance'">
            {{ u.unit_number }}{{ u.status === 'maintenance' ? ` (${t('backoffice.timeshare.underMaintenance')})` : '' }}
          </option>
        </select>
        <p v-if="transferCandidateUnits.length === 0" class="text-xs text-amber-600 dark:text-amber-300">{{ t('backoffice.timeshare.noCandidateUnits') }}</p>
        <input v-model="transferModal.reason" type="text" :placeholder="t('backoffice.timeshare.transferReasonPlaceholder')"
          class="min-h-[44px] w-full bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        <AppButton class="w-full" :loading="transferModal.saving" @click="saveTransfer">{{ t('backoffice.timeshare.confirmTransfer') }}</AppButton>
      </div>
    </AppModal>

    <!-- ══ PAY MODAL ══ -->
    <AppModal :open="payModal.open" :title="`💰 ${t('backoffice.timeshare.recordPayment')}`" size="sm" @close="payModal.open = false">
      <p class="text-sm text-gray-600 dark:text-gray-300 mb-4">{{ payModal.customer_name }}</p>
      <div class="space-y-3">
        <div>
          <label class="text-xs text-gray-600 dark:text-gray-300 font-semibold block mb-1">{{ t('backoffice.timeshare.amountPaid') }}</label>
          <input v-model.number="payModal.amount" type="number" min="1" :placeholder="t('backoffice.timeshare.duePlaceholder', { amount: fmt(payModal.due_amount) })"
            class="min-h-[44px] w-full bg-stone-50 dark:bg-gray-800/60 border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 text-sm rounded-xl px-4 py-2.5 outline-none focus:border-primary-500" />
        </div>
        <div>
          <label class="text-xs text-gray-600 dark:text-gray-300 font-semibold block mb-1">{{ t('backoffice.timeshare.paymentMethod') }}</label>
          <select v-model="payModal.method" class="min-h-[44px] w-full bg-stone-50 dark:bg-gray-800/60 border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 text-sm rounded-xl px-4 py-2.5 outline-none">
            <option value="cash">{{ t('backoffice.timeshare.paymentMethodCash') }}</option><option value="card">{{ t('backoffice.timeshare.paymentMethodCard') }}</option>
            <option value="bank_transfer">{{ t('backoffice.timeshare.paymentMethodBankTransfer') }}</option><option value="other">{{ t('backoffice.timeshare.paymentMethodOther') }}</option>
          </select>
        </div>
        <div>
          <label class="text-xs text-gray-600 dark:text-gray-300 font-semibold block mb-1">{{ t('backoffice.timeshare.receiptNumberOptional') }}</label>
          <input v-model="payModal.receipt_number" class="min-h-[44px] w-full bg-stone-50 dark:bg-gray-800/60 border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 text-sm rounded-xl px-4 py-2.5 outline-none" />
        </div>
      </div>
      <template #footer>
        <div class="flex gap-3">
          <AppButton variant="primary" block :loading="payModal.saving" :disabled="!payModal.amount" @click="submitPayment">
            ✅ {{ t('backoffice.timeshare.confirmPayment') }}
          </AppButton>
          <AppButton variant="ghost" @click="payModal.open = false">{{ t('backoffice.timeshare.cancelAction') }}</AppButton>
        </div>
      </template>
    </AppModal>

    <!-- ══ MAINTENANCE PAY MODAL ══ -->
    <AppModal :open="maintPayModal.open" :title="`🛠️ ${t('backoffice.timeshare.recordMaintenancePayment')}`" size="sm" @close="maintPayModal.open = false">
      <p class="text-sm text-gray-600 dark:text-gray-300 mb-4">{{ maintPayModal.customer_name }}</p>
      <div class="space-y-3">
        <div>
          <label class="text-xs text-gray-600 dark:text-gray-300 font-semibold block mb-1">{{ t('backoffice.timeshare.amountPaid') }}</label>
          <input v-model.number="maintPayModal.amount" type="number" min="1" :placeholder="t('backoffice.timeshare.duePlaceholder', { amount: fmt(maintPayModal.due_amount) })"
            class="min-h-[44px] w-full bg-stone-50 dark:bg-gray-800/60 border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 text-sm rounded-xl px-4 py-2.5 outline-none focus:border-primary-500" />
        </div>
        <div>
          <label class="text-xs text-gray-600 dark:text-gray-300 font-semibold block mb-1">{{ t('backoffice.timeshare.paymentMethod') }}</label>
          <select v-model="maintPayModal.method" class="min-h-[44px] w-full bg-stone-50 dark:bg-gray-800/60 border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 text-sm rounded-xl px-4 py-2.5 outline-none">
            <option value="cash">{{ t('backoffice.timeshare.paymentMethodCash') }}</option><option value="card">{{ t('backoffice.timeshare.paymentMethodCard') }}</option>
            <option value="bank_transfer">{{ t('backoffice.timeshare.paymentMethodBankTransfer') }}</option><option value="other">{{ t('backoffice.timeshare.paymentMethodOther') }}</option>
          </select>
        </div>
        <div>
          <label class="text-xs text-gray-600 dark:text-gray-300 font-semibold block mb-1">{{ t('backoffice.timeshare.receiptNumberOptional') }}</label>
          <input v-model="maintPayModal.receipt_number" class="min-h-[44px] w-full bg-stone-50 dark:bg-gray-800/60 border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 text-sm rounded-xl px-4 py-2.5 outline-none" />
        </div>
      </div>
      <template #footer>
        <div class="flex gap-3">
          <AppButton variant="primary" block :loading="maintPayModal.saving" :disabled="!maintPayModal.amount" @click="submitMaintenancePayment">
            ✅ {{ t('backoffice.timeshare.confirmPayment') }}
          </AppButton>
          <AppButton variant="ghost" @click="maintPayModal.open = false">{{ t('backoffice.timeshare.cancelAction') }}</AppButton>
        </div>
      </template>
    </AppModal>

    <!-- ══ IMPORT MODAL ══ -->
    <AppModal v-if="auth.hasRole('timeshare_admin')" :open="importModal.open" :title="`📥 ${t('backoffice.timeshare.importContractsTitle')}`" @close="importModal.open = false">
      <p class="text-sm text-gray-600 dark:text-gray-300 mb-4">
        {{ t('backoffice.timeshare.importHint') }}
      </p>
      <input type="file" accept=".xlsx,.xls" @change="onFilePicked"
        class="min-h-[44px] w-full text-sm text-gray-700 dark:text-gray-300 file:me-3 file:py-2 file:px-4 file:rounded-xl file:border-0 file:bg-primary-50 dark:file:bg-primary-950/40 file:text-primary-700 dark:file:text-primary-300 file:font-bold" />
      <div v-if="importModal.result" class="mt-4 p-3 rounded-xl text-sm" :class="importModal.result.error ? 'bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-300' : 'bg-green-50 dark:bg-green-950/30 text-green-700 dark:text-green-300'">
        <div v-if="importModal.result.error">{{ importModal.result.error }}</div>
        <div v-else>
          ✅ {{ t('backoffice.timeshare.importedCount', { count: importModal.result.imported }) }}
          <span v-if="importModal.result.skipped"> · {{ t('backoffice.timeshare.skippedCount', { count: importModal.result.skipped }) }}</span>
          <div v-if="importModal.result.errors?.length" class="mt-2 text-red-500">
            <div v-for="(err, i) in importModal.result.errors" :key="i">{{ err }}</div>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="flex gap-3">
          <AppButton variant="primary" block :loading="importModal.uploading" :disabled="!importModal.file" @click="submitImport">
            📤 {{ t('backoffice.timeshare.importAction') }}
          </AppButton>
          <AppButton variant="ghost" @click="importModal.open = false">{{ t('backoffice.timeshare.close') }}</AppButton>
        </div>
      </template>
    </AppModal>

    <!-- ══ CUSTOMER PROFILE (أجمّع كل عقود/زيارات/أقساط/تقييمات نفس العميل) ══ -->
    <AppModal :open="profileModal.open" :title="t('backoffice.timeshare.fullProfileTitle', { name: profileCustomerName })" size="lg" @close="profileModal.open = false">
      <LoadingState v-if="profileModal.loading" :label="t('backoffice.timeshare.loadingProfile')" />
      <div v-else class="space-y-5 text-sm">
        <!-- Totals -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
            <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-1">{{ t('backoffice.timeshare.contractCount') }}</p>
            <p class="font-black text-gray-900 dark:text-gray-100">{{ profileModal.contracts.length }}</p>
          </div>
          <div class="bg-green-50 dark:bg-green-950/30 rounded-xl p-3">
            <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-1">{{ t('backoffice.timeshare.collected') }}</p>
            <p class="font-black text-green-600 dark:text-green-300">{{ fmt(profileTotals.collected) }}</p>
          </div>
          <div class="bg-red-50 dark:bg-red-950/30 rounded-xl p-3">
            <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-1">{{ t('backoffice.timeshare.overdue') }}</p>
            <p class="font-black text-red-600 dark:text-red-300">{{ fmt(profileTotals.overdue) }}</p>
          </div>
          <div class="bg-amber-50 dark:bg-amber-950/30 rounded-xl p-3">
            <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-1">{{ t('backoffice.timeshare.pending') }}</p>
            <p class="font-black text-amber-600 dark:text-amber-300">{{ fmt(profileTotals.pending) }}</p>
          </div>
        </div>

        <!-- Contracts -->
        <div>
          <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-2">{{ t('backoffice.timeshare.contractsCount', { count: profileModal.contracts.length }) }}</p>
          <div class="space-y-1.5">
            <div v-for="c in profileModal.contracts" :key="c.id" class="flex items-center justify-between gap-2 p-2.5 rounded-xl bg-stone-50 dark:bg-gray-800/60 border border-stone-100 dark:border-border/50">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-bold text-gray-900 dark:text-gray-100">{{ c.contract_number }}</span>
                <span :class="roomTypeBadge(c.room_type)">{{ c.room_type }}</span>
                <AppBadge size="sm" :variant="contractStatusVariant[c.status] ?? 'neutral'">{{ statusLabel(c.status) }}</AppBadge>
              </div>
              <span class="font-bold text-green-600 dark:text-green-300">{{ fmt(c.total_value) }}</span>
            </div>
          </div>
        </div>

        <!-- Visits (وحدة فعلية مخصَّصة + تواريخ + حالة) -->
        <div>
          <div class="flex items-center justify-between mb-2">
            <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase">{{ t('backoffice.timeshare.visitsCount', { count: profileModal.visits.length }) }}</p>
            <!-- زرار جدولة زيارة: manager/timeshare_agent فقط -->
            <AppButton
              v-if="auth.hasRole('timeshare_agent')"
              size="sm" variant="primary"
              @click="openScheduleVisit"
            >📅 {{ t('backoffice.timeshare.scheduleVisit.btnLabel') }}</AppButton>
          </div>
          <EmptyState v-if="!profileModal.visits.length" icon="🏝️" :title="t('backoffice.timeshare.noVisitsRecorded')" />
          <div v-else class="space-y-1.5">
            <div v-for="v in profileModal.visits" :key="v.id" class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 rounded-xl bg-sky-50 dark:bg-sky-950/30 border border-sky-100 dark:border-sky-900/60">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-bold text-gray-900 dark:text-gray-100">🔑 {{ v.unit_id ? (unitNumberById[v.unit_id] ?? t('backoffice.timeshare.unitHash', { id: v.unit_id })) : '—' }}</span>
                <span class="text-gray-500 dark:text-gray-400">{{ formatDateValue(v.check_in) }} → {{ formatDateValue(v.check_out) }}</span>
              </div>
              <div class="flex items-center gap-2 flex-wrap">
                <!-- أزرار تغيير الحالة — manager/timeshare_agent فقط على الحالات المسموحة -->
                <template v-if="(auth.hasRole('timeshare_agent')) && nextStatuses(v.status).length">
                  <AppButton
                    v-for="ns in nextStatuses(v.status)" :key="ns.status"
                    size="sm" variant="ghost"
                    :loading="updatingVisitId === v.id"
                    @click="updateVisitStatus(v, ns.status)"
                  >{{ ns.label }}</AppButton>
                </template>
                <AppButton
                  v-if="auth.hasRole('timeshare_admin') && v.status === 'completed' && !sentSurveyIds.has(v.id)"
                  size="sm" variant="ghost" :loading="sendingSurveyId === v.id"
                  @click="sendSurvey(v)"
                >📨 {{ t('backoffice.timeshare.satisfactionSurvey') }}</AppButton>
                <span v-else-if="sentSurveyIds.has(v.id)" class="text-xs text-green-600 dark:text-green-300 font-bold">✓ {{ t('backoffice.timeshare.sentDone') }}</span>
                <AppBadge size="sm" :variant="visitStatusVariant[v.status] ?? 'neutral'">{{ visitStatusLabel(v.status) }}</AppBadge>
              </div>
            </div>
          </div>
        </div>

        <!-- Installments across all contracts -->
        <div>
          <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-2">{{ t('backoffice.timeshare.installmentsCount', { count: profileAllInstallments.length }) }}</p>
          <EmptyState v-if="!profileAllInstallments.length" icon="💰" :title="t('backoffice.timeshare.noInstallments')" />
          <div v-else class="overflow-x-auto">
          <table class="w-full min-w-[520px] text-xs">
            <thead><tr class="text-gray-500 dark:text-gray-400 border-b border-stone-100 dark:border-border/50">
              <th class="text-start py-2 ps-1">{{ t('backoffice.timeshare.column.contract') }}</th><th class="text-start py-2">{{ t('backoffice.timeshare.column.dueDate') }}</th>
              <th class="text-start py-2">{{ t('backoffice.timeshare.column.amount') }}</th><th class="text-start py-2">{{ t('backoffice.timeshare.column.status') }}</th>
            </tr></thead>
            <tbody class="divide-y divide-stone-100 dark:divide-border">
              <tr v-for="p in profileAllInstallments" :key="p.id">
                <td class="py-2 ps-1 text-gray-500 dark:text-gray-400">{{ p.contract_number }}</td>
                <td class="py-2 text-gray-600 dark:text-gray-300">{{ formatDateValue(p.due_date) }}</td>
                <td class="py-2 font-bold">{{ fmt(p.amount) }}</td>
                <td class="py-2"><AppBadge size="sm" :variant="payStatusVariant[p.status] ?? 'neutral'">{{ payLabel(p.status) }}</AppBadge></td>
              </tr>
            </tbody>
          </table>
          </div>
        </div>

        <!-- Maintenance dues across all contracts -->
        <div>
          <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-2">{{ t('backoffice.timeshare.maintenanceDuesCount', { count: profileAllMaintenanceDues.length }) }}</p>
          <EmptyState v-if="!profileAllMaintenanceDues.length" icon="🛠️" :title="t('backoffice.timeshare.noMaintenanceDues')" />
          <div v-else class="overflow-x-auto">
          <table class="w-full min-w-[520px] text-xs">
            <thead><tr class="text-gray-500 dark:text-gray-400 border-b border-stone-100 dark:border-border/50">
              <th class="text-start py-2 ps-1">{{ t('backoffice.timeshare.column.contract') }}</th><th class="text-start py-2">{{ t('backoffice.timeshare.column.year') }}</th>
              <th class="text-start py-2">{{ t('backoffice.timeshare.column.amount') }}</th><th class="text-start py-2">{{ t('backoffice.timeshare.column.status') }}</th>
            </tr></thead>
            <tbody class="divide-y divide-stone-100 dark:divide-border">
              <tr v-for="d in profileAllMaintenanceDues" :key="d.id">
                <td class="py-2 ps-1 text-gray-500 dark:text-gray-400">{{ d.contract_number }}</td>
                <td class="py-2 text-gray-600 dark:text-gray-300">{{ d.fee_year }}</td>
                <td class="py-2 font-bold">{{ fmt(d.amount) }}</td>
                <td class="py-2"><AppBadge size="sm" :variant="payStatusVariant[d.status] ?? 'neutral'">{{ payLabel(d.status) }}</AppBadge></td>
              </tr>
            </tbody>
          </table>
          </div>
        </div>

        <!-- Reviews (manager فقط — GET /analytics/reviews محتاج صلاحية manager) -->
        <div v-if="auth.hasRole('timeshare_admin')">
          <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-2">{{ t('backoffice.timeshare.reviewsCount', { count: profileModal.reviews.length }) }}</p>
          <EmptyState v-if="!profileModal.reviews.length" icon="⭐" :title="t('backoffice.timeshare.noReviewsRecorded')" />
          <div v-else class="space-y-1.5">
            <div v-for="r in profileModal.reviews" :key="r.id" class="p-3 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-100 dark:border-amber-900/60">
              <div class="flex items-center justify-between mb-1">
                <span class="font-bold text-amber-600 dark:text-amber-300">{{ '⭐'.repeat(r.overall_rating) }}</span>
                <span class="text-gray-500 dark:text-gray-400 text-xs">{{ formatDateValue(r.reviewed_at) }}</span>
              </div>
              <p v-if="r.comment" class="text-gray-700 dark:text-gray-300">{{ r.comment }}</p>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <AppButton variant="ghost" block @click="profileModal.open = false">{{ t('backoffice.timeshare.close') }}</AppButton>
      </template>
    </AppModal>

    <!-- ── Schedule Visit Modal ──────────────────────────────────────────── -->
    <AppModal
      v-model:open="scheduleModal.open"
      :title="t('backoffice.timeshare.scheduleVisit.title')"
      max-width="sm"
    >
      <div class="space-y-4">
        <!-- اختيار العقد — لو العميل عنده أكتر من عقد -->
        <div v-if="profileModal.contracts.length > 1">
          <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
            {{ t('backoffice.timeshare.scheduleVisit.contract') }}
          </label>
          <AppSelect
            v-model="scheduleModal.contractId"
            :options="contractOptions"
            :placeholder="t('backoffice.timeshare.scheduleVisit.selectContract')"
          />
        </div>
        <!-- تاريخ الوصول -->
        <div>
          <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
            {{ t('backoffice.timeshare.scheduleVisit.checkIn') }}
          </label>
          <AppInput v-model="scheduleModal.checkIn" type="date" />
        </div>
        <!-- تاريخ المغادرة -->
        <div>
          <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
            {{ t('backoffice.timeshare.scheduleVisit.checkOut') }}
          </label>
          <AppInput v-model="scheduleModal.checkOut" type="date" :min="scheduleModal.checkIn" />
        </div>
        <!-- ملاحظات (اختياري) -->
        <div>
          <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
            {{ t('backoffice.timeshare.scheduleVisit.notes') }}
          </label>
          <AppInput v-model="scheduleModal.notes" :placeholder="t('backoffice.timeshare.scheduleVisit.notesPlaceholder')" />
        </div>
        <p v-if="scheduleModal.error" class="text-sm text-red-600 dark:text-red-400">{{ scheduleModal.error }}</p>
      </div>
      <template #footer>
        <div class="flex gap-2 justify-end">
          <AppButton variant="ghost" @click="scheduleModal.open = false">{{ t('common.cancel') }}</AppButton>
          <AppButton variant="primary" :loading="scheduleModal.loading" @click="confirmScheduleVisit">
            {{ t('backoffice.timeshare.scheduleVisit.confirm') }}
          </AppButton>
        </div>
      </template>
    </AppModal>
  </div>
</template>
