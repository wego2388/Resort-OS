<script setup lang="ts">
// ميزان المراجعة (Trial Balance) — استُخرج من FinanceView.vue (تقسيم
// الملفات الكبيرة، 2026-09-07).
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppButton, AppCard, AppBadge, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }

interface TrialBalanceLineRow { account_code: string; account_name: string; account_type: string; debit: number; credit: number }
interface TrialBalanceData {
  as_of: string; lines: TrialBalanceLineRow[]
  total_debit: number; total_credit: number; is_balanced: boolean; grouped_by_parent: boolean
}

const toast = useToast()
const { t } = useI18n()
const { formatNumber } = useStaffFormat()
const branchId = computed(() => props.branchId)

const today = new Date().toISOString().slice(0, 10)
const tbAsOf = ref(today)
const tbGroupByParent = ref(false)
const tbData = ref<TrialBalanceData | null>(null)
const tbDownloading = ref<'pdf' | 'excel' | null>(null)
const loading = ref(false)

async function loadTrialBalance() {
  loading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.finance.reportsTrialBalance, {
      params: { branch_id: branchId.value, as_of: tbAsOf.value, group_by_parent: tbGroupByParent.value },
    })
    tbData.value = {
      as_of: data.as_of,
      lines: (data.lines ?? []).map((l: Record<string, unknown>) => ({ ...l, debit: Number(l.debit), credit: Number(l.credit) } as TrialBalanceLineRow)),
      total_debit: Number(data.total_debit),
      total_credit: Number(data.total_credit),
      is_balanced: Boolean(data.is_balanced),
      grouped_by_parent: Boolean(data.grouped_by_parent),
    }
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.trialBalance.loadError'))
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

async function downloadTrialBalance(fmt: 'pdf' | 'excel') {
  tbDownloading.value = fmt
  try {
    const url = fmt === 'pdf' ? ENDPOINTS.finance.reportsTrialBalancePdf : ENDPOINTS.finance.reportsTrialBalanceExcel
    const res = await api.get(url, {
      params: { branch_id: branchId.value, as_of: tbAsOf.value, group_by_parent: tbGroupByParent.value },
      responseType: 'blob',
    })
    downloadBlobFile(res.data, `trial-balance-${tbAsOf.value}.${fmt === 'pdf' ? 'pdf' : 'xlsx'}`)
  } catch {
    toast.error(t('backoffice.finance.reportDownloadError'))
  } finally {
    tbDownloading.value = null
  }
}

onMounted(loadTrialBalance)
</script>

<template>
  <div>
    <div class="flex flex-wrap items-end gap-3 mb-4">
      <div>
        <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.asOfDate') }}</label>
        <input v-model="tbAsOf" type="date" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm" />
      </div>
      <label class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300 pb-1.5">
        <input v-model="tbGroupByParent" type="checkbox" class="rounded" />
        {{ t('backoffice.finance.trialBalance.groupByParent') }}
      </label>
      <AppButton size="sm" @click="loadTrialBalance">{{ t('backoffice.finance.apply') }}</AppButton>
      <AppBadge v-if="tbData" size="sm" :variant="tbData.is_balanced ? 'success' : 'danger'">
        {{ tbData.is_balanced ? `✅ ${t('backoffice.finance.balanced')}` : `⚠️ ${t('backoffice.finance.notBalanced')}` }}
      </AppBadge>
      <div class="flex gap-2 ms-auto">
        <AppButton size="sm" variant="outline" :loading="tbDownloading === 'pdf'" @click="downloadTrialBalance('pdf')">📄 PDF</AppButton>
        <AppButton size="sm" variant="outline" :loading="tbDownloading === 'excel'" @click="downloadTrialBalance('excel')">📊 Excel</AppButton>
      </div>
    </div>

    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
    <AppCard v-else-if="tbData" padding="none">
      <div class="overflow-x-auto">
        <table class="w-full min-w-[600px]">
          <thead class="bg-stone-50 dark:bg-gray-800/60">
            <tr>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.code') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.accountName') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.type') }}</th>
              <th class="px-4 py-3 text-end text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.ledger.debit') }}</th>
              <th class="px-4 py-3 text-end text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.ledger.credit') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="l in tbData.lines" :key="l.account_code" class="border-t border-stone-100 dark:border-border/50">
              <td class="px-4 py-3 font-mono text-sm text-gray-600 dark:text-gray-400">{{ l.account_code }}</td>
              <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100">{{ l.account_name }}</td>
              <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ l.account_type }}</td>
              <td class="px-4 py-3 text-sm text-end font-semibold text-green-600 dark:text-green-300">{{ l.debit ? formatNumber(l.debit) : '—' }}</td>
              <td class="px-4 py-3 text-sm text-end font-semibold text-red-600 dark:text-red-300">{{ l.credit ? formatNumber(l.credit) : '—' }}</td>
            </tr>
            <tr v-if="tbData.lines.length === 0">
              <td colspan="5" class="px-4 py-8"><EmptyState icon="📒" :title="t('backoffice.finance.noAccounts')" /></td>
            </tr>
          </tbody>
          <tfoot v-if="tbData.lines.length">
            <tr class="border-t-2 border-stone-200 dark:border-border bg-stone-50 dark:bg-gray-800/60">
              <td colspan="3" class="px-4 py-3 text-sm font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.total') }}</td>
              <td class="px-4 py-3 text-sm text-end font-black text-green-700 dark:text-green-300">{{ formatNumber(tbData.total_debit) }}</td>
              <td class="px-4 py-3 text-sm text-end font-black text-red-700 dark:text-red-300">{{ formatNumber(tbData.total_credit) }}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </AppCard>
    <AppCard v-else padding="lg">
      <EmptyState icon="⚖️" :title="t('backoffice.finance.noBalanceSheetData')" />
    </AppCard>
  </div>
</template>
