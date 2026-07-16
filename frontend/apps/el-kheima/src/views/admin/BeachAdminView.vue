<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, ENDPOINTS, useAuthStore } from '@resort-os/core'
import { AppCard, AppBadge, AppButton, AppModal, AppSpinner, EmptyState, useToast, useConfirm } from '@resort-os/ui'

const toast = useToast()
const { confirm } = useConfirm()
const auth = useAuthStore()
const branchId = auth.branchId
const tab = ref<'summary' | 'transactions' | 'b2b' | 'eod'>('summary')

// ── Interfaces ────────────────────────────────────────────────────────
interface BeachInventory {
  capacity_max: number; capacity_used: number; capacity_pct: number
  available_slots: number; towels_total: number; towels_used: number
  towels_available: number; surge_pct: number; surge_active: boolean
  surge_multiplier: number; adult_price: number; child_price: number
  resident_price: number; towel_price: number
}
interface BeachDailySummary {
  date: string; total_entries: number; total_revenue: number
  b2b_entries: number; b2b_revenue: number
  capacity_pct: number; surge_active: boolean; towels_rented: number
}
interface BeachTransaction {
  id: number; tx_type: string; quantity: number; unit_price: number
  total_amount: number; vat_amount: number; surge_applied: boolean
  tx_date: string; cashier_id: number | null; b2b_contract_id: number | null
  notes: string | null; voided_at: string | null; created_at: string
}
interface B2BContract {
  id: number; hotel_name: string; hotel_name_ar: string | null
  contact_phone: string | null; daily_quota: number; entry_price: number
  towel_price: number; valid_from: string; valid_until: string
  is_active: boolean; credit_limit: number | null; payment_terms_days: number
  last_settled_at: string | null; is_overdue: boolean; created_at: string
}
interface B2BStatus {
  contract_id: number; hotel_name: string; daily_quota: number
  used_today: number; remaining: number; quota_warning: boolean
  is_overdue: boolean; outstanding_balance: number | null
}
interface EodReport {
  date: string; total_entries: number; b2b_entries: number
  individual_entries: number; resident_entries: number
  towels_rented: number; total_revenue: number
  yesterday?: { total_entries: number; total_revenue: number } | null
  last_week?: { total_entries: number; total_revenue: number } | null
}

// ── State ─────────────────────────────────────────────────────────────
const loading = ref(false)
const inventory = ref<BeachInventory | null>(null)
const summary = ref<BeachDailySummary | null>(null)
const transactions = ref<BeachTransaction[]>([])
const txTotal = ref(0)
const txPage = ref(1)
const txDate = ref(new Date().toISOString().slice(0, 10))
const b2bContracts = ref<B2BContract[]>([])
const b2bStatus = ref<B2BStatus[]>([])
const eodReport = ref<EodReport | null>(null)
const eodDate = ref(new Date().toISOString().slice(0, 10))
const eodLoading = ref(false)
const downloadingPdf = ref(false)

// Surge modal
const surgeModal = ref(false)
const surgePct = ref('0')
const savingSurge = ref(false)

// B2B create modal
const b2bModal = ref(false)
const savingB2b = ref(false)
const b2bForm = ref({
  hotel_name: '', hotel_name_ar: '', contact_phone: '',
  daily_quota: '50', entry_price: '', towel_price: '0',
  valid_from: new Date().toISOString().slice(0, 10),
  valid_until: '', credit_limit: '', payment_terms_days: '30',
})

// B2B settle modal
const settleModal = ref(false)
const settlingContract = ref<B2BContract | null>(null)
const settledThrough = ref(new Date().toISOString().slice(0, 10))
const savingSettle = ref(false)

// B2B credit edit modal
const creditModal = ref(false)
const editingCredit = ref<B2BContract | null>(null)
const creditForm = ref({ credit_limit: '', payment_terms_days: '30' })
const savingCredit = ref(false)

// ── Computed ──────────────────────────────────────────────────────────
const capacityColor = computed(() => {
  if (!inventory.value) return 'bg-gray-200'
  const pct = inventory.value.capacity_pct
  if (pct >= 90) return 'bg-red-500'
  if (pct >= 70) return 'bg-amber-500'
  return 'bg-green-500'
})
const capacityTextColor = computed(() => {
  if (!inventory.value) return 'text-gray-600'
  const pct = inventory.value.capacity_pct
  if (pct >= 90) return 'text-red-600'
  if (pct >= 70) return 'text-amber-600'
  return 'text-green-600'
})

