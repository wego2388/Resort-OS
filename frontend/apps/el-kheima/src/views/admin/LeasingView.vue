<script setup lang="ts">
// LeasingView — يغطي فجوة كانت موجودة: الباك إند (app/modules/leasing) عنده
// 9 endpoints حقيقية (عقود إيجار تجاري، دفعات، غرامات تأخير، سجل كاش
// المستأجرين، إيصال PDF) لكن مفيش أي شاشة/route/عنصر قائمة في el-kheima —
// مستحيل أي حد يستخدم الميزة دي فعليًا رغم إنها مبنية بالكامل في الباك إند.
import { ref, computed, onMounted } from 'vue'
import { api, useAuthStore } from '@resort-os/core'
import { AppCard, AppBadge, AppButton, AppModal, AppSpinner, EmptyState, useToast, useConfirm } from '@resort-os/ui'

const auth = useAuthStore()
const toast = useToast()
const { confirm } = useConfirm()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

interface Payment {
  id: number; contract_id: number; due_date: string; amount: number
  penalty: number; paid_amount: number; status: string
  paid_at: string | null; payment_method: string | null
  receipt_number: string | null; year_n: number; notes: string | null
}
interface CashLog {
  id: number; amount: number; activity_type: string
  payment_method: string | null; reference: string | null
  notes: string | null; created_at: string
}
interface Contract {
  id: number; contract_number: string; tenant_name: string; tenant_phone: string | null
  tenant_national_id: string | null; unit_description: string
  start_date: string; end_date: string
  base_rent: number; increase_rate: number; billing_day: number
  grace_months: number; payment_period: string; security_deposit: number
  status: string; notes: string | null
  payments: Payment[]
}

const contracts = ref<Contract[]>([])
const loading = ref(false)
const statusFilter = ref<string>('')
const expandedId = ref<number | null>(null)
const cashLogsByContract = ref<Record<number, CashLog[]>>({})

const statusConfig: Record<string, { label: string; variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }> = {
  draft:      { label: 'مسودة',  variant: 'neutral' },
  active:     { label: 'نشط',    variant: 'success' },
  expired:    { label: 'منتهي',  variant: 'warning' },
  terminated: { label: 'مفسوخ',  variant: 'danger' },
}
const paymentStatusConfig: Record<string, { label: string; variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }> = {
  pending:  { label: 'مستحق',  variant: 'warning' },
  paid:     { label: 'مدفوع',  variant: 'success' },
  overdue:  { label: 'متأخر',  variant: 'danger' },
  partial:  { label: 'جزئي',   variant: 'info' },
}
const paymentPeriodLabels: Record<string, string> = {
  monthly: 'شهري', quarterly: 'ربع سنوي', biannual: 'نصف سنوي', annual: 'سنوي',
}
const activityTypeLabels: Record<string, string> = {
  rent_payment: 'دفعة إيجار', penalty: 'غرامة', deposit: 'تأمين',
  refund: 'استرداد', maintenance: 'صيانة', revenue_share: 'حصة إيراد', other: 'أخرى',
}

async function loadContracts() {
  loading.value = true
  try {
    const params: Record<string, any> = { branch_id: branchId, size: 100 }
    if (statusFilter.value) params.status = statusFilter.value
    const { data } = await api.get('/api/v1/leasing/contracts', { params })
    contracts.value = data.items
  } catch { toast.error('تعذّر تحميل عقود الإيجار — حاول تاني') }
  finally { loading.value = false }
}

async function toggleExpand(contract: Contract) {
  if (expandedId.value === contract.id) { expandedId.value = null; return }
  expandedId.value = contract.id
  if (!cashLogsByContract.value[contract.id]) await loadCashLogs(contract.id)
}

async function loadCashLogs(contractId: number) {
  try {
    const { data } = await api.get(`/api/v1/leasing/contracts/${contractId}/cash-logs`)
    cashLogsByContract.value[contractId] = data
  } catch { toast.error('تعذّر تحميل سجل الكاش') }
}

