<script setup lang="ts">
// الميزانية العمومية — استُخرج من FinanceView.vue (تقسيم الملفات الكبيرة،
// 2026-09-07). ميزان المراجعة/قائمة الدخل (أرصدة journal_lines الفعلية لكل
// حساب حتى as_of)، مش حساب موازٍ منفصل. راجع finance.services.get_balance_sheet.
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppButton, AppCard, AppBadge, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }

interface BalanceSheetLine { account_code: string; account_name: string; amount: number }
interface BalanceSheetData {
  as_of: string
  asset_lines: BalanceSheetLine[]; liability_lines: BalanceSheetLine[]; equity_lines: BalanceSheetLine[]
  retained_earnings: number
  total_assets: number; total_liabilities: number; total_equity: number; total_liabilities_and_equity: number
  is_balanced: boolean
}

const toast = useToast()
const { t } = useI18n()
const { formatNumber } = useStaffFormat()
const branchId = computed(() => props.branchId)

const today = new Date().toISOString().slice(0, 10)
const bsAsOf = ref(today)
const bsData = ref<BalanceSheetData | null>(null)
const loading = ref(false)
const bsDownloading = ref<'pdf' | 'excel' | null>(null)

async function loadBalanceSheet() {
  loading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.finance.reportsBalanceSheet, {
      params: { branch_id: branchId.value, as_of: bsAsOf.value },
    })
    const toLines = (lines: { amount?: unknown; [k: string]: unknown }[]): BalanceSheetLine[] =>
      (lines ?? []).map((l) => ({ ...l, amount: Number(l.amount) } as BalanceSheetLine))
    bsData.value = {
      as_of: data.as_of,
      asset_lines: toLines(data.asset_lines),
      liability_lines: toLines(data.liability_lines),
      equity_lines: toLines(data.equity_lines),
      retained_earnings: Number(data.retained_earnings),
      total_assets: Number(data.total_assets),
      total_liabilities: Number(data.total_liabilities),
      total_equity: Number(data.total_equity),
      total_liabilities_and_equity: Number(data.total_liabilities_and_equity),
      is_balanced: Boolean(data.is_balanced),
    }
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.loadBalanceSheetError'))
  } finally {
    loading.value = false
  }
}

// نفس نمط HRView.vue's downloadBlobFile بالظبط (blob response + object URL
// + تنزيل تلقائي + revoke بعد 5 ثواني) — مفيش util مشترك للنمط ده جوه
// @resort-os/core/ui حاليًا، فكل شاشة بتكرره محليًا (نفس القرار الموثّق هناك).
function downloadBlobFile(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 5000)
}

async function downloadBalanceSheet(fmt: 'pdf' | 'excel') {
  bsDownloading.value = fmt
  try {
    const url = fmt === 'pdf' ? ENDPOINTS.finance.reportsBalanceSheetPdf : ENDPOINTS.finance.reportsBalanceSheetExcel
    const res = await api.get(url, { params: { branch_id: branchId.value, as_of: bsAsOf.value }, responseType: 'blob' })
    downloadBlobFile(res.data, `balance-sheet-${bsAsOf.value}.${fmt === 'pdf' ? 'pdf' : 'xlsx'}`)
  } catch {
    toast.error(t('backoffice.finance.reportDownloadError'))
  } finally {
    bsDownloading.value = null
  }
}

onMounted(loadBalanceSheet)
</script>