// ── Loaders ───────────────────────────────────────────────────────────
async function loadInventory() {
  try {
    const { data } = await api.get(ENDPOINTS.beach.inventory, {
      params: { branch_id: branchId }
    })
    inventory.value = data
    surgePct.value = String(data.surge_pct ?? 0)
  } catch { inventory.value = null }
}

async function loadSummary(date?: string) {
  try {
    const { data } = await api.get(ENDPOINTS.beach.summary, {
      params: { branch_id: branchId, tx_date: date ?? txDate.value }
    })
    summary.value = data
  } catch { summary.value = null }
}

async function loadTransactions() {
  loading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.beach.transactions, {
      params: { branch_id: branchId, tx_date: txDate.value, page: txPage.value, size: 50 }
    })
    transactions.value = data.items ?? []
    txTotal.value = data.total ?? 0
  } catch { transactions.value = [] }
  finally { loading.value = false }
}

async function loadB2B() {
  loading.value = true
  try {
    const [contractsRes, statusRes] = await Promise.all([
      api.get(ENDPOINTS.beach.b2bContracts, { params: { branch_id: branchId, active_only: false } }),
      api.get(ENDPOINTS.beach.b2bQuotaStatus, { params: { branch_id: branchId } }),
    ])
    b2bContracts.value = contractsRes.data ?? []
    b2bStatus.value = statusRes.data ?? []
  } catch { b2bContracts.value = [] }
  finally { loading.value = false }
}

async function loadEod() {
  eodLoading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.beach.eodReport, {
      params: { branch_id: branchId, report_date: eodDate.value }
    })
    eodReport.value = data
  } catch { eodReport.value = null }
  finally { eodLoading.value = false }
}

async function switchTab(t: typeof tab.value) {
  tab.value = t
  if (t === 'summary') { await Promise.all([loadInventory(), loadSummary()]) }
  else if (t === 'transactions') { await loadTransactions() }
  else if (t === 'b2b') { await loadB2B() }
  else if (t === 'eod') { await loadEod() }
}

// ── Actions ───────────────────────────────────────────────────────────
async function saveSurge() {
  savingSurge.value = true
  try {
    await api.patch(ENDPOINTS.beach.surge, { surge_pct: surgePct.value }, {
      params: { branch_id: branchId }
    })
    toast.success('تم تحديث الـ Surge')
    surgeModal.value = false
    await loadInventory()
  } catch(e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر تحديث الـ Surge')
  } finally { savingSurge.value = false }
}

async function downloadTicket(txId: number) {
  try {
    const { data } = await api.get(ENDPOINTS.beach.ticket(txId), { responseType: 'blob' })
    const url = URL.createObjectURL(data)
    const a = document.createElement('a'); a.href = url; a.download = `beach-ticket-${txId}.pdf`; a.click()
    setTimeout(() => URL.revokeObjectURL(url), 5000)
  } catch { toast.error('تعذّر تحميل التذكرة') }
}

async function downloadEodPdf() {
  downloadingPdf.value = true
  try {
    const { data } = await api.get(ENDPOINTS.beach.eodReportPdf, {
      params: { branch_id: branchId, report_date: eodDate.value }, responseType: 'blob'
    })
    const url = URL.createObjectURL(data)
    const a = document.createElement('a'); a.href = url; a.download = `beach-eod-${eodDate.value}.pdf`; a.click()
    setTimeout(() => URL.revokeObjectURL(url), 5000)
  } catch { toast.error('تعذّر تحميل التقرير') }
  finally { downloadingPdf.value = false }
}

