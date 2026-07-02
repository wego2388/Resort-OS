<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import axios from 'axios'

const h = { Authorization: `Bearer ${localStorage.getItem('access_token')}` }
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
}
interface CalendarWeek { week: number; start_date: string; end_date: string; is_current: boolean; is_past: boolean; contracts: any[] }
interface CalendarMonth { month: number; month_name: string; weeks: CalendarWeek[] }

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
  try { const r = await axios.get('/api/v1/timeshare/cs-summary', { headers: h, params: { branch_id: branchId } }); summary.value = r.data }
  catch (e) { console.error(e) }
}

async function loadCalendar() {
  calLoading.value = true
  try {
    const r = await axios.get('/api/v1/timeshare/calendar', { headers: h, params: { branch_id: branchId, year: calYear.value } })
    calendar.value = r.data
  } catch (e) { console.error(e) } finally { calLoading.value = false }
}

async function loadClients() {
  clientsLoading.value = true
  try {
    const r = await axios.get('/api/v1/timeshare/contracts', { headers: h, params: { branch_id: branchId, size: 100 } })
    allClients.value = r.data.items ?? []
  } catch (e) { console.error(e) } finally { clientsLoading.value = false }
}

async function loadInstallments() {
  installLoading.value = true
  try {
    const params: Record<string, any> = { branch_id: branchId, limit: 300 }
    if (installStatus.value) params.status = installStatus.value
    if (installMonth.value) params.month = installMonth.value
    if (installSearch.value) params.search = installSearch.value
    const r = await axios.get('/api/v1/timeshare/installments', { headers: h, params })
    installments.value = r.data.installments ?? []
    installSummary.value = r.data.summary ?? { overdue_total: 0, pending_total: 0 }
  } catch (e) { console.error(e) } finally { installLoading.value = false }
}

async function refreshAll() {
  loading.value = true
  await Promise.all([loadSummary(), loadCalendar(), loadClients(), loadInstallments()])
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
    await axios.post(`/api/v1/timeshare/installments/${payModal.inst_id}/pay`, {
      paid_amount: payModal.amount, payment_method: payModal.method,
      receipt_number: payModal.receipt_number || undefined,
    }, { headers: h })
    payModal.open = false
    await Promise.all([loadSummary(), loadInstallments(), loadClients()])
  } catch (e: any) { alert(e?.response?.data?.detail ?? 'فشل في تسجيل الدفعة') }
  finally { payModal.saving = false }
}

// ── Status / Cancel ──────────────────────────────────────────────────────
const statusSaving = ref<number | null>(null)
async function toggleStatus(c: Contract) {
  const next = c.status === 'active' ? 'suspended' : 'active'
  statusSaving.value = c.id
  try {
    await axios.patch(`/api/v1/timeshare/contracts/${c.id}`, { status: next }, { headers: h })
    c.status = next
    await loadSummary()
  } catch (e: any) { alert(e?.response?.data?.detail ?? 'خطأ في تغيير الحالة') }
  finally { statusSaving.value = null }
}

async function cancelContract(c: Contract) {
  if (!confirm(`إلغاء عقد ${c.customer_name}؟`)) return
  try {
    await axios.post(`/api/v1/timeshare/contracts/${c.id}/cancel`, { cancel_amount: 0 }, { headers: h })
    c.status = 'cancelled'
    await loadSummary()
  } catch (e: any) { alert(e?.response?.data?.detail ?? 'خطأ في الإلغاء') }
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
    const r = await axios.post('/api/v1/timeshare/contracts/import-excel', form, {
      headers: { ...h, 'Content-Type': 'multipart/form-data' }, params: { branch_id: branchId },
    })
    importModal.result = r.data
    await Promise.all([loadClients(), loadSummary()])
  } catch (e: any) {
    importModal.result = { error: e?.response?.data?.detail ?? 'فشل الاستيراد' }
  } finally { importModal.uploading = false }
}

