<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { api, useAuthStore } from '@resort-os/core'
import { AppCard, AppBadge, AppButton, AppModal, useToast, useConfirm } from '@resort-os/ui'

const toast = useToast()
const { confirm } = useConfirm()
const auth = useAuthStore()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

// ── Types ──────────────────────────────────────────────────────────────────
interface Installment {
  id: number; contract_id: number; installment_no: number; due_date: string
  amount: number; paid_amount: number; status: string
  customer_name?: string; customer_phone?: string; room_type?: string
}
interface Contract {
  id: number; contract_number: string; customer_name: string; customer_phone: string | null
  customer_email: string | null; room_type: string; week_number: number | null
  nights_per_year: number; season: string; total_value: number; down_payment: number
  installments: number; status: string; booking_frozen: boolean
  start_date: string; end_date: string | null; notes: string | null
  nationality: string | null; address: string | null; rci_included: boolean
  partner_company: string | null; maintenance_fee: number
  installments_list: Installment[]
  collected?: number; overdue_amount?: number
  unit_id: number | null
}
interface CalendarWeek { week: number; start_date: string; end_date: string; is_current: boolean; is_past: boolean; contracts: any[] }
interface CalendarMonth { month: number; month_name: string; weeks: CalendarWeek[] }
interface TimeshareUnit { id: number; unit_number: string; unit_type: string; status: string }
interface Visit {
  id: number; contract_id: number; unit_id: number | null
  check_in: string; check_out: string; nights: number; status: string
}
interface GuestReview {
  id: number; guest_name: string; overall_rating: number; comment: string | null
  source: string; reviewed_at: string
}

// ── Tabs ───────────────────────────────────────────────────────────────────
const TABS = [
  { id: 'dashboard', icon: '🏠', label: 'لوحة التحكم' },
  { id: 'calendar', icon: '📅', label: 'الكالندر' },
  { id: 'clients', icon: '👤', label: 'العملاء' },
  { id: 'installments', icon: '💰', label: 'الأقساط' },
]
const activeTab = ref('dashboard')
const loading = ref(false)

// ── Dashboard ────────────────────────────────────────────────────────────
const summary = ref<any>({})

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

// ── Customer Profile (ملف عميل مجمّع — كل عقوده/زياراته/أقساطه/تقييماته) ──
// العقود مفيهاش كيان "عميل" منفصل (customer_name/phone/email مباشرة على كل
// صف عقد) — فبنجمّع حسب customer_phone (الأكثر ثباتاً ووجوداً) وإلا
// customer_national_id، وإلا كل عقد بروفايله لوحده (مفيش حاجة تجمعه بحاجة تانية).
function customerKey(c: Contract): string {
  return c.customer_phone?.trim() || (c as any).customer_national_id?.trim() || `contract-${c.id}`
}

const profileModal = reactive({
  open: false, loading: false,
  contracts: [] as Contract[],
  visits: [] as Visit[],
  reviews: [] as GuestReview[],
})

const profileCustomerName = computed(() => profileModal.contracts[0]?.customer_name ?? '')
const profileAllInstallments = computed(() =>
  profileModal.contracts.flatMap(c => (c.installments_list ?? []).map(i => ({ ...i, contract_number: (c as any).contract_number }))),
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
    const r = await api.get('/api/v1/timeshare/units', { params: { branch_id: branchId } })
    units.value = r.data ?? []
  } catch { toast.error('فشل تحميل وحدات التايم شير') }
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
        api.get('/api/v1/timeshare/visits', { params: { branch_id: branchId, contract_id: ct.id } })
          .then(r => r.data as Visit[]).catch(() => [] as Visit[])),
    )
    profileModal.visits = visitLists.flat().sort((a, b) => b.check_in.localeCompare(a.check_in))

    // التقييمات محتاجة صلاحية manager على الباك إند (GET /analytics/reviews) —
    // لو المستخدم أقل من كده (مثلاً supervisor بيشوف شاشة التايم شير) بنتخطى
    // القسم ده بهدوء بدل ما نطلب endpoint هيرجع 403.
    if (auth.hasRole('manager') && profileModal.visits.length) {
      const reviewLists = await Promise.all(
        profileModal.visits.map(v =>
          api.get('/api/v1/analytics/reviews', { params: { branch_id: branchId, timeshare_visit_id: v.id } })
            .then(r => (r.data?.items ?? []) as GuestReview[]).catch(() => [] as GuestReview[])),
      )
      profileModal.reviews = reviewLists.flat()
    }
  } catch (e) { console.error(e); toast.error('فشل تحميل ملف العميل الشامل') }
  finally { profileModal.loading = false }
}

const visitStatusVariant: Record<string, BadgeVariant> = {
  scheduled: 'info', active: 'success', completed: 'neutral', cancelled: 'danger',
}
function visitStatusLabel(s: string) {
  return { scheduled: '📅 مجدولة', active: '🏝️ جارية', completed: '✅ منتهية', cancelled: '❌ ملغاة' }[s] || s
}

// إرسال استبيان الرضا (واتساب) لصاحب زيارة منتهية — الـ endpoint موجود
// (POST /analytics/reviews/survey-token/timeshare/{id}/send) لكن كان بدون
// أي زر في المشروع كله يستدعيه، يعني الاستبيان كان عمليًا غير قابل
// للاستخدام رغم إن الباك إند والفرونت إند (SurveyView.vue) شغالين بالكامل.
const sendingSurveyId = ref<number | null>(null)
const sentSurveyIds = ref<Set<number>>(new Set())