// ── Create/Edit Contract ──────────────────────────────────────────────
const contractModal = ref({ open: false, editingId: null as number | null })
const contractForm = ref({
  tenant_name: '', tenant_phone: '', tenant_national_id: '', unit_description: '',
  start_date: '', end_date: '', base_rent: '', increase_rate: '0',
  billing_day: '1', grace_months: '0', payment_period: 'monthly',
  security_deposit: '0', notes: '', status: 'draft',
})
const savingContract = ref(false)

function openCreateContract() {
  contractModal.value = { open: true, editingId: null }
  contractForm.value = {
    tenant_name: '', tenant_phone: '', tenant_national_id: '', unit_description: '',
    start_date: '', end_date: '', base_rent: '', increase_rate: '0',
    billing_day: '1', grace_months: '0', payment_period: 'monthly',
    security_deposit: '0', notes: '', status: 'draft',
  }
}

function openEditContract(c: Contract) {
  contractModal.value = { open: true, editingId: c.id }
  contractForm.value = {
    tenant_name: c.tenant_name, tenant_phone: c.tenant_phone ?? '',
    tenant_national_id: c.tenant_national_id ?? '', unit_description: c.unit_description,
    start_date: c.start_date, end_date: c.end_date,
    base_rent: String(c.base_rent), increase_rate: String(c.increase_rate),
    billing_day: String(c.billing_day), grace_months: String(c.grace_months),
    payment_period: c.payment_period, security_deposit: String(c.security_deposit),
    notes: c.notes ?? '', status: c.status,
  }
}

async function saveContract() {
  savingContract.value = true
  try {
    if (contractModal.value.editingId) {
      await api.patch(`/api/v1/leasing/contracts/${contractModal.value.editingId}`, {
        tenant_phone: contractForm.value.tenant_phone || null,
        status: contractForm.value.status,
        notes: contractForm.value.notes || null,
      })
      toast.success('تم تحديث العقد')
    } else {
      await api.post('/api/v1/leasing/contracts', {
        branch_id: branchId,
        tenant_name: contractForm.value.tenant_name,
        tenant_phone: contractForm.value.tenant_phone || null,
        tenant_national_id: contractForm.value.tenant_national_id || null,
        unit_description: contractForm.value.unit_description,
        start_date: contractForm.value.start_date,
        end_date: contractForm.value.end_date,
        base_rent: contractForm.value.base_rent,
        increase_rate: contractForm.value.increase_rate,
        billing_day: parseInt(contractForm.value.billing_day, 10),
        grace_months: parseInt(contractForm.value.grace_months, 10),
        payment_period: contractForm.value.payment_period,
        security_deposit: contractForm.value.security_deposit,
        notes: contractForm.value.notes || null,
      })
      toast.success('تم إنشاء عقد الإيجار')
    }
    contractModal.value.open = false
    await loadContracts()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر حفظ العقد')
  } finally {
    savingContract.value = false
  }
}

// ── Pay Payment ────────────────────────────────────────────────────────
const payModal = ref({ open: false, payment: null as Payment | null, contractId: 0 })
const payForm = ref({ paid_amount: '', payment_method: 'cash', receipt_number: '', notes: '' })
const payingInProgress = ref(false)

function openPayModal(contract: Contract, payment: Payment) {
  payModal.value = { open: true, payment, contractId: contract.id }
  payForm.value = {
    paid_amount: String(Number(payment.amount) + Number(payment.penalty)),
    payment_method: 'cash', receipt_number: '', notes: '',
  }
}

async function submitPayment() {
  if (!payModal.value.payment) return
  payingInProgress.value = true
  try {
    await api.post(`/api/v1/leasing/payments/${payModal.value.payment.id}/pay`, {
      paid_amount: payForm.value.paid_amount,
      payment_method: payForm.value.payment_method,
      receipt_number: payForm.value.receipt_number || null,
      notes: payForm.value.notes || null,
    })
    toast.success('تم تسجيل الدفعة')
    payModal.value.open = false
    await loadContracts()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر تسجيل الدفعة')
  } finally {
    payingInProgress.value = false
  }
}

