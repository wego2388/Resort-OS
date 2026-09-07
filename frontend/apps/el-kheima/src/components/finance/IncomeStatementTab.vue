<script setup lang="ts">
// قائمة الدخل التفصيلية (Income Statement) — استُخرج من FinanceView.vue
// (تقسيم الملفات الكبيرة، 2026-09-07).
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppButton, AppCard, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }

interface IncomeStatementLineRow { account_code: string; account_name: string; amount: number }
interface IncomeStatementData {
  date_from: string; date_to: string
  revenue_lines: IncomeStatementLineRow[]; expense_lines: IncomeStatementLineRow[]
  total_revenue: number; total_expense: number; net_income: number
}

const toast = useToast()
const { t } = useI18n()
const { formatNumber } = useStaffFormat()
const branchId = computed(() => props.branchId)

const today = new Date().toISOString().slice(0, 10)
const firstOfMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().slice(0, 10)
const isDateFrom = ref(firstOfMonth)
const isDateTo = ref(today)
const isData = ref<IncomeStatementData | null>(null)
const isDownloading = ref<'pdf' | 'excel' | null>(null)
const loading = ref(false)

async function loadIncomeStatementReport() {
  loading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.finance.reportsIncomeStatement, {
      params: { branch_id: branchId.value, date_from: isDateFrom.value, date_to: isDateTo.value },
    })
    isData.value = {
      date_from: data.date_from,
      date_to: data.date_to,
      revenue_lines: (data.revenue_lines ?? []).map((l: Record<string, unknown>) => ({ ...l, amount: Number(l.amount) } as IncomeStatementLineRow)),
      expense_lines: (data.expense_lines ?? []).map((l: Record<string, unknown>) => ({ ...l, amount: Number(l.amount) } as IncomeStatementLineRow)),
      total_revenue: Number(data.total_revenue),
      total_expense: Number(data.total_expense),
      net_income: Number(data.net_income),
    }
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.loadIncomeStatementError'))
  } finally {
    loading.value = false
  }
}

// نفس نمط HRView.vue's downloadBlobFile بالظبط — مفيش util مشترك للنمط ده
// جوه @resort-os/core/ui حاليًا، فكل شاشة بتكرره محليًا (قرار موثّق).
function downloadBlobFile(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 5000)
}

async function downloadIncomeStatement(fmt: 'pdf' | 'excel') {
  isDownloading.value = fmt
  try {
    const url = fmt === 'pdf' ? ENDPOINTS.finance.reportsIncomeStatementPdf : ENDPOINTS.finance.reportsIncomeStatementExcel
    const res = await api.get(url, {
      params: { branch_id: branchId.value, date_from: isDateFrom.value, date_to: isDateTo.value },
      responseType: 'blob',
    })
    downloadBlobFile(res.data, `income-statement-${isDateFrom.value}_${isDateTo.value}.${fmt === 'pdf' ? 'pdf' : 'xlsx'}`)
  } catch {
    toast.error(t('backoffice.finance.reportDownloadError'))
  } finally {
    isDownloading.value = null
  }
}

onMounted(loadIncomeStatementReport)
</script>