async function sendSurvey(v: Visit) {
  const ok = await confirm({
    message: 'إرسال رابط استبيان رضا لصاحب هذه الزيارة عبر واتساب؟',
    confirmText: 'نعم، أرسل', cancelText: 'تراجع',
  })
  if (!ok) return
  sendingSurveyId.value = v.id
  try {
    await api.post(`/api/v1/analytics/reviews/survey-token/timeshare/${v.id}/send`, null, {
      params: { branch_id: branchId },
    })
    sentSurveyIds.value.add(v.id)
    toast.success('تم إرسال استبيان الرضا')
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر إرسال الاستبيان')
  } finally {
    sendingSurveyId.value = null
  }
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

// ── Import Modal ─────────────────────────────────────────────────────────
const importModal = reactive({ open: false, uploading: false, result: null as any, file: null as File | null })

const fmt = (v: any) => `${(parseFloat(v) || 0).toLocaleString('ar-EG', { maximumFractionDigits: 0 })} ج`
const formatDateAr = (d?: string) => {
  if (!d) return '—'
  try { return new Date(d).toLocaleDateString('ar-EG', { day: 'numeric', month: 'short', year: 'numeric' }) }
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
  try { const r = await api.get('/api/v1/timeshare/cs-summary', { params: { branch_id: branchId } }); summary.value = r.data }
  catch (e) { console.error(e); toast.error('فشل تحميل ملخص التايم شير') }
}

async function loadCalendar() {
  calLoading.value = true
  try {
    const r = await api.get('/api/v1/timeshare/calendar', { params: { branch_id: branchId, year: calYear.value } })
    calendar.value = r.data
  } catch (e) { console.error(e); toast.error('فشل تحميل الكالندر') } finally { calLoading.value = false }
}

// ── Print calendar (لعرض تقديمي في اجتماعات المبيعات) ──────────────────────
// طباعة/تصدير PDF من المتصفح مباشرة — نفس نمط QRGeneratorView.printSelected،
// لأن كالندر 52 أسبوع أصلاً layout مرئي (شبكة)، مش بيانات صفوف تصلح لملف Excel
function escapeHtml(s: string): string {
  const map: Record<string, string> = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }
  return s.replace(/[&<>"']/g, (ch) => map[ch])
}

function calContractPrintClass(c: any): string {
  if (c.rci_included) return 'rci'
  const m: Record<string, string> = { '2R': 'r2', '4R': 'r4', '6R': 'r6' }
  return m[c.room_type] || 'other'
}

function printCalendarView() {
  if (!calendar.value.calendar.length) { toast.error('لا يوجد بيانات كالندر للطباعة'); return }

  const exportedAt = new Date().toLocaleString('ar-EG')
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
                ? week.contracts.map((c: any) => `<span class="tag ${calContractPrintClass(c)}">${escapeHtml((c.customer_name ?? '').split(' ').slice(0, 2).join(' '))}${c.rci_included ? ' ✦' : ''}</span>`).join('')
                : '<span class="empty">—</span>'}
            </span>
          </div>
        `).join('')}
      </div>
    </div>
  `).join('')

  const html = `<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
<meta charset="UTF-8">
<title>كالندر التايم شير ${calYear.value}</title>
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
    <h1>📅 كالندر التايم شير — ${calYear.value}</h1>
    <div class="meta">
      أسابيع محجوزة: ${calendar.value.total_booked_weeks || 0} ·
      صدّره: ${escapeHtml(exportedBy)} · بتاريخ: ${escapeHtml(exportedAt)}
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
  <div class="no-print" style="text-align:center;margin-top:20px;color:#999;font-size:12px;">اضغط Ctrl+P للطباعة أو الحفظ كـ PDF</div>
</body>
</html>`

  const win = window.open('', '_blank')
  if (!win) { toast.error('المتصفح منع فتح نافذة الطباعة — فعّل النوافذ المنبثقة'); return }
  win.document.write(html)
  win.document.close()
  win.focus()
  setTimeout(() => win.print(), 500)
}

async function loadClients() {
  clientsLoading.value = true
  try {
    const r = await api.get('/api/v1/timeshare/contracts', { params: { branch_id: branchId, size: 100 } })
    allClients.value = r.data.items ?? []
  } catch (e) { console.error(e); toast.error('فشل تحميل بيانات العملاء') } finally { clientsLoading.value = false }
}

async function loadInstallments() {
  installLoading.value = true
  try {
    const params: Record<string, any> = { branch_id: branchId, limit: 300 }
    if (installStatus.value) params.status = installStatus.value
    if (installMonth.value) params.month = installMonth.value
    if (installSearch.value) params.search = installSearch.value
    const r = await api.get('/api/v1/timeshare/installments', { params })
    installments.value = r.data.installments ?? []
    installSummary.value = r.data.summary ?? { overdue_total: 0, pending_total: 0 }
  } catch (e) { console.error(e); toast.error('فشل تحميل الأقساط') } finally { installLoading.value = false }
}

async function refreshAll() {
  loading.value = true
  await Promise.all([loadSummary(), loadCalendar(), loadClients(), loadInstallments(), loadUnits()])
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
    toast.success('تم تسجيل الدفعة بنجاح')
    await Promise.all([loadSummary(), loadInstallments(), loadClients()])
  } catch (e: any) { toast.error(e?.response?.data?.detail ?? 'فشل في تسجيل الدفعة') }
  finally { payModal.saving = false }
}

// ── Status / Cancel ──────────────────────────────────────────────────────
const statusSaving = ref<number | null>(null)
async function toggleStatus(c: Contract) {
  const next = c.status === 'active' ? 'suspended' : 'active'
  statusSaving.value = c.id
  try {
    await api.patch(`/api/v1/timeshare/contracts/${c.id}`, { status: next })
    c.status = next
    toast.success(next === 'active' ? 'تم تفعيل العقد' : 'تم تعليق العقد')
    await loadSummary()
  } catch (e: any) { toast.error(e?.response?.data?.detail ?? 'خطأ في تغيير الحالة') }
  finally { statusSaving.value = null }
}