async function downloadReceipt(payment: Payment) {
  try {
    const res = await api.get(`/api/v1/leasing/payments/${payment.id}/receipt`, { responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    window.open(url, '_blank')
  } catch {
    toast.error('تعذّر تحميل الإيصال — تأكد إن الدفعة مسجّلة بالفعل')
  }
}

async function applyPenalties(contract: Contract) {
  const ok = await confirm({
    title: 'تطبيق غرامات التأخير',
    message: `هل تريد فحص كل دفعات "${contract.tenant_name}" وتطبيق غرامة تأخير على أي دفعة متأخرة؟`,
  })
  if (!ok) return
  try {
    const { data } = await api.post(`/api/v1/leasing/contracts/${contract.id}/apply-penalties`)
    toast.success(`تم تحديث ${data.updated} دفعة متأخرة`)
    await loadContracts()
  } catch { toast.error('تعذّر تطبيق الغرامات') }
}

// ── Cash Log ─────────────────────────────────────────────────────────
const cashLogModal = ref({ open: false, contractId: 0 })
const cashLogForm = ref({ amount: '', activity_type: 'rent_payment', payment_method: '', reference: '', notes: '' })
const savingCashLog = ref(false)

function openCashLogModal(contractId: number) {
  cashLogModal.value = { open: true, contractId }
  cashLogForm.value = { amount: '', activity_type: 'rent_payment', payment_method: '', reference: '', notes: '' }
}

async function saveCashLog() {
  savingCashLog.value = true
  try {
    await api.post(`/api/v1/leasing/contracts/${cashLogModal.value.contractId}/cash-logs`, {
      branch_id: branchId, contract_id: cashLogModal.value.contractId,
      amount: cashLogForm.value.amount, activity_type: cashLogForm.value.activity_type,
      payment_method: cashLogForm.value.payment_method || null,
      reference: cashLogForm.value.reference || null,
      notes: cashLogForm.value.notes || null,
    })
    toast.success('تم تسجيل حركة الكاش')
    cashLogModal.value.open = false
    await loadCashLogs(cashLogModal.value.contractId)
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر تسجيل الحركة')
  } finally {
    savingCashLog.value = false
  }
}

onMounted(loadContracts)
</script>

<template>
  <div dir="rtl">
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-2xl font-black text-gray-900">عقود الإيجار التجاري</h2>
      <AppButton v-if="auth.hasRole('manager')" size="sm" @click="openCreateContract">+ عقد جديد</AppButton>
    </div>

    <div class="flex gap-2 mb-4">
      <select v-model="statusFilter" @change="loadContracts" class="border border-stone-200 rounded-lg px-3 py-1.5 text-sm">
        <option value="">كل الحالات</option>
        <option v-for="(cfg, key) in statusConfig" :key="key" :value="key">{{ cfg.label }}</option>
      </select>
    </div>

    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
    <div v-else class="space-y-3">
      <AppCard v-for="c in contracts" :key="c.id" padding="none">
        <div class="p-4 cursor-pointer" @click="toggleExpand(c)">
          <div class="flex items-center justify-between">
            <div>
              <div class="flex items-center gap-2 mb-1">
                <span class="font-mono text-xs text-gray-400">{{ c.contract_number }}</span>
                <span class="font-bold text-gray-900">{{ c.tenant_name }}</span>
              </div>
              <div class="text-sm text-gray-500">{{ c.unit_description }}</div>
              <div class="text-xs text-gray-400 mt-1">
                {{ c.start_date }} → {{ c.end_date }} · {{ paymentPeriodLabels[c.payment_period] }}
              </div>
            </div>
            <div class="flex items-center gap-3">
              <div class="text-left">
                <div class="font-bold text-blue-700">{{ Number(c.base_rent).toLocaleString('ar-EG') }} ج</div>
                <div class="text-[10px] text-gray-400">الإيجار الأساسي</div>
              </div>
              <AppBadge size="sm" :variant="statusConfig[c.status]?.variant ?? 'neutral'">
                {{ statusConfig[c.status]?.label ?? c.status }}
              </AppBadge>
            </div>
          </div>
        </div>

        <div v-if="expandedId === c.id" class="border-t border-stone-100 p-4 bg-stone-50">
          <div class="flex items-center justify-between mb-3">
            <h4 class="font-bold text-sm text-gray-700">الدفعات</h4>
            <div class="flex gap-2" v-if="auth.hasRole('manager')">
              <AppButton size="sm" variant="secondary" @click="openEditContract(c)">تعديل العقد</AppButton>
              <AppButton size="sm" variant="secondary" @click="applyPenalties(c)">تطبيق غرامات التأخير</AppButton>
              <AppButton size="sm" variant="secondary" @click="openCashLogModal(c.id)">+ حركة كاش</AppButton>
            </div>
          </div>

          <div class="overflow-x-auto mb-4">
            <table class="w-full text-sm">
              <thead>
                <tr class="text-xs text-gray-400">
                  <th class="text-right py-1">الاستحقاق</th>
                  <th class="text-right py-1">المبلغ</th>
                  <th class="text-right py-1">غرامة</th>
                  <th class="text-right py-1">المدفوع</th>
                  <th class="text-right py-1">الحالة</th>
                  <th class="text-right py-1">إجراء</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="p in c.payments" :key="p.id" class="border-t border-stone-100">
                  <td class="py-2">{{ p.due_date }}</td>
                  <td class="py-2 font-medium">{{ Number(p.amount).toLocaleString('ar-EG') }} ج</td>
                  <td class="py-2 text-red-500">{{ Number(p.penalty).toLocaleString('ar-EG') }} ج</td>
                  <td class="py-2">{{ Number(p.paid_amount).toLocaleString('ar-EG') }} ج</td>
                  <td class="py-2">
                    <AppBadge size="sm" :variant="paymentStatusConfig[p.status]?.variant ?? 'neutral'">
                      {{ paymentStatusConfig[p.status]?.label ?? p.status }}
                    </AppBadge>
                  </td>
                  <td class="py-2">
                    <div class="flex gap-2">
                      <AppButton v-if="p.status !== 'paid'" size="sm" @click="openPayModal(c, p)">تسجيل دفع</AppButton>
                      <AppButton v-else size="sm" variant="secondary" @click="downloadReceipt(p)">الإيصال</AppButton>
                    </div>
                  </td>
                </tr>
                <tr v-if="c.payments.length === 0">
                  <td colspan="6" class="py-6 text-center text-gray-400 text-xs">لا توجد دفعات مجدولة</td>
                </tr>
              </tbody>
            </table>
          </div>

          <h4 class="font-bold text-sm text-gray-700 mb-2">سجل كاش المستأجر</h4>
          <div class="space-y-1">
            <div v-for="log in (cashLogsByContract[c.id] ?? [])" :key="log.id"
              class="flex items-center justify-between text-sm bg-white rounded-lg px-3 py-2 border border-stone-100">
              <span>{{ activityTypeLabels[log.activity_type] ?? log.activity_type }}</span>
              <span class="font-bold">{{ Number(log.amount).toLocaleString('ar-EG') }} ج</span>
              <span class="text-xs text-gray-400">{{ new Date(log.created_at).toLocaleDateString('ar-EG') }}</span>
            </div>
            <EmptyState v-if="(cashLogsByContract[c.id] ?? []).length === 0" icon="💵" title="لا توجد حركات كاش" />
          </div>
        </div>
      </AppCard>
      <EmptyState v-if="contracts.length === 0" icon="🏢" title="لا توجد عقود إيجار" />
    </div>

    <!-- Create/Edit Contract Modal -->
    <AppModal :open="contractModal.open" :title="contractModal.editingId ? 'تعديل العقد' : 'عقد إيجار جديد'" size="lg" @close="contractModal.open = false">
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <template v-if="!contractModal.editingId">
          <input v-model="contractForm.tenant_name" type="text" placeholder="اسم المستأجر"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm sm:col-span-2" />
          <input v-model="contractForm.unit_description" type="text" placeholder="وصف الوحدة"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm sm:col-span-2" />
          <input v-model="contractForm.tenant_phone" type="text" placeholder="هاتف المستأجر"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <input v-model="contractForm.tenant_national_id" type="text" placeholder="الرقم القومي"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <div><label class="block text-xs text-gray-400 mb-1">تاريخ البداية</label>
            <input v-model="contractForm.start_date" type="date" class="border border-stone-200 rounded-xl px-3 py-2 text-sm w-full" /></div>
          <div><label class="block text-xs text-gray-400 mb-1">تاريخ النهاية</label>
            <input v-model="contractForm.end_date" type="date" class="border border-stone-200 rounded-xl px-3 py-2 text-sm w-full" /></div>
          <input v-model="contractForm.base_rent" type="number" step="0.01" placeholder="الإيجار الأساسي"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <input v-model="contractForm.increase_rate" type="number" step="0.01" placeholder="نسبة الزيادة السنوية %"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <select v-model="contractForm.payment_period" class="border border-stone-200 rounded-xl px-3 py-2 text-sm">
            <option v-for="(label, val) in paymentPeriodLabels" :key="val" :value="val">{{ label }}</option>
          </select>
          <input v-model="contractForm.security_deposit" type="number" step="0.01" placeholder="التأمين"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <input v-model="contractForm.billing_day" type="number" min="1" max="28" placeholder="يوم الاستحقاق الشهري"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <input v-model="contractForm.grace_months" type="number" min="0" placeholder="أشهر السماح"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
        </template>
        <template v-else>
          <input v-model="contractForm.tenant_phone" type="text" placeholder="هاتف المستأجر"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <select v-model="contractForm.status" class="border border-stone-200 rounded-xl px-3 py-2 text-sm">
            <option v-for="(cfg, key) in statusConfig" :key="key" :value="key">{{ cfg.label }}</option>
          </select>
        </template>
        <textarea v-model="contractForm.notes" placeholder="ملاحظات" rows="2"
          class="border border-stone-200 rounded-xl px-3 py-2 text-sm sm:col-span-2" />
      </div>
      <template #footer>
        <AppButton :loading="savingContract" @click="saveContract">حفظ</AppButton>
      </template>
    </AppModal>

    <!-- Pay Payment Modal -->
    <AppModal :open="payModal.open" title="تسجيل دفعة إيجار" size="sm" @close="payModal.open = false">
      <div class="space-y-3">
        <input v-model="payForm.paid_amount" type="number" step="0.01" placeholder="المبلغ المدفوع"
          class="border border-stone-200 rounded-xl px-3 py-2 text-sm w-full" />
        <select v-model="payForm.payment_method" class="border border-stone-200 rounded-xl px-3 py-2 text-sm w-full">
          <option value="cash">كاش</option>
          <option value="card">بطاقة</option>
          <option value="bank_transfer">تحويل بنكي</option>
          <option value="other">أخرى</option>
        </select>
        <input v-model="payForm.receipt_number" type="text" placeholder="رقم الإيصال (اختياري)"
          class="border border-stone-200 rounded-xl px-3 py-2 text-sm w-full" />
      </div>
      <template #footer>
        <AppButton :loading="payingInProgress" @click="submitPayment">تأكيد الدفع</AppButton>
      </template>
    </AppModal>

    <!-- Cash Log Modal -->
    <AppModal :open="cashLogModal.open" title="حركة كاش جديدة" size="sm" @close="cashLogModal.open = false">
      <div class="space-y-3">
        <input v-model="cashLogForm.amount" type="number" step="0.01" placeholder="المبلغ"
          class="border border-stone-200 rounded-xl px-3 py-2 text-sm w-full" />
        <select v-model="cashLogForm.activity_type" class="border border-stone-200 rounded-xl px-3 py-2 text-sm w-full">
          <option v-for="(label, val) in activityTypeLabels" :key="val" :value="val">{{ label }}</option>
        </select>
        <input v-model="cashLogForm.reference" type="text" placeholder="مرجع (اختياري)"
          class="border border-stone-200 rounded-xl px-3 py-2 text-sm w-full" />
      </div>
      <template #footer>
        <AppButton :loading="savingCashLog" @click="saveCashLog">حفظ</AppButton>
      </template>
    </AppModal>
  </div>
</template>
