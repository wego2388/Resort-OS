<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@resort-os/core'
import { AppCard, AppBadge, AppButton, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const toast = useToast()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')
const tab = ref<'overview' | 'checks' | 'accounts' | 'cost-centers'>('overview')

interface Check { id: number; check_number: string; amount: number; drawer_name: string; due_date: string; status: string; bank_name: string }
interface Account { id: number; code: string; name: string; account_type: string; balance: number }
interface CostCenterLine { code: string; name: string; revenue: number; source: 'ledger' | 'direct' }

const checks = ref<Check[]>([])
const accounts = ref<Account[]>([])
const financeData = ref<{ total_revenue: number; total_expense: number; net_income: number } | null>(null)
const loading = ref(false)

// ── Cost Centers ─────────────────────────────────────────────────────
const today = new Date().toISOString().slice(0, 10)
const firstOfMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().slice(0, 10)
const ccDateFrom = ref(firstOfMonth)
const ccDateTo = ref(today)
const ccLines = ref<CostCenterLine[]>([])
const ccTotal = ref(0)

async function loadCostCenters() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/finance/cost-centers/report', {
      params: { branch_id: branchId, date_from: ccDateFrom.value, date_to: ccDateTo.value },
    })
    ccLines.value = res.data.lines ?? []
    ccTotal.value = res.data.total_revenue ?? 0
  } catch { toast.error('تعذّر تحميل مراكز التكلفة — حاول تاني') }
  finally { loading.value = false }
}

const checkStatusConfig: Record<string, { label: string; variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }> = {
  received:  { label: 'مستلم',   variant: 'neutral' },
  deposited: { label: 'مودع',    variant: 'info' },
  cleared:   { label: 'محصل',    variant: 'success' },
  bounced:   { label: 'مرتجع',   variant: 'danger' },
}

async function loadTab(t: typeof tab.value) {
  tab.value = t
  loading.value = true
  try {
    if (t === 'overview') {
      const res = await api.get('/api/v1/finance/reports/income-statement', {
        params: { branch_id: branchId, date_from: firstOfMonth, date_to: today },
      })
      financeData.value = {
        total_revenue: Number(res.data.total_revenue),
        total_expense: Number(res.data.total_expense),
        net_income: Number(res.data.net_income),
      }
    } else if (t === 'checks') {
      const res = await api.get('/api/v1/finance/checks', { params: { branch_id: branchId } })
      checks.value = res.data.checks ?? res.data.items ?? res.data
    } else if (t === 'accounts') {
      const res = await api.get('/api/v1/finance/accounts', { params: { branch_id: branchId } })
      accounts.value = res.data.accounts ?? res.data.items ?? res.data
    } else if (t === 'cost-centers') {
      await loadCostCenters()
    }
  } catch {
    const messages: Record<typeof tab.value, string> = {
      overview: 'تعذّر تحميل قائمة الدخل — حاول تاني',
      checks: 'تعذّر تحميل الشيكات — حاول تاني',
      accounts: 'تعذّر تحميل الحسابات — حاول تاني',
      'cost-centers': 'تعذّر تحميل مراكز التكلفة — حاول تاني',
    }
    toast.error(messages[t])
  } finally { loading.value = false }
}

async function advanceCheck(check: Check) {
  const flow: Record<string, string> = { received: 'deposited', deposited: 'cleared' }
  const next = flow[check.status]
  if (!next) return
  try {
    await api.patch(`/api/v1/finance/checks/${check.id}/status`, { to_status: next })
    check.status = next
  } catch { toast.error('تعذّر تحديث حالة الشيك — حاول تاني') }
}

onMounted(() => loadTab('overview'))
</script>