async function createB2BContract() {
  if (!b2bForm.value.hotel_name || !b2bForm.value.entry_price || !b2bForm.value.valid_until) {
    toast.error('اسم الفندق، سعر الدخول، وتاريخ الانتهاء إلزامية'); return
  }
  savingB2b.value = true
  try {
    await api.post(ENDPOINTS.beach.b2bContracts, {
      branch_id: branchId,
      hotel_name: b2bForm.value.hotel_name,
      hotel_name_ar: b2bForm.value.hotel_name_ar || null,
      contact_phone: b2bForm.value.contact_phone || null,
      daily_quota: parseInt(b2bForm.value.daily_quota),
      entry_price: b2bForm.value.entry_price,
      towel_price: b2bForm.value.towel_price || '0',
      valid_from: b2bForm.value.valid_from,
      valid_until: b2bForm.value.valid_until,
      credit_limit: b2bForm.value.credit_limit || null,
      payment_terms_days: parseInt(b2bForm.value.payment_terms_days),
    })
    toast.success('تم إنشاء عقد B2B')
    b2bModal.value = false
    b2bForm.value = { hotel_name: '', hotel_name_ar: '', contact_phone: '', daily_quota: '50',
      entry_price: '', towel_price: '0', valid_from: new Date().toISOString().slice(0, 10),
      valid_until: '', credit_limit: '', payment_terms_days: '30' }
    await loadB2B()
  } catch(e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر إنشاء العقد')
  } finally { savingB2b.value = false }
}

function openSettle(c: B2BContract) {
  settlingContract.value = c
  settledThrough.value = new Date().toISOString().slice(0, 10)
  settleModal.value = true
}

async function doSettle() {
  if (!settlingContract.value) return
  savingSettle.value = true
  try {
    await api.post(ENDPOINTS.beach.b2bContractSettle(settlingContract.value.id), {
      settled_through: settledThrough.value
    })
    toast.success('تمت التسوية')
    settleModal.value = false
    await loadB2B()
  } catch(e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر إجراء التسوية')
  } finally { savingSettle.value = false }
}

function openCreditEdit(c: B2BContract) {
  editingCredit.value = c
  creditForm.value = {
    credit_limit: c.credit_limit != null ? String(c.credit_limit) : '',
    payment_terms_days: String(c.payment_terms_days),
  }
  creditModal.value = true
}

async function saveCreditEdit() {
  if (!editingCredit.value) return
  savingCredit.value = true
  try {
    await api.patch(ENDPOINTS.beach.b2bContract(editingCredit.value.id), {
      credit_limit: creditForm.value.credit_limit ? Number(creditForm.value.credit_limit) : null,
      payment_terms_days: parseInt(creditForm.value.payment_terms_days),
    })
    toast.success('تم تحديث بيانات الائتمان')
    creditModal.value = false
    await loadB2B()
  } catch(e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر التحديث')
  } finally { savingCredit.value = false }
}

function fmtMoney(n: number | null | undefined) {
  return (n ?? 0).toLocaleString('ar-EG', { maximumFractionDigits: 0 })
}
function fmtDate(d?: string | null) {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('ar-EG')
}
const txTypeLabels: Record<string, string> = {
  entry: 'دخول بالغ', entry_child: 'دخول طفل', entry_resident: 'مقيم',
  entry_towel: 'دخول + فوطة', towel_rent: 'إيجار فوطة', towel_return: 'إرجاع فوطة',
}

onMounted(() => switchTab('summary'))
</script>