<template>
  <div>
    <div class="flex flex-wrap items-end gap-3 mb-4">
      <div>
        <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.asOfDate') }}</label>
        <input v-model="bsAsOf" type="date" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm" />
      </div>
      <AppButton size="sm" @click="loadBalanceSheet">{{ t('backoffice.finance.apply') }}</AppButton>
      <AppBadge v-if="bsData" size="sm" :variant="bsData.is_balanced ? 'success' : 'danger'">
        {{ bsData.is_balanced ? `✅ ${t('backoffice.finance.balanced')}` : `⚠️ ${t('backoffice.finance.notBalanced')}` }}
      </AppBadge>
      <div class="flex gap-2 ms-auto">
        <AppButton size="sm" variant="outline" :loading="bsDownloading === 'pdf'" @click="downloadBalanceSheet('pdf')">📄 PDF</AppButton>
        <AppButton size="sm" variant="outline" :loading="bsDownloading === 'excel'" @click="downloadBalanceSheet('excel')">📊 Excel</AppButton>
      </div>
    </div>

    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
    <template v-else-if="bsData">
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <AppCard padding="none">
          <div class="px-4 py-3 border-b border-stone-100 dark:border-border/50 font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.assets') }}</div>
          <div class="overflow-x-auto">
            <table class="w-full min-w-[380px]">
              <tbody>
                <tr v-for="l in bsData.asset_lines" :key="l.account_code" class="border-t border-stone-100 dark:border-border/50">
                  <td class="px-4 py-2 text-xs font-mono text-gray-500 dark:text-gray-400">{{ l.account_code }}</td>
                  <td class="px-4 py-2 text-sm text-gray-900 dark:text-gray-100">{{ l.account_name }}</td>
                  <td class="px-4 py-2 text-sm font-bold text-gray-900 dark:text-gray-100">{{ formatNumber(l.amount) }} {{ t('backoffice.finance.egp') }}</td>
                </tr>
                <tr v-if="bsData.asset_lines.length === 0">
                  <td colspan="3" class="px-4 py-6"><EmptyState icon="🏦" :title="t('backoffice.finance.noAssetsToDate')" /></td>
                </tr>
              </tbody>
              <tfoot v-if="bsData.asset_lines.length">
                <tr class="border-t-2 border-stone-200 dark:border-border bg-stone-50 dark:bg-gray-800/60">
                  <td colspan="2" class="px-4 py-3 text-sm font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.totalAssets') }}</td>
                  <td class="px-4 py-3 text-sm font-black text-green-700 dark:text-green-300">{{ formatNumber(bsData.total_assets) }} {{ t('backoffice.finance.egp') }}</td>
                </tr>
              </tfoot>
            </table>
          </div>
        </AppCard>

        <div class="space-y-4">
          <AppCard padding="none">
            <div class="px-4 py-3 border-b border-stone-100 dark:border-border/50 font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.liabilities') }}</div>
            <div class="overflow-x-auto">
              <table class="w-full min-w-[380px]">
                <tbody>
                  <tr v-for="l in bsData.liability_lines" :key="l.account_code" class="border-t border-stone-100 dark:border-border/50">
                    <td class="px-4 py-2 text-xs font-mono text-gray-500 dark:text-gray-400">{{ l.account_code }}</td>
                    <td class="px-4 py-2 text-sm text-gray-900 dark:text-gray-100">{{ l.account_name }}</td>
                    <td class="px-4 py-2 text-sm font-bold text-gray-900 dark:text-gray-100">{{ formatNumber(l.amount) }} {{ t('backoffice.finance.egp') }}</td>
                  </tr>
                  <tr v-if="bsData.liability_lines.length === 0">
                    <td colspan="3" class="px-4 py-6"><EmptyState icon="📋" :title="t('backoffice.finance.noLiabilitiesToDate')" /></td>
                  </tr>
                </tbody>
                <tfoot v-if="bsData.liability_lines.length">
                  <tr class="border-t-2 border-stone-200 dark:border-border bg-stone-50 dark:bg-gray-800/60">
                    <td colspan="2" class="px-4 py-3 text-sm font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.totalLiabilities') }}</td>
                    <td class="px-4 py-3 text-sm font-black text-red-700 dark:text-red-300">{{ formatNumber(bsData.total_liabilities) }} {{ t('backoffice.finance.egp') }}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </AppCard>

          <AppCard padding="none">
            <div class="px-4 py-3 border-b border-stone-100 dark:border-border/50 font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.equity') }}</div>
            <div class="overflow-x-auto">
              <table class="w-full min-w-[380px]">
                <tbody>
                  <tr v-for="l in bsData.equity_lines" :key="l.account_code" class="border-t border-stone-100 dark:border-border/50">
                    <td class="px-4 py-2 text-xs font-mono text-gray-500 dark:text-gray-400">{{ l.account_code }}</td>
                    <td class="px-4 py-2 text-sm text-gray-900 dark:text-gray-100">{{ l.account_name }}</td>
                    <td class="px-4 py-2 text-sm font-bold text-gray-900 dark:text-gray-100">{{ formatNumber(l.amount) }} {{ t('backoffice.finance.egp') }}</td>
                  </tr>
                  <tr class="border-t border-stone-100 dark:border-border/50">
                    <td colspan="2" class="px-4 py-2 text-sm text-gray-700 dark:text-gray-300">{{ t('backoffice.finance.retainedEarnings') }}</td>
                    <td class="px-4 py-2 text-sm font-bold text-gray-900 dark:text-gray-100">{{ formatNumber(bsData.retained_earnings) }} {{ t('backoffice.finance.egp') }}</td>
                  </tr>
                </tbody>
                <tfoot>
                  <tr class="border-t-2 border-stone-200 dark:border-border bg-stone-50 dark:bg-gray-800/60">
                    <td colspan="2" class="px-4 py-3 text-sm font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.totalLiabilitiesAndEquity') }}</td>
                    <td class="px-4 py-3 text-sm font-black text-blue-700 dark:text-blue-300">{{ formatNumber(bsData.total_liabilities_and_equity) }} {{ t('backoffice.finance.egp') }}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </AppCard>
        </div>
      </div>
      <p class="text-[11px] text-gray-400 dark:text-gray-400">
        {{ t('backoffice.finance.balanceSheetHint') }}
      </p>
    </template>
    <AppCard v-else padding="lg">
      <EmptyState icon="⚖️" :title="t('backoffice.finance.noBalanceSheetData')" />
    </AppCard>
  </div>
</template>