// ── Badges ───────────────────────────────────────────────────────────────
function roomTypeBadge(type: string) {
  const m: Record<string, string> = {
    '2R': 'bg-sky-100 text-sky-700', '4R': 'bg-amber-100 text-amber-700', '6R': 'bg-emerald-100 text-emerald-700',
  }
  return `text-[10px] px-1.5 py-0.5 rounded-full font-bold ${m[type] || 'bg-stone-100 text-stone-500'}`
}
function statusBadge(s: string) {
  const m: Record<string, string> = {
    active: 'bg-green-100 text-green-700', suspended: 'bg-yellow-100 text-yellow-700',
    cancelled: 'bg-red-100 text-red-700', expired: 'bg-stone-200 text-stone-600',
  }
  return `text-[10px] px-1.5 py-0.5 rounded-full font-bold ${m[s] || 'bg-stone-100 text-stone-500'}`
}
function statusLabel(s: string) {
  return { active: '✅ نشط', suspended: '⏸️ موقوف', cancelled: '❌ ملغي', expired: '⌛ منتهي' }[s] || s
}
function payBadge(s: string) {
  const m: Record<string, string> = {
    paid: 'bg-green-100 text-green-700', pending: 'bg-yellow-100 text-yellow-700',
    overdue: 'bg-red-100 text-red-700', partial: 'bg-blue-100 text-blue-700',
  }
  return `px-2 py-0.5 rounded-full text-[10px] font-bold ${m[s] || 'bg-stone-100 text-stone-500'}`
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
        <button @click="importModal.open = true; importModal.result = null"
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
        <div class="bg-white rounded-2xl border border-stone-200 p-4 shadow-sm">
          <p class="text-[10px] text-gray-400 font-bold uppercase tracking-wide mb-2">عقود نشطة</p>
          <p class="text-2xl font-black text-gray-900">{{ summary.active_contracts || 0 }}</p>
        </div>
        <div class="bg-white rounded-2xl border border-stone-200 p-4 shadow-sm">
          <p class="text-[10px] text-gray-400 font-bold uppercase tracking-wide mb-2">نسبة التحصيل</p>
          <p :class="['text-2xl font-black', (summary.collection_rate_pct||0) >= 50 ? 'text-green-600' : 'text-amber-500']">
            {{ summary.collection_rate_pct || 0 }}%
          </p>
          <p class="text-[10px] text-gray-400 mt-1">{{ fmt(summary.total_collected) }} من {{ fmt(summary.total_value) }}</p>
        </div>
        <div class="bg-white rounded-2xl border border-red-200 p-4 shadow-sm">
          <p class="text-[10px] text-gray-400 font-bold uppercase tracking-wide mb-2">متأخرات</p>
          <p class="text-2xl font-black text-red-500">{{ fmt(summary.total_overdue) }}</p>
          <p class="text-[10px] text-gray-400 mt-1">{{ summary.overdue_contracts_count || 0 }} عقد متأخر</p>
        </div>
        <div class="bg-white rounded-2xl border border-amber-200 p-4 shadow-sm">
          <p class="text-[10px] text-gray-400 font-bold uppercase tracking-wide mb-2">مستحق هذا الشهر</p>
          <p class="text-2xl font-black text-amber-500">{{ fmt(summary.this_month_due) }}</p>
        </div>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div class="bg-white rounded-2xl border border-stone-200 p-5 shadow-sm">
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
        </div>

        <div class="bg-white rounded-2xl border border-red-100 p-5 shadow-sm">
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
        </div>
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
        <span class="text-xs text-gray-400">أسابيع محجوزة: <span class="text-amber-500 font-bold">{{ calendar.total_booked_weeks || 0 }}</span></span>
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
                <span :class="statusBadge(c.status)">{{ statusLabel(c.status) }}</span>
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
                      <td class="py-1.5"><span :class="payBadge(p.status)">{{ payLabel(p.status) }}</span></td>
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
              <button v-if="c.status === 'active'" @click="toggleStatus(c)" :disabled="statusSaving === c.id"
                class="px-4 py-2 rounded-xl bg-yellow-50 text-yellow-700 text-xs font-bold border border-yellow-200 hover:bg-yellow-100 disabled:opacity-40">⏸️ تعليق</button>
              <button v-else-if="c.status === 'suspended'" @click="toggleStatus(c)" :disabled="statusSaving === c.id"
                class="px-4 py-2 rounded-xl bg-green-50 text-green-700 text-xs font-bold border border-green-200 hover:bg-green-100 disabled:opacity-40">▶️ تفعيل</button>
              <button v-if="c.status !== 'cancelled'" @click="cancelContract(c)"
                class="px-4 py-2 rounded-xl bg-red-50 text-red-600 text-xs font-bold border border-red-200 hover:bg-red-100">🗑️ إلغاء</button>
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
      <div v-else class="bg-white rounded-2xl border border-stone-200 overflow-hidden shadow-sm">
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
              <td class="px-4 py-3"><span :class="payBadge(p.status)">{{ payLabel(p.status) }}</span></td>
              <td class="px-4 py-3">
                <button v-if="p.status !== 'paid'" @click="openPayModal(p)"
                  class="px-3 py-1 rounded-xl bg-green-50 text-green-700 text-[10px] font-bold border border-green-200 hover:bg-green-100">💰 دفع</button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <!-- ══ PAY MODAL ══ -->
    <Teleport to="body">
      <div v-if="payModal.open" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" @click.self="payModal.open = false">
        <div class="bg-white rounded-2xl p-6 w-full max-w-sm shadow-xl" dir="rtl">
          <h3 class="font-black text-sm text-gray-900 mb-1">💰 تسجيل دفعة</h3>
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
          <div class="flex gap-3 mt-5">
            <button @click="submitPayment" :disabled="payModal.saving || !payModal.amount"
              class="flex-1 py-2.5 bg-green-600 text-white rounded-xl text-sm font-bold disabled:opacity-40 hover:bg-green-700">
              {{ payModal.saving ? '⏳' : '✅ تأكيد الدفع' }}
            </button>
            <button @click="payModal.open = false" class="px-4 py-2.5 bg-stone-100 text-gray-500 rounded-xl text-sm font-bold hover:bg-stone-200">إلغاء</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ══ IMPORT MODAL ══ -->
    <Teleport to="body">
      <div v-if="importModal.open" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" @click.self="importModal.open = false">
        <div class="bg-white rounded-2xl p-6 w-full max-w-md shadow-xl" dir="rtl">
          <h3 class="font-black text-sm text-gray-900 mb-1">📥 استيراد عقود من Excel</h3>
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
          <div class="flex gap-3 mt-5">
            <button @click="submitImport" :disabled="!importModal.file || importModal.uploading"
              class="flex-1 py-2.5 bg-primary-700 text-white rounded-xl text-sm font-bold disabled:opacity-40 hover:bg-primary-800">
              {{ importModal.uploading ? '⏳ جاري الاستيراد...' : '📤 استيراد' }}
            </button>
            <button @click="importModal.open = false" class="px-4 py-2.5 bg-stone-100 text-gray-500 rounded-xl text-sm font-bold hover:bg-stone-200">إغلاق</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