<template>
  <div dir="rtl" class="space-y-5">
    <!-- Header -->
    <div class="flex items-center justify-between">
      <div>
        <h1 class="text-2xl font-black text-gray-800 dark:text-gray-200">إدارة الشاطئ</h1>
        <p class="text-sm text-gray-500 dark:text-gray-500 mt-1">ملخص يومي، معاملات، عقود B2B، وتقارير نهاية اليوم</p>
      </div>
    </div>

    <!-- Tabs -->
    <div class="flex gap-1 bg-stone-100 dark:bg-gray-700 p-1 rounded-xl w-fit flex-wrap">
      <button v-for="t in [
        { val: 'summary',      label: '📊 الملخص اليومي' },
        { val: 'transactions', label: '🧾 المعاملات' },
        { val: 'b2b',          label: '🤝 عقود B2B' },
        { val: 'eod',          label: '📋 تقرير نهاية اليوم' },
      ]" :key="t.val" @click="switchTab(t.val as any)"
        :class="['px-4 py-2 rounded-lg text-sm font-semibold transition-all',
          tab === t.val ? 'bg-white dark:bg-surface shadow-sm text-gray-900 dark:text-gray-100' : 'text-gray-500 hover:text-gray-700']"
      >{{ t.label }}</button>
    </div>

    <!-- ══ TAB: SUMMARY ══ -->
    <div v-if="tab === 'summary'" class="space-y-4">
      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <template v-else>
        <!-- Capacity Card -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
          <AppCard padding="md">
            <div class="flex items-center justify-between mb-3">
              <span class="text-sm text-gray-500 dark:text-gray-500">السعة الحالية</span>
              <AppBadge v-if="inventory?.surge_active" variant="warning">Surge نشط {{ inventory?.surge_pct }}%</AppBadge>
            </div>
            <div :class="['text-3xl font-black', capacityTextColor]">
              {{ inventory?.capacity_used ?? 0 }} / {{ inventory?.capacity_max ?? 0 }}
            </div>
            <div class="mt-3 bg-gray-100 rounded-full h-3">
              <div :class="['h-3 rounded-full transition-all', capacityColor]"
                :style="{ width: (inventory?.capacity_pct ?? 0) + '%' }"></div>
            </div>
            <div class="text-xs text-gray-400 dark:text-gray-500 mt-1">{{ inventory?.available_slots ?? 0 }} مكان متاح</div>
          </AppCard>

          <AppCard padding="md">
            <div class="text-sm text-gray-500 dark:text-gray-500 mb-2">الفوط</div>
            <div class="text-2xl font-black text-gray-800 dark:text-gray-200">{{ inventory?.towels_used ?? 0 }} / {{ inventory?.towels_total ?? 0 }}</div>
            <div class="text-xs text-gray-400 dark:text-gray-500 mt-1">{{ inventory?.towels_available ?? 0 }} متاحة</div>
          </AppCard>

          <AppCard padding="md">
            <div class="text-sm text-gray-500 dark:text-gray-500 mb-2">الأسعار الأساسية</div>
            <div class="space-y-1 text-sm">
              <div class="flex justify-between"><span class="text-gray-500 dark:text-gray-500">بالغ:</span><span class="font-bold">{{ fmtMoney(inventory?.adult_price) }} ج</span></div>
              <div class="flex justify-between"><span class="text-gray-500 dark:text-gray-500">طفل:</span><span class="font-bold">{{ fmtMoney(inventory?.child_price) }} ج</span></div>
              <div class="flex justify-between"><span class="text-gray-500 dark:text-gray-500">مقيم:</span><span class="font-bold">{{ fmtMoney(inventory?.resident_price) }} ج</span></div>
              <div class="flex justify-between"><span class="text-gray-500 dark:text-gray-500">فوطة:</span><span class="font-bold">{{ fmtMoney(inventory?.towel_price) }} ج</span></div>
            </div>
          </AppCard>
        </div>
        </template>

        <!-- Summary KPIs -->
        <div v-if="summary" class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <AppCard padding="md">
            <div class="text-sm text-gray-500 dark:text-gray-500 mb-1">إجمالي الدخول</div>
            <div class="text-2xl font-black text-gray-800 dark:text-gray-200">{{ summary.total_entries }}</div>
          </AppCard>
          <AppCard padding="md">
            <div class="text-sm text-gray-500 dark:text-gray-500 mb-1">إجمالي الإيراد</div>
            <div class="text-2xl font-black text-green-600">{{ fmtMoney(summary.total_revenue) }}</div>
            <div class="text-xs text-gray-400 dark:text-gray-500">جنيه</div>
          </AppCard>
          <AppCard padding="md">
            <div class="text-sm text-gray-500 dark:text-gray-500 mb-1">دخول B2B</div>
            <div class="text-2xl font-black text-blue-700">{{ summary.b2b_entries }}</div>
            <div class="text-xs text-gray-400 dark:text-gray-500">{{ fmtMoney(summary.b2b_revenue) }} ج</div>
          </AppCard>
          <AppCard padding="md">
            <div class="text-sm text-gray-500 dark:text-gray-500 mb-1">فوط مُؤجَّرة</div>
            <div class="text-2xl font-black text-gray-800 dark:text-gray-200">{{ summary.towels_rented }}</div>
          </AppCard>
        </div>
        <EmptyState v-else icon="🏖️" title="لا توجد بيانات لهذا اليوم" />

        <!-- Surge control -->
        <AppCard padding="md">
          <div class="flex items-center justify-between">
            <div>
              <div class="font-semibold text-gray-800 dark:text-gray-200">ضبط نسبة الـ Surge</div>
              <div class="text-sm text-gray-500 dark:text-gray-500">زيادة مؤقتة على الأسعار في أوقات الذروة</div>
            </div>
            <AppButton variant="outline" size="sm" @click="surgeModal = true">
              {{ inventory?.surge_active ? '✏️ تعديل Surge' : '⚡ تفعيل Surge' }}
            </AppButton>
          </div>
        </AppCard>
    </div>

    <!-- ══ TAB: TRANSACTIONS ══ -->
    <div v-else-if="tab === 'transactions'" class="space-y-4">
      <div class="flex items-center gap-3">
        <input type="date" v-model="txDate" @change="loadTransactions"
          class="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        <span class="text-sm text-gray-500 dark:text-gray-500">{{ txTotal }} معاملة</span>
      </div>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <AppCard v-else padding="none">
        <EmptyState v-if="!transactions.length" icon="🧾" title="لا توجد معاملات لهذا اليوم" />
        <div v-else class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">النوع</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الكمية</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">السعر</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الإجمالي</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الوقت</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الحالة</th>
                <th class="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="tx in transactions" :key="tx.id"
                :class="['border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60', tx.voided_at ? 'opacity-50' : '']">
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ txTypeLabels[tx.tx_type] ?? tx.tx_type }}</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ tx.quantity }}</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ fmtMoney(tx.unit_price) }} ج</td>
                <td class="px-4 py-3 text-sm font-bold text-gray-900 dark:text-gray-100">{{ fmtMoney(tx.total_amount) }} ج</td>
                <td class="px-4 py-3 text-xs text-gray-500 dark:text-gray-500">{{ new Date(tx.created_at).toLocaleTimeString('ar-EG') }}</td>
                <td class="px-4 py-3">
                  <AppBadge v-if="tx.voided_at" variant="danger">ملغاة</AppBadge>
                  <AppBadge v-else-if="tx.surge_applied" variant="warning">Surge</AppBadge>
                  <AppBadge v-else variant="success">مكتملة</AppBadge>
                </td>
                <td class="px-4 py-3">
                  <button v-if="!tx.voided_at" @click="downloadTicket(tx.id)"
                    class="text-xs text-blue-600 hover:underline">🖨️ تذكرة</button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </div>

    <!-- ══ TAB: B2B ══ -->
    <div v-else-if="tab === 'b2b'" class="space-y-4">
      <div class="flex items-center justify-between">
        <div class="text-sm text-gray-500 dark:text-gray-500">{{ b2bContracts.length }} عقد</div>
        <AppButton v-if="auth.hasRole('admin')" size="sm" @click="b2bModal = true">+ إضافة عقد</AppButton>
      </div>

      <!-- B2B status alerts -->
      <div v-if="b2bStatus.some(s => s.is_overdue || s.quota_warning)" class="space-y-2">
        <div v-for="s in b2bStatus.filter(x => x.is_overdue || x.quota_warning)" :key="s.contract_id"
          :class="['rounded-lg px-4 py-3 text-sm font-semibold',
            s.is_overdue ? 'bg-red-50 text-red-700 border border-red-200' : 'bg-amber-50 text-amber-700 border border-amber-200']">
          {{ s.is_overdue ? '⚠️ متأخر: ' : '⚡ حصة منخفضة: ' }} {{ s.hotel_name }}
          — {{ s.remaining }} مكان متبقٍ اليوم
        </div>
      </div>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <AppCard v-else padding="none">
        <EmptyState v-if="!b2bContracts.length" icon="🤝" title="لا توجد عقود B2B" />
        <div v-else class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الفندق</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الحصة اليومية</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">السعر</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">حد الائتمان</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">مهلة السداد</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الحالة</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">الصلاحية</th>
                <th class="px-4 py-3"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="c in b2bContracts" :key="c.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3">
                  <div class="font-semibold text-sm text-gray-900 dark:text-gray-100">{{ c.hotel_name }}</div>
                  <div v-if="c.hotel_name_ar" class="text-xs text-gray-500 dark:text-gray-500">{{ c.hotel_name_ar }}</div>
                </td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ c.daily_quota }}</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ fmtMoney(c.entry_price) }} ج</td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">
                  {{ c.credit_limit != null ? fmtMoney(c.credit_limit) + ' ج' : '—' }}
                </td>
                <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ c.payment_terms_days }} يوم</td>
                <td class="px-4 py-3">
                  <AppBadge v-if="c.is_overdue" variant="danger">متأخر</AppBadge>
                  <AppBadge v-else-if="!c.is_active" variant="neutral">موقوف</AppBadge>
                  <AppBadge v-else variant="success">نشط</AppBadge>
                </td>
                <td class="px-4 py-3 text-xs text-gray-500 dark:text-gray-500">{{ fmtDate(c.valid_from) }} → {{ fmtDate(c.valid_until) }}</td>
                <td class="px-4 py-3">
                  <div class="flex gap-2">
                    <button @click="openCreditEdit(c)" class="text-xs text-blue-600 hover:underline">✏️ ائتمان</button>
                    <button @click="openSettle(c)" class="text-xs text-green-600 hover:underline">✅ تسوية</button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </div>

    <!-- ══ TAB: EOD ══ -->
    <div v-else-if="tab === 'eod'" class="space-y-4">
      <div class="flex items-center gap-3">
        <input type="date" v-model="eodDate" @change="loadEod"
          class="border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        <AppButton size="sm" variant="outline" :loading="downloadingPdf" @click="downloadEodPdf">
          📄 تحميل PDF
        </AppButton>
      </div>

      <div v-if="eodLoading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <template v-else-if="eodReport">
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
          <AppCard padding="md">
            <div class="text-sm text-gray-500 dark:text-gray-500 mb-1">إجمالي الدخول</div>
            <div class="text-2xl font-black text-gray-800 dark:text-gray-200">{{ eodReport.total_entries }}</div>
            <div v-if="eodReport.yesterday" class="text-xs text-gray-400 dark:text-gray-500 mt-1">
              أمس: {{ eodReport.yesterday.total_entries }}
              <span :class="eodReport.total_entries >= eodReport.yesterday.total_entries ? 'text-green-500' : 'text-red-500'">
                {{ eodReport.total_entries >= eodReport.yesterday.total_entries ? '↑' : '↓' }}
              </span>
            </div>
          </AppCard>
          <AppCard padding="md">
            <div class="text-sm text-gray-500 dark:text-gray-500 mb-1">الإيراد الكلي</div>
            <div class="text-2xl font-black text-green-600">{{ fmtMoney(eodReport.total_revenue) }}</div>
            <div v-if="eodReport.yesterday" class="text-xs text-gray-400 dark:text-gray-500 mt-1">
              أمس: {{ fmtMoney(eodReport.yesterday.total_revenue) }} ج
            </div>
          </AppCard>
          <AppCard padding="md">
            <div class="text-sm text-gray-500 dark:text-gray-500 mb-1">دخول B2B</div>
            <div class="text-2xl font-black text-blue-700">{{ eodReport.b2b_entries }}</div>
          </AppCard>
          <AppCard padding="md">
            <div class="text-sm text-gray-500 dark:text-gray-500 mb-1">دخول أفراد</div>
            <div class="text-2xl font-black text-gray-800 dark:text-gray-200">{{ eodReport.individual_entries }}</div>
            <div class="text-xs text-gray-400 dark:text-gray-500">{{ eodReport.resident_entries }} مقيم</div>
          </AppCard>
        </div>

        <!-- Last week comparison -->
        <AppCard v-if="eodReport.last_week" padding="md" title="مقارنة بنفس اليوم الأسبوع الماضي">
          <div class="grid grid-cols-2 gap-4">
            <div>
              <div class="text-sm text-gray-500 dark:text-gray-500">الدخول</div>
              <div class="flex items-center gap-2">
                <span class="text-xl font-black text-gray-800 dark:text-gray-200">{{ eodReport.total_entries }}</span>
                <span class="text-sm text-gray-400 dark:text-gray-500">vs {{ eodReport.last_week.total_entries }}</span>
                <span :class="eodReport.total_entries >= eodReport.last_week.total_entries ? 'text-green-500 font-bold' : 'text-red-500 font-bold'">
                  {{ eodReport.total_entries >= eodReport.last_week.total_entries ? '▲' : '▼' }}
                </span>
              </div>
            </div>
            <div>
              <div class="text-sm text-gray-500 dark:text-gray-500">الإيراد</div>
              <div class="flex items-center gap-2">
                <span class="text-xl font-black text-gray-800 dark:text-gray-200">{{ fmtMoney(eodReport.total_revenue) }}</span>
                <span class="text-sm text-gray-400 dark:text-gray-500">vs {{ fmtMoney(eodReport.last_week.total_revenue) }}</span>
                <span :class="eodReport.total_revenue >= eodReport.last_week.total_revenue ? 'text-green-500 font-bold' : 'text-red-500 font-bold'">
                  {{ eodReport.total_revenue >= eodReport.last_week.total_revenue ? '▲' : '▼' }}
                </span>
              </div>
            </div>
          </div>
        </AppCard>
      <EmptyState v-else icon="📋" title="لا توجد بيانات لهذا اليوم" />
      </template>
    </div>

    <!-- ══ MODAL: SURGE ══ -->
    <AppModal :open="surgeModal" @close="surgeModal = false" title="ضبط نسبة الـ Surge">
      <div class="space-y-4">
        <div>
          <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">نسبة الـ Surge (%)</label>
          <input v-model="surgePct" type="number" min="0" max="200" step="5"
            class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          <p class="text-xs text-gray-400 dark:text-gray-500 mt-1">0 = إيقاف Surge — مثال: 50 يعني الأسعار تزيد 50%</p>
        </div>
        <div class="flex gap-3 justify-end">
          <AppButton variant="ghost" @click="surgeModal = false">إلغاء</AppButton>
          <AppButton :loading="savingSurge" @click="saveSurge">حفظ</AppButton>
        </div>
      </div>
    </AppModal>

    <!-- ══ MODAL: CREATE B2B ══ -->
    <AppModal :open="b2bModal" @close="b2bModal = false" title="إضافة عقد B2B جديد">
      <div class="space-y-3">
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">اسم الفندق *</label>
            <input v-model="b2bForm.hotel_name" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">الاسم بالعربي</label>
            <input v-model="b2bForm.hotel_name_ar" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">رقم التواصل</label>
            <input v-model="b2bForm.contact_phone" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">الحصة اليومية</label>
            <input v-model="b2bForm.daily_quota" type="number" min="1" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">سعر الدخول (ج) *</label>
            <input v-model="b2bForm.entry_price" type="number" min="0" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">سعر الفوطة (ج)</label>
            <input v-model="b2bForm.towel_price" type="number" min="0" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">من تاريخ</label>
            <input v-model="b2bForm.valid_from" type="date" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">حتى تاريخ *</label>
            <input v-model="b2bForm.valid_until" type="date" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">حد الائتمان (ج)</label>
            <input v-model="b2bForm.credit_limit" type="number" min="0" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" placeholder="اتركه فارغاً للـ unlimited" />
          </div>
          <div>
            <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">مهلة السداد (يوم)</label>
            <input v-model="b2bForm.payment_terms_days" type="number" min="1" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
          </div>
        </div>
        <div class="flex gap-3 justify-end pt-2">
          <AppButton variant="ghost" @click="b2bModal = false">إلغاء</AppButton>
          <AppButton :loading="savingB2b" @click="createB2BContract">إنشاء العقد</AppButton>
        </div>
      </div>
    </AppModal>

    <!-- ══ MODAL: SETTLE ══ -->
    <AppModal :open="settleModal" @close="settleModal = false" :title="`تسوية رصيد: ${settlingContract?.hotel_name}`">
      <div class="space-y-4">
        <p class="text-sm text-gray-600 dark:text-gray-500">تسجيل تحصيل الرصيد المستحق على الفندق حتى التاريخ المحدد.</p>
        <div>
          <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">محصّل حتى تاريخ</label>
          <input v-model="settledThrough" type="date" class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
        <div class="flex gap-3 justify-end">
          <AppButton variant="ghost" @click="settleModal = false">إلغاء</AppButton>
          <AppButton :loading="savingSettle" @click="doSettle">تأكيد التسوية</AppButton>
        </div>
      </div>
    </AppModal>

    <!-- ══ MODAL: CREDIT EDIT ══ -->
    <AppModal :open="creditModal" @close="creditModal = false" :title="`تعديل ائتمان: ${editingCredit?.hotel_name}`">
      <div class="space-y-3">
        <div>
          <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">حد الائتمان (ج)</label>
          <input v-model="creditForm.credit_limit" type="number" min="0"
            class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
            placeholder="فارغ = unlimited" />
        </div>
        <div>
          <label class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-1">مهلة السداد (يوم)</label>
          <input v-model="creditForm.payment_terms_days" type="number" min="1"
            class="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm" />
        </div>
        <div class="flex gap-3 justify-end">
          <AppButton variant="ghost" @click="creditModal = false">إلغاء</AppButton>
          <AppButton :loading="savingCredit" @click="saveCreditEdit">حفظ</AppButton>
        </div>
      </div>
    </AppModal>
  </div>
</template>