async function cancelContract(c: Contract) {
  const ok = await confirm({
    message: `إلغاء عقد ${c.customer_name}؟ لا يمكن التراجع عن هذا الإجراء.`,
    danger: true, confirmText: 'نعم، ألغِ', cancelText: 'تراجع',
  })
  if (!ok) return
  try {
    await api.post(`/api/v1/timeshare/contracts/${c.id}/cancel`, { cancel_amount: 0 })
    c.status = 'cancelled'
    toast.success('تم إلغاء العقد')
    await loadSummary()
  } catch (e: any) { toast.error(e?.response?.data?.detail ?? 'خطأ في الإلغاء') }
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
  return units.value.filter(u => u.unit_type === transferModal.contract!.room_type && u.id !== transferModal.contract!.unit_id)
})

async function saveTransfer() {
  if (!transferModal.contract) return
  if (!transferModal.new_unit_id) { toast.error('اختر الوحدة الجديدة'); return }
  if (!transferModal.reason.trim() || transferModal.reason.trim().length < 3) {
    toast.error('سبب النقل مطلوب (3 أحرف على الأقل)'); return
  }
  transferModal.saving = true
  try {
    const { data } = await api.post(`/api/v1/timeshare/contracts/${transferModal.contract.id}/transfer-unit`, {
      new_unit_id: transferModal.new_unit_id, reason: transferModal.reason,
    })
    transferModal.contract.unit_id = data.unit_id
    toast.success('تم نقل الوحدة')
    transferModal.open = false
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر نقل الوحدة')
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
      headers: { 'Content-Type': 'multipart/form-data' }, params: { branch_id: branchId },
    })
    importModal.result = r.data
    await Promise.all([loadClients(), loadSummary()])
  } catch (e: any) {
    const msg = e?.response?.data?.detail ?? 'فشل الاستيراد'
    importModal.result = { error: msg }
    toast.error(msg)
  } finally { importModal.uploading = false }
}

// ── Badges ───────────────────────────────────────────────────────────────
type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'

function roomTypeBadge(type: string) {
  const m: Record<string, string> = {
    '2R': 'bg-sky-100 text-sky-700', '4R': 'bg-amber-100 text-amber-700', '6R': 'bg-emerald-100 text-emerald-700',
  }
  return `text-[10px] px-1.5 py-0.5 rounded-full font-bold ${m[type] || 'bg-stone-100 text-stone-500'}`
}
const contractStatusVariant: Record<string, BadgeVariant> = {
  active: 'success', suspended: 'warning', cancelled: 'danger', expired: 'neutral',
}
function statusLabel(s: string) {
  return { active: '✅ نشط', suspended: '⏸️ موقوف', cancelled: '❌ ملغي', expired: '⌛ منتهي' }[s] || s
}
const payStatusVariant: Record<string, BadgeVariant> = {
  paid: 'success', pending: 'warning', overdue: 'danger', partial: 'info',
}
function payLabel(s: string) {
  return { paid: '✅ مدفوع', pending: '⏳ معلق', overdue: '🔴 متأخر', partial: '🔵 جزئي' }[s] || s
}
function calContractClass(c: any) {
  if (c.rci_included) return 'bg-purple-100 text-purple-700 border-purple-200'
  const m: Record<string, string> = {
    '2R': 'bg-sky-100 text-sky-700 border-sky-200', '4R': 'bg-amber-100 text-amber-700 border-amber-200',
    '6R': 'bg-emerald-100 text-emerald-700 border-emerald-200',
  }
  return m[c.room_type] || 'bg-stone-100 text-stone-500 border-stone-200'
}

onMounted(refreshAll)
</script>