<template>
  <div dir="rtl">
    <h2 class="text-2xl font-black text-gray-900 mb-6">المالية</h2>

    <div class="flex gap-1 bg-stone-100 p-1 rounded-xl mb-6 w-fit">
      <button v-for="t in [{ val: 'overview', label: 'نظرة عامة' }, { val: 'checks', label: 'الشيكات' }, { val: 'accounts', label: 'الحسابات' }, { val: 'cost-centers', label: 'مراكز التكلفة' }]"
        :key="t.val" @click="loadTab(t.val as any)"
        :class="['px-4 py-2 rounded-lg text-sm font-semibold transition-all', tab === t.val ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-700']"
      >{{ t.label }}</button>
    </div>

    <!-- Overview -->
    <div v-if="tab === 'overview'">
      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <div v-else-if="financeData" class="grid grid-cols-1 md:grid-cols-3 gap-4">
        <AppCard padding="lg" class="text-center">
          <div class="text-sm text-gray-500 mb-2">إجمالي الإيرادات</div>
          <div class="text-3xl font-black text-green-600">{{ financeData.total_revenue.toLocaleString('ar-EG') }}</div>
          <div class="text-xs text-gray-400 mt-1">جنيه</div>
        </AppCard>
        <AppCard padding="lg" class="text-center">
          <div class="text-sm text-gray-500 mb-2">إجمالي المصروفات</div>
          <div class="text-3xl font-black text-red-500">{{ financeData.total_expense.toLocaleString('ar-EG') }}</div>
          <div class="text-xs text-gray-400 mt-1">جنيه</div>
        </AppCard>
        <AppCard padding="lg" class="text-center">
          <div class="text-sm text-gray-500 mb-2">صافي الربح</div>
          <div :class="['text-3xl font-black', financeData.net_income >= 0 ? 'text-blue-700' : 'text-red-500']">
            {{ financeData.net_income.toLocaleString('ar-EG') }}
          </div>
          <div class="text-xs text-gray-400 mt-1">جنيه</div>
        </AppCard>
      </div>
      <AppCard v-else padding="lg">
        <EmptyState icon="📊" title="لا تتوفر بيانات مالية حالياً" />
      </AppCard>
    </div>

    <!-- Checks -->
    <div v-if="tab === 'checks'">
      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <AppCard v-else padding="none">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50">
              <tr>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">رقم الشيك</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الساحب</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">المبلغ</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">تاريخ الاستحقاق</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الحالة</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">إجراء</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="check in checks" :key="check.id" class="border-t border-stone-100 hover:bg-stone-50">
                <td class="px-4 py-3 font-mono text-sm text-gray-900">{{ check.check_number }}</td>
                <td class="px-4 py-3 text-sm text-gray-700">{{ check.drawer_name }}</td>
                <td class="px-4 py-3 text-sm font-bold text-gray-900">{{ check.amount.toLocaleString('ar-EG') }} ج</td>
                <td class="px-4 py-3 text-sm text-gray-600">{{ new Date(check.due_date).toLocaleDateString('ar-EG') }}</td>
                <td class="px-4 py-3">
                  <AppBadge size="sm" :variant="checkStatusConfig[check.status]?.variant ?? 'neutral'">
                    {{ checkStatusConfig[check.status]?.label ?? check.status }}
                  </AppBadge>
                </td>
                <td class="px-4 py-3">
                  <AppButton v-if="check.status === 'received' || check.status === 'deposited'"
                    size="sm" @click="advanceCheck(check)"
                  >
                    {{ check.status === 'received' ? 'إيداع' : 'تحصيل' }}
                  </AppButton>
                </td>
              </tr>
              <tr v-if="checks.length === 0">
                <td colspan="6" class="px-4 py-8">
                  <EmptyState icon="🏦" title="لا توجد شيكات" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </div>

    <!-- Accounts -->
    <div v-if="tab === 'accounts'">
      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <AppCard v-else padding="none">
        <div class="overflow-x-auto">
          <table class="w-full">
            <thead class="bg-stone-50">
              <tr>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الكود</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">اسم الحساب</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">النوع</th>
                <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الرصيد</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="acc in accounts" :key="acc.id" class="border-t border-stone-100 hover:bg-stone-50">
                <td class="px-4 py-3 font-mono text-sm text-gray-600">{{ acc.code }}</td>
                <td class="px-4 py-3 text-sm font-medium text-gray-900">{{ acc.name }}</td>
                <td class="px-4 py-3 text-sm text-gray-600">{{ acc.account_type }}</td>
                <td class="px-4 py-3 text-sm font-bold" :class="acc.balance >= 0 ? 'text-green-600' : 'text-red-500'">
                  {{ acc.balance.toLocaleString('ar-EG') }} ج
                </td>
              </tr>
              <tr v-if="accounts.length === 0">
                <td colspan="4" class="px-4 py-8">
                  <EmptyState icon="📒" title="لا توجد حسابات" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </AppCard>
    </div>

    <!-- Cost Centers -->
    <div v-if="tab === 'cost-centers'">
      <div class="flex flex-wrap items-end gap-3 mb-4">
        <div>
          <label class="block text-xs text-gray-400 mb-1">من تاريخ</label>
          <input v-model="ccDateFrom" type="date" class="border border-stone-200 rounded-lg px-3 py-1.5 text-sm" />
        </div>
        <div>
          <label class="block text-xs text-gray-400 mb-1">إلى تاريخ</label>
          <input v-model="ccDateTo" type="date" class="border border-stone-200 rounded-lg px-3 py-1.5 text-sm" />
        </div>
        <AppButton size="sm" @click="loadCostCenters">تطبيق</AppButton>
      </div>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <template v-else>
        <AppCard padding="none" class="mb-4">
          <div class="overflow-x-auto">
            <table class="w-full">
              <thead class="bg-stone-50">
                <tr>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">مركز التكلفة</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الإيراد</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">المصدر</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="line in ccLines" :key="line.code" class="border-t border-stone-100 hover:bg-stone-50">
                  <td class="px-4 py-3 text-sm font-bold text-gray-900">{{ line.name }}</td>
                  <td class="px-4 py-3 text-sm font-bold text-green-600">{{ line.revenue.toLocaleString('ar-EG') }} ج</td>
                  <td class="px-4 py-3">
                    <span :class="['px-2 py-0.5 rounded-full text-[10px] font-bold',
                                   line.source === 'ledger' ? 'bg-blue-100 text-blue-700' : 'bg-amber-100 text-amber-700']">
                      {{ line.source === 'ledger' ? 'دفتر اليومية' : 'مباشر' }}
                    </span>
                  </td>
                </tr>
                <tr v-if="ccLines.length === 0">
                  <td colspan="3" class="px-4 py-8">
                    <EmptyState icon="📈" title="لا توجد بيانات في هذه الفترة" />
                  </td>
                </tr>
              </tbody>
              <tfoot v-if="ccLines.length">
                <tr class="border-t-2 border-stone-200 bg-stone-50">
                  <td class="px-4 py-3 text-sm font-black text-gray-900">الإجمالي</td>
                  <td class="px-4 py-3 text-sm font-black text-gray-900">{{ ccTotal.toLocaleString('ar-EG') }} ج</td>
                  <td></td>
                </tr>
              </tfoot>
            </table>
          </div>
        </AppCard>
        <p class="text-[11px] text-gray-400">
          "دفتر اليومية" = محسوب من القيود المحاسبية الفعلية. "مباشر" = محسوب من جداول العمليات
          لأن الموديول ده لسه ميرحّلش لدفتر اليومية.
        </p>
      </template>
    </div>
  </div>
</template>