<template>
  <div>
    <div class="flex flex-wrap items-end gap-3 mb-4">
      <div>
        <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.fromDate') }}</label>
        <input v-model="isDateFrom" type="date" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm" />
      </div>
      <div>
        <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.toDate') }}</label>
        <input v-model="isDateTo" type="date" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm" />
      </div>
      <AppButton size="sm" @click="loadIncomeStatementReport">{{ t('backoffice.finance.apply') }}</AppButton>
      <div class="flex gap-2 ms-auto">
        <AppButton size="sm" variant="outline" :loading="isDownloading === 'pdf'" @click="downloadIncomeStatement('pdf')">📄 PDF</AppButton>
        <AppButton size="sm" variant="outline" :loading="isDownloading === 'excel'" @click="downloadIncomeStatement('excel')">📊 Excel</AppButton>
      </div>
    </div>

    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
    <template v-else-if="isData">
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <AppCard padding="none">
          <div class="px-4 py-3 border-b border-stone-100 dark:border-border/50 font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.revenue') }}</div>
          <div class="overflow-x-auto">
            <table class="w-full min-w-[320px]">
              <tbody>
                <tr v-for="l in isData.revenue_lines" :key="l.account_code" class="border-t border-stone-100 dark:border-border/50">
                  <td class="px-4 py-2 text-xs font-mono text-gray-500 dark:text-gray-400">{{ l.account_code }}</td>
                  <td class="px-4 py-2 text-sm text-gray-900 dark:text-gray-100">{{ l.account_name }}</td>
                  <td class="px-4 py-2 text-sm font-bold text-green-700 dark:text-green-300">{{ formatNumber(l.amount) }} {{ t('backoffice.finance.egp') }}</td>
                </tr>
                <tr v-if="isData.revenue_lines.length === 0">
                  <td colspan="3" class="px-4 py-6"><EmptyState icon="💰" :title="t('backoffice.finance.noDataThisPeriod')" /></td>
                </tr>
              </tbody>
              <tfoot v-if="isData.revenue_lines.length">
                <tr class="border-t-2 border-stone-200 dark:border-border bg-stone-50 dark:bg-gray-800/60">
                  <td colspan="2" class="px-4 py-3 text-sm font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.totalRevenue') }}</td>
                  <td class="px-4 py-3 text-sm font-black text-green-700 dark:text-green-300">{{ formatNumber(isData.total_revenue) }} {{ t('backoffice.finance.egp') }}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </AppCard>

        <AppCard padding="none">
          <div class="px-4 py-3 border-b border-stone-100 dark:border-border/50 font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.expense') }}</div>
          <div class="overflow-x-auto">
            <table class="w-full min-w-[320px]">
              <tbody>
                <tr v-for="l in isData.expense_lines" :key="l.account_code" class="border-t border-stone-100 dark:border-border/50">
                  <td class="px-4 py-2 text-xs font-mono text-gray-500 dark:text-gray-400">{{ l.account_code }}</td>
                  <td class="px-4 py-2 text-sm text-gray-900 dark:text-gray-100">{{ l.account_name }}</td>
                  <td class="px-4 py-2 text-sm font-bold text-red-700 dark:text-red-300">{{ formatNumber(l.amount) }} {{ t('backoffice.finance.egp') }}</td>
                </tr>
                <tr v-if="isData.expense_lines.length === 0">
                  <td colspan="3" class="px-4 py-6"><EmptyState icon="🧾" :title="t('backoffice.finance.noDataThisPeriod')" /></td>
                </tr>
              </tbody>
              <tfoot v-if="isData.expense_lines.length">
                <tr class="border-t-2 border-stone-200 dark:border-border bg-stone-50 dark:bg-gray-800/60">
                  <td colspan="2" class="px-4 py-3 text-sm font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.totalExpense') }}</td>
                  <td class="px-4 py-3 text-sm font-black text-red-700 dark:text-red-300">{{ formatNumber(isData.total_expense) }} {{ t('backoffice.finance.egp') }}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </AppCard>
      </div>
      <AppCard padding="md">
        <div class="flex items-center justify-between">
          <span class="font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.netIncome') }}</span>
          <span class="text-lg font-black" :class="isData.net_income >= 0 ? 'text-green-700 dark:text-green-300' : 'text-red-600 dark:text-red-300'">
            {{ formatNumber(isData.net_income) }} {{ t('backoffice.finance.egp') }}
          </span>
        </div>
      </AppCard>
    </template>
    <AppCard v-else padding="lg">
      <EmptyState icon="📉" :title="t('backoffice.finance.noDataThisPeriod')" />
    </AppCard>
  </div>
</template>