<template>
  <div dir="rtl">
    <div class="flex items-center justify-between flex-wrap gap-3 mb-4">
      <h2 class="text-2xl font-black text-gray-900">🏨 التايم شير</h2>
      <div class="flex items-center gap-2">
        <button v-if="auth.hasRole('manager')" @click="importModal.open = true; importModal.result = null"
          class="px-3 py-1.5 rounded-xl bg-white border border-stone-200 text-gray-600 text-xs font-bold hover:bg-stone-50 transition-all">
          📥 استيراد Excel
        </button>
        <button @click="refreshAll" :disabled="loading"
          class="px-3 py-1.5 rounded-xl bg-white border border-stone-200 text-gray-600 text-xs font-bold hover:bg-stone-50 transition-all">
          {{ loading ? '⏳' : '🔄' }} تحديث
        </button>
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex gap-1 bg-stone-100 p-1 rounded-xl mb-6 w-fit">
      <button v-for="t in TABS" :key="t.id" @click="activeTab = t.id"
        :class="['px-4 py-2 rounded-lg text-sm font-semibold transition-all', activeTab === t.id ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-700']">
        {{ t.icon }} {{ t.label }}
      </button>
    </div>

    <!-- ══ DASHBOARD ══ -->
    <div v-if="activeTab === 'dashboard'" class="space-y-5">
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <AppCard padding="md">
          <p class="text-[10px] text-gray-400 font-bold uppercase tracking-wide mb-2">عقود نشطة</p>
          <p class="text-2xl font-black text-gray-900">{{ summary.active_contracts || 0 }}</p>
        </AppCard>
        <AppCard padding="md">
          <p class="text-[10px] text-gray-400 font-bold uppercase tracking-wide mb-2">نسبة التحصيل</p>
          <p :class="['text-2xl font-black', (summary.collection_rate_pct||0) >= 50 ? 'text-green-600' : 'text-amber-500']">
            {{ summary.collection_rate_pct || 0 }}%
          </p>
          <p class="text-[10px] text-gray-400 mt-1">{{ fmt(summary.total_collected) }} من {{ fmt(summary.total_value) }}</p>
        </AppCard>
        <AppCard padding="md">
          <p class="text-[10px] text-gray-400 font-bold uppercase tracking-wide mb-2">متأخرات</p>
          <p class="text-2xl font-black text-red-500">{{ fmt(summary.total_overdue) }}</p>
          <p class="text-[10px] text-gray-400 mt-1">{{ summary.overdue_contracts_count || 0 }} عقد متأخر</p>
        </AppCard>
        <AppCard padding="md">
          <p class="text-[10px] text-gray-400 font-bold uppercase tracking-wide mb-2">مستحق هذا الشهر</p>
          <p class="text-2xl font-black text-amber-500">{{ fmt(summary.this_month_due) }}</p>
        </AppCard>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <AppCard padding="md">
          <div class="flex items-center justify-between mb-4">
            <p class="font-black text-sm text-gray-900">📅 زيارات قادمة — خلال 30 يوم</p>
            <span class="text-[10px] px-2 py-0.5 rounded-full bg-sky-100 text-sky-700 font-bold">{{ summary.upcoming_visits?.length || 0 }}</span>
          </div>
          <div v-if="!summary.upcoming_visits?.length" class="text-center py-6 text-gray-300 text-xs">لا توجد زيارات قادمة</div>
          <div v-else class="space-y-2">
            <div v-for="v in summary.upcoming_visits" :key="v.id" class="flex items-center justify-between gap-3 p-3 rounded-xl bg-stone-50 border border-stone-100">
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-1 flex-wrap">
                  <span class="font-bold text-xs text-gray-900">{{ v.customer_name }}</span>
                  <span :class="roomTypeBadge(v.room_type)">{{ v.room_type }}</span>
                </div>
                <div class="text-[10px] text-gray-400">أسبوع {{ v.week_number }} · {{ formatDateAr(v.visit_start) }}</div>
              </div>
              <div class="text-left flex-shrink-0">
                <div :class="['text-sm font-black', v.days_until === 0 ? 'text-red-500' : v.days_until <= 7 ? 'text-amber-500' : 'text-green-600']">
                  {{ v.days_until === 0 ? 'اليوم!' : v.days_until === 1 ? 'غداً' : `${v.days_until} يوم` }}
                </div>
                <div v-if="v.customer_phone" class="text-[10px] text-gray-400 mt-0.5">{{ v.customer_phone }}</div>
              </div>
            </div>
          </div>
        </AppCard>

        <AppCard padding="md">
          <div class="flex items-center justify-between mb-4">
            <p class="font-black text-sm text-gray-900">🔴 عملاء متأخرون</p>
            <span class="text-[10px] px-2 py-0.5 rounded-full bg-red-100 text-red-700 font-bold">{{ summary.overdue_clients?.length || 0 }}</span>
          </div>
          <div v-if="!summary.overdue_clients?.length" class="text-center py-6 text-gray-300 text-xs">🎉 لا توجد متأخرات</div>
          <div v-else class="space-y-2">
            <div v-for="c in summary.overdue_clients" :key="c.id" class="flex items-center justify-between gap-3 p-3 rounded-xl bg-red-50 border border-red-100">
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2 mb-1 flex-wrap">
                  <span class="font-bold text-xs text-gray-900">{{ c.customer_name }}</span>
                  <span :class="roomTypeBadge(c.room_type)">{{ c.room_type }}</span>
                </div>
                <div class="text-[10px] text-gray-400">{{ c.pending_count }} قسط معلق<span v-if="c.next_due"> · استحق {{ formatDateAr(c.next_due) }}</span></div>
              </div>
              <div class="text-left flex-shrink-0">
                <div class="text-sm font-black text-red-500">{{ fmt(c.overdue_amount) }}</div>
                <a v-if="c.customer_phone" :href="`tel:${c.customer_phone}`" class="text-[10px] text-gray-400 hover:text-amber-500">📞 {{ c.customer_phone }}</a>
              </div>
            </div>
          </div>
        </AppCard>
      </div>
    </div>

    <!-- ══ CALENDAR ══ -->
    <div v-if="activeTab === 'calendar'" class="space-y-4">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <button @click="calYear--; loadCalendar()" class="w-8 h-8 rounded-xl bg-white border border-stone-200 text-gray-500 hover:bg-stone-50 text-sm font-bold">›</button>
          <h3 class="text-lg font-black text-gray-900">{{ calYear }}</h3>
          <button @click="calYear++; loadCalendar()" class="w-8 h-8 rounded-xl bg-white border border-stone-200 text-gray-500 hover:bg-stone-50 text-sm font-bold">‹</button>
        </div>
        <div class="flex items-center gap-3">
          <span class="text-xs text-gray-400">أسابيع محجوزة: <span class="text-amber-500 font-bold">{{ calendar.total_booked_weeks || 0 }}</span></span>
          <button @click="printCalendarView"
            class="px-2.5 py-1.5 rounded-xl bg-primary-50 text-primary-700 text-[10px] font-bold border border-primary-200 hover:bg-primary-100"
            title="طباعة الكالندر أو حفظه كـ PDF لعرضه في اجتماع مبيعات">
            🖨️ طباعة / PDF
          </button>
        </div>
      </div>

      <div v-if="calLoading" class="flex justify-center py-12">
        <div class="w-6 h-6 border-2 border-primary-700 border-t-transparent rounded-full animate-spin"/>
      </div>
      <div v-else class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        <div v-for="month in calendar.calendar" :key="month.month" class="bg-white rounded-2xl border border-stone-200 overflow-hidden shadow-sm">
          <div class="px-4 py-2.5 border-b border-stone-100 bg-stone-50">
            <p class="font-bold text-xs text-gray-700">{{ month.month_name }} {{ calYear }}</p>
          </div>
          <div class="divide-y divide-stone-100">
            <div v-for="week in month.weeks" :key="week.week"
              :class="['flex items-center gap-2 px-3 py-2', week.is_current ? 'bg-amber-50 border-r-2 border-amber-400' : '', week.is_past && !week.is_current ? 'opacity-40' : '']">
              <div class="flex-shrink-0 w-8 text-center">
                <span :class="['text-[10px] font-bold rounded-full px-1.5 py-0.5', week.is_current ? 'bg-amber-400 text-white' : 'text-gray-300']">{{ week.week }}</span>
              </div>
              <div class="flex-shrink-0 text-[9px] text-gray-300 w-20">{{ week.start_date?.slice(5) }} →</div>
              <div class="flex-1 flex flex-wrap gap-1">
                <span v-if="!week.contracts.length" class="text-[9px] text-gray-200">—</span>
                <span v-for="c in week.contracts" :key="c.id" :class="['text-[9px] px-2 py-0.5 rounded-lg font-bold border', calContractClass(c)]">
                  {{ c.customer_name.split(' ').slice(0, 2).join(' ') }}
                  <span v-if="c.rci_included" class="mr-1">✦</span>
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
        <input v-model="clientSearch" placeholder="🔍 ابحث بالاسم أو الهاتف أو رقم العقد..."
          class="flex-1 min-w-48 bg-white border border-stone-200 text-gray-900 text-xs rounded-xl px-4 py-2.5 outline-none focus:border-primary-500" />
        <select v-model="clientStatusFilter" class="bg-white border border-stone-200 text-gray-600 text-xs rounded-xl px-3 py-2.5 outline-none">
          <option value="">كل الحالات</option>
          <option value="active">نشط</option>
          <option value="suspended">موقوف</option>
          <option value="cancelled">ملغي</option>
        </select>
        <select v-model="clientRoomFilter" class="bg-white border border-stone-200 text-gray-600 text-xs rounded-xl px-3 py-2.5 outline-none">
          <option value="">كل الأنواع</option>
          <option value="2R">2R</option><option value="4R">4R</option><option value="6R">6R</option>
        </select>
      </div>

      <div v-if="clientsLoading" class="flex justify-center py-12">
        <div class="w-6 h-6 border-2 border-primary-700 border-t-transparent rounded-full animate-spin"/>
      </div>
      <div v-else class="space-y-2">
        <div v-if="!filteredClients.length" class="text-center py-10 text-gray-300 text-xs">لا توجد نتائج</div>
        <div v-for="c in filteredClients" :key="c.id"
          class="bg-white rounded-2xl border overflow-hidden transition-all shadow-sm"
          :class="expandedClient === c.id ? 'border-primary-300' : 'border-stone-200 hover:border-stone-300'">

          <div class="p-4 cursor-pointer flex items-center gap-4" @click="expandedClient = expandedClient === c.id ? null : c.id">
            <div class="w-9 h-9 rounded-xl flex-shrink-0 flex items-center justify-center text-sm font-black" :class="roomTypeBadge(c.room_type)">
              {{ c.customer_name?.charAt(0) || '?' }}
            </div>
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-bold text-sm text-gray-900">{{ c.customer_name }}</span>
                <span :class="roomTypeBadge(c.room_type)">{{ c.room_type }}</span>
                <span v-if="c.rci_included" class="text-[9px] px-1.5 py-0.5 rounded-full bg-purple-100 text-purple-700 font-bold">RCI</span>
                <AppBadge size="sm" :variant="contractStatusVariant[c.status] ?? 'neutral'">{{ statusLabel(c.status) }}</AppBadge>
              </div>
              <div class="text-[10px] text-gray-400 mt-0.5 flex flex-wrap gap-3">
                <span v-if="c.customer_phone">📞 {{ c.customer_phone }}</span>
                <span>أسبوع {{ c.week_number || '—' }}</span>
                <span>{{ c.contract_number }}</span>
              </div>
            </div>
            <div class="text-left flex-shrink-0 hidden sm:block">
              <div class="text-green-600 font-black text-sm">{{ fmt(c.total_value) }}</div>
            </div>
            <button @click.stop="openProfile(c)"
              class="flex-shrink-0 px-2.5 py-1.5 rounded-xl bg-primary-50 text-primary-700 text-[10px] font-bold border border-primary-200 hover:bg-primary-100">
              👤 الملف الشامل
            </button>
            <div class="text-gray-300 text-xs flex-shrink-0">{{ expandedClient === c.id ? '▲' : '▼' }}</div>
          </div>

          <div v-if="expandedClient === c.id" class="border-t border-stone-100 p-4 space-y-4">
            <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 text-[11px]">
              <div class="space-y-1.5">
                <p class="text-[10px] text-gray-400 font-bold uppercase mb-1">بيانات العقد</p>
                <div class="flex justify-between"><span class="text-gray-400">مدة العقد</span><span>{{ c.start_date }} — {{ c.end_date || '—' }}</span></div>
                <div class="flex justify-between"><span class="text-gray-400">ليالٍ/سنة</span><span class="font-bold text-amber-600">{{ c.nights_per_year }}</span></div>
                <div v-if="c.nationality" class="flex justify-between"><span class="text-gray-400">الجنسية</span><span>{{ c.nationality }}</span></div>
                <div v-if="c.maintenance_fee > 0" class="flex justify-between"><span class="text-gray-400">صيانة سنوية</span><span class="text-amber-600">{{ fmt(c.maintenance_fee) }}</span></div>
              </div>
              <div class="space-y-1.5">
                <p class="text-[10px] text-gray-400 font-bold uppercase mb-1">الوضع المالي</p>
                <div class="flex justify-between"><span class="text-gray-400">قيمة العقد</span><span class="font-bold text-green-600">{{ fmt(c.total_value) }}</span></div>
                <div class="flex justify-between"><span class="text-gray-400">دفعة أولى</span><span>{{ fmt(c.down_payment) }}</span></div>
                <div class="flex justify-between"><span class="text-gray-400">عدد الأقساط</span><span>{{ c.installments }}</span></div>
              </div>
            </div>

            <div>
              <p class="text-[10px] text-gray-400 font-bold uppercase mb-2">جدول الأقساط</p>
              <div v-if="c.installments_list?.length" class="overflow-x-auto">
                <table class="w-full text-[10px]">
                  <thead><tr class="text-gray-400 border-b border-stone-100">
                    <th class="text-right py-1.5 pr-1">#</th><th class="text-right py-1.5">الاستحقاق</th>
                    <th class="text-right py-1.5">المبلغ</th><th class="text-right py-1.5">الحالة</th><th></th>
                  </tr></thead>
                  <tbody class="divide-y divide-stone-100">
                    <tr v-for="(p, i) in c.installments_list" :key="p.id">
                      <td class="py-1.5 pr-1 text-gray-300">{{ i + 1 }}</td>
                      <td class="py-1.5 text-gray-500">{{ formatDateAr(p.due_date) }}</td>
                      <td class="py-1.5 font-bold">{{ fmt(p.amount) }}</td>
                      <td class="py-1.5"><AppBadge size="sm" :variant="payStatusVariant[p.status] ?? 'neutral'">{{ payLabel(p.status) }}</AppBadge></td>
                      <td class="py-1.5">
                        <button v-if="p.status !== 'paid'" @click="openPayModal({ ...p, customer_name: c.customer_name })"
                          class="px-2 py-0.5 rounded-lg bg-green-50 text-green-700 text-[9px] font-bold border border-green-200 hover:bg-green-100">دفع</button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div class="flex flex-wrap gap-2 pt-2 border-t border-stone-100">
              <button @click="openPayModalForContract(c)" class="px-4 py-2 rounded-xl bg-green-50 text-green-700 text-xs font-bold border border-green-200 hover:bg-green-100">💰 تسجيل دفعة</button>
              <a v-if="c.customer_phone" :href="`tel:${c.customer_phone}`" class="px-4 py-2 rounded-xl bg-sky-50 text-sky-700 text-xs font-bold border border-sky-200 hover:bg-sky-100">📞 اتصال</a>
              <button v-if="auth.hasRole('manager') && c.status === 'active'" @click="toggleStatus(c)" :disabled="statusSaving === c.id"
                class="px-4 py-2 rounded-xl bg-yellow-50 text-yellow-700 text-xs font-bold border border-yellow-200 hover:bg-yellow-100 disabled:opacity-40">⏸️ تعليق</button>
              <button v-else-if="auth.hasRole('manager') && c.status === 'suspended'" @click="toggleStatus(c)" :disabled="statusSaving === c.id"
                class="px-4 py-2 rounded-xl bg-green-50 text-green-700 text-xs font-bold border border-green-200 hover:bg-green-100 disabled:opacity-40">▶️ تفعيل</button>
              <button v-if="auth.hasRole('manager') && c.unit_id && !['cancelled','expired'].includes(c.status)" @click="openTransferModal(c)"
                class="px-4 py-2 rounded-xl bg-violet-50 text-violet-700 text-xs font-bold border border-violet-200 hover:bg-violet-100">🔑 نقل الوحدة</button>
              <AppButton v-if="auth.hasRole('manager') && c.status !== 'cancelled'" variant="danger" size="sm" @click="cancelContract(c)">🗑️ إلغاء</AppButton>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- ══ INSTALLMENTS ══ -->
    <div v-if="activeTab === 'installments'" class="space-y-4">
      <div class="flex flex-wrap gap-3">
        <div class="px-4 py-2 rounded-xl bg-red-50 border border-red-200 text-xs font-bold text-red-600">🔴 متأخرات: {{ fmt(installSummary.overdue_total) }}</div>
        <div class="px-4 py-2 rounded-xl bg-amber-50 border border-amber-200 text-xs font-bold text-amber-600">⏳ معلق: {{ fmt(installSummary.pending_total) }}</div>
      </div>
      <div class="flex flex-wrap gap-3">
        <input v-model="installSearch" @keyup.enter="loadInstallments" placeholder="🔍 ابحث باسم العميل..."
          class="flex-1 min-w-40 bg-white border border-stone-200 text-gray-900 text-xs rounded-xl px-4 py-2 outline-none" />
        <select v-model="installStatus" @change="loadInstallments" class="bg-white border border-stone-200 text-gray-600 text-xs rounded-xl px-3 py-2">
          <option value="">كل الحالات</option><option value="overdue">🔴 متأخر</option>
          <option value="pending">⏳ معلق</option><option value="paid">✅ مدفوع</option><option value="partial">🔵 جزئي</option>
        </select>
        <input v-model="installMonth" @change="loadInstallments" type="month" class="bg-white border border-stone-200 text-gray-600 text-xs rounded-xl px-3 py-2" />
      </div>

      <div v-if="installLoading" class="flex justify-center py-12">
        <div class="w-6 h-6 border-2 border-primary-700 border-t-transparent rounded-full animate-spin"/>
      </div>
      <AppCard v-else padding="none">
        <div v-if="!installments.length" class="text-center py-10 text-gray-300 text-xs">لا توجد نتائج</div>
        <table v-else class="w-full text-xs">
          <thead class="bg-stone-50"><tr>
            <th class="text-right px-4 py-3 text-gray-400 font-bold">العميل</th>
            <th class="text-right px-4 py-3 text-gray-400 font-bold">الاستحقاق</th>
            <th class="text-right px-4 py-3 text-gray-400 font-bold">المبلغ</th>
            <th class="text-right px-4 py-3 text-gray-400 font-bold">الحالة</th>
            <th class="px-4 py-3"></th>
          </tr></thead>
          <tbody class="divide-y divide-stone-100">
            <tr v-for="p in installments" :key="p.id" :class="p.status === 'overdue' ? 'bg-red-50/30' : ''">
              <td class="px-4 py-3">
                <div class="font-bold text-gray-900">{{ p.customer_name }}</div>
                <div class="text-[10px] text-gray-400">{{ p.customer_phone }}</div>
              </td>
              <td class="px-4 py-3"><span :class="p.status === 'overdue' ? 'text-red-500 font-bold' : 'text-gray-500'">{{ formatDateAr(p.due_date) }}</span></td>
              <td class="px-4 py-3 font-bold">{{ fmt(p.amount) }}</td>
              <td class="px-4 py-3"><AppBadge size="sm" :variant="payStatusVariant[p.status] ?? 'neutral'">{{ payLabel(p.status) }}</AppBadge></td>
              <td class="px-4 py-3">
                <button v-if="p.status !== 'paid'" @click="openPayModal(p)"
                  class="px-3 py-1 rounded-xl bg-green-50 text-green-700 text-[10px] font-bold border border-green-200 hover:bg-green-100">💰 دفع</button>
              </td>
            </tr>
          </tbody>
        </table>
      </AppCard>
    </div>

    <!-- ══ TRANSFER UNIT MODAL (#10) ══ -->
    <AppModal :open="transferModal.open" title="🔑 نقل الوحدة" size="sm" @close="transferModal.open = false">
      <div v-if="transferModal.contract" class="space-y-3">
        <p class="text-xs text-gray-500">
          {{ transferModal.contract.customer_name }} — الوحدة الحالية:
          <span class="font-bold">{{ transferModal.contract.unit_id ? (unitNumberById[transferModal.contract.unit_id] ?? `#${transferModal.contract.unit_id}`) : '—' }}</span>
        </p>
        <select v-model="transferModal.new_unit_id" class="w-full border border-stone-200 rounded-xl px-3 py-2 text-sm">
          <option value="">اختر الوحدة الجديدة (نفس نوع {{ transferModal.contract.room_type }}) *</option>
          <option v-for="u in transferCandidateUnits" :key="u.id" :value="u.id" :disabled="u.status === 'maintenance'">
            {{ u.unit_number }}{{ u.status === 'maintenance' ? ' (تحت الصيانة)' : '' }}
          </option>
        </select>
        <p v-if="transferCandidateUnits.length === 0" class="text-xs text-amber-600">لا توجد وحدات أخرى متاحة من نفس النوع حاليًا</p>
        <input v-model="transferModal.reason" type="text" placeholder="سبب النقل (مطلوب) *"
          class="w-full border border-stone-200 rounded-xl px-3 py-2 text-sm" />
        <AppButton class="w-full" :loading="transferModal.saving" @click="saveTransfer">تأكيد النقل</AppButton>
      </div>
    </AppModal>

    <!-- ══ PAY MODAL ══ -->
    <AppModal :open="payModal.open" title="💰 تسجيل دفعة" size="sm" @close="payModal.open = false">
      <p class="text-xs text-gray-400 mb-4">{{ payModal.customer_name }}</p>
      <div class="space-y-3">
        <div>
          <label class="text-[10px] text-gray-400 block mb-1">المبلغ المدفوع</label>
          <input v-model.number="payModal.amount" type="number" min="1" :placeholder="`المستحق: ${fmt(payModal.due_amount)}`"
            class="w-full bg-stone-50 border border-stone-200 text-gray-900 text-sm rounded-xl px-4 py-2.5 outline-none focus:border-primary-500" />
        </div>
        <div>
          <label class="text-[10px] text-gray-400 block mb-1">طريقة الدفع</label>
          <select v-model="payModal.method" class="w-full bg-stone-50 border border-stone-200 text-gray-900 text-xs rounded-xl px-4 py-2.5 outline-none">
            <option value="cash">نقدي</option><option value="card">بطاقة</option>
            <option value="bank_transfer">تحويل بنكي</option><option value="other">أخرى</option>
          </select>
        </div>
        <div>
          <label class="text-[10px] text-gray-400 block mb-1">رقم الإيصال (اختياري)</label>
          <input v-model="payModal.receipt_number" class="w-full bg-stone-50 border border-stone-200 text-gray-900 text-xs rounded-xl px-4 py-2.5 outline-none" />
        </div>
      </div>
      <template #footer>
        <div class="flex gap-3">
          <AppButton variant="primary" block :loading="payModal.saving" :disabled="!payModal.amount" @click="submitPayment">
            ✅ تأكيد الدفع
          </AppButton>
          <AppButton variant="ghost" @click="payModal.open = false">إلغاء</AppButton>
        </div>
      </template>
    </AppModal>

    <!-- ══ IMPORT MODAL ══ -->
    <AppModal v-if="auth.hasRole('manager')" :open="importModal.open" title="📥 استيراد عقود من Excel" @close="importModal.open = false">
      <p class="text-xs text-gray-400 mb-4">
        الصف الأول = أسماء الأعمدة (customer_name, room_type, total_value, down_payment, installments, start_date, first_installment_date إلزامية).
      </p>
      <input type="file" accept=".xlsx,.xls" @change="onFilePicked"
        class="w-full text-xs text-gray-600 file:ml-3 file:py-2 file:px-4 file:rounded-xl file:border-0 file:bg-primary-50 file:text-primary-700 file:font-bold" />
      <div v-if="importModal.result" class="mt-4 p-3 rounded-xl text-xs" :class="importModal.result.error ? 'bg-red-50 text-red-600' : 'bg-green-50 text-green-700'">
        <div v-if="importModal.result.error">{{ importModal.result.error }}</div>
        <div v-else>
          ✅ تم استيراد {{ importModal.result.imported }} عقد
          <span v-if="importModal.result.skipped"> · تخطي {{ importModal.result.skipped }} (مستورد سابقاً)</span>
          <div v-if="importModal.result.errors?.length" class="mt-2 text-red-500">
            <div v-for="(err, i) in importModal.result.errors" :key="i">{{ err }}</div>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="flex gap-3">
          <AppButton variant="primary" block :loading="importModal.uploading" :disabled="!importModal.file" @click="submitImport">
            📤 استيراد
          </AppButton>
          <AppButton variant="ghost" @click="importModal.open = false">إغلاق</AppButton>
        </div>
      </template>
    </AppModal>

    <!-- ══ CUSTOMER PROFILE (أجمّع كل عقود/زيارات/أقساط/تقييمات نفس العميل) ══ -->
    <AppModal :open="profileModal.open" :title="`👤 ملف العميل الشامل — ${profileCustomerName}`" size="lg" @close="profileModal.open = false">
      <div v-if="profileModal.loading" class="flex justify-center py-12">
        <div class="w-6 h-6 border-2 border-primary-700 border-t-transparent rounded-full animate-spin"/>
      </div>
      <div v-else class="space-y-5 text-xs">
        <!-- Totals -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div class="bg-stone-50 rounded-xl p-3">
            <p class="text-[9px] text-gray-400 font-bold uppercase mb-1">عدد العقود</p>
            <p class="font-black text-gray-900">{{ profileModal.contracts.length }}</p>
          </div>
          <div class="bg-green-50 rounded-xl p-3">
            <p class="text-[9px] text-gray-400 font-bold uppercase mb-1">محصّل</p>
            <p class="font-black text-green-600">{{ fmt(profileTotals.collected) }}</p>
          </div>
          <div class="bg-red-50 rounded-xl p-3">
            <p class="text-[9px] text-gray-400 font-bold uppercase mb-1">متأخر</p>
            <p class="font-black text-red-500">{{ fmt(profileTotals.overdue) }}</p>
          </div>
          <div class="bg-amber-50 rounded-xl p-3">
            <p class="text-[9px] text-gray-400 font-bold uppercase mb-1">معلّق</p>
            <p class="font-black text-amber-600">{{ fmt(profileTotals.pending) }}</p>
          </div>
        </div>

        <!-- Contracts -->
        <div>
          <p class="text-[10px] text-gray-400 font-bold uppercase mb-2">العقود ({{ profileModal.contracts.length }})</p>
          <div class="space-y-1.5">
            <div v-for="c in profileModal.contracts" :key="c.id" class="flex items-center justify-between gap-2 p-2.5 rounded-xl bg-stone-50 border border-stone-100">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-bold text-gray-900">{{ c.contract_number }}</span>
                <span :class="roomTypeBadge(c.room_type)">{{ c.room_type }}</span>
                <AppBadge size="sm" :variant="contractStatusVariant[c.status] ?? 'neutral'">{{ statusLabel(c.status) }}</AppBadge>
              </div>
              <span class="font-bold text-green-600">{{ fmt(c.total_value) }}</span>
            </div>
          </div>
        </div>

        <!-- Visits (وحدة فعلية مخصَّصة + تواريخ + حالة) -->
        <div>
          <p class="text-[10px] text-gray-400 font-bold uppercase mb-2">الزيارات ({{ profileModal.visits.length }})</p>
          <div v-if="!profileModal.visits.length" class="text-center py-4 text-gray-300">لا توجد زيارات مسجّلة</div>
          <div v-else class="space-y-1.5">
            <div v-for="v in profileModal.visits" :key="v.id" class="flex items-center justify-between gap-2 p-2.5 rounded-xl bg-sky-50 border border-sky-100">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-bold text-gray-900">🔑 {{ v.unit_id ? (unitNumberById[v.unit_id] ?? `وحدة #${v.unit_id}`) : '—' }}</span>
                <span class="text-gray-400">{{ formatDateAr(v.check_in) }} → {{ formatDateAr(v.check_out) }}</span>
              </div>
              <div class="flex items-center gap-2">
                <AppButton
                  v-if="auth.hasRole('manager') && v.status === 'completed' && !sentSurveyIds.has(v.id)"
                  size="sm" variant="ghost" :loading="sendingSurveyId === v.id"
                  @click="sendSurvey(v)"
                >📨 استبيان الرضا</AppButton>
                <span v-else-if="sentSurveyIds.has(v.id)" class="text-[10px] text-green-600 font-bold">✓ تم الإرسال</span>
                <AppBadge size="sm" :variant="visitStatusVariant[v.status] ?? 'neutral'">{{ visitStatusLabel(v.status) }}</AppBadge>
              </div>
            </div>
          </div>
        </div>

        <!-- Installments across all contracts -->
        <div>
          <p class="text-[10px] text-gray-400 font-bold uppercase mb-2">الأقساط ({{ profileAllInstallments.length }})</p>
          <div v-if="!profileAllInstallments.length" class="text-center py-4 text-gray-300">لا توجد أقساط</div>
          <table v-else class="w-full text-[10px]">
            <thead><tr class="text-gray-400 border-b border-stone-100">
              <th class="text-right py-1.5 pr-1">العقد</th><th class="text-right py-1.5">الاستحقاق</th>
              <th class="text-right py-1.5">المبلغ</th><th class="text-right py-1.5">الحالة</th>
            </tr></thead>
            <tbody class="divide-y divide-stone-100">
              <tr v-for="p in profileAllInstallments" :key="p.id">
                <td class="py-1.5 pr-1 text-gray-400">{{ p.contract_number }}</td>
                <td class="py-1.5 text-gray-500">{{ formatDateAr(p.due_date) }}</td>
                <td class="py-1.5 font-bold">{{ fmt(p.amount) }}</td>
                <td class="py-1.5"><AppBadge size="sm" :variant="payStatusVariant[p.status] ?? 'neutral'">{{ payLabel(p.status) }}</AppBadge></td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- Reviews (manager فقط — GET /analytics/reviews محتاج صلاحية manager) -->
        <div v-if="auth.hasRole('manager')">
          <p class="text-[10px] text-gray-400 font-bold uppercase mb-2">التقييمات ({{ profileModal.reviews.length }})</p>
          <div v-if="!profileModal.reviews.length" class="text-center py-4 text-gray-300">لا توجد تقييمات مسجّلة</div>
          <div v-else class="space-y-1.5">
            <div v-for="r in profileModal.reviews" :key="r.id" class="p-2.5 rounded-xl bg-amber-50 border border-amber-100">
              <div class="flex items-center justify-between mb-1">
                <span class="font-bold text-amber-600">{{ '⭐'.repeat(r.overall_rating) }}</span>
                <span class="text-gray-400 text-[9px]">{{ formatDateAr(r.reviewed_at) }}</span>
              </div>
              <p v-if="r.comment" class="text-gray-600">{{ r.comment }}</p>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <AppButton variant="ghost" block @click="profileModal.open = false">إغلاق</AppButton>
      </template>
    </AppModal>
  </div>
</template>
