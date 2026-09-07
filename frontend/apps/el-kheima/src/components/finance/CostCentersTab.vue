<script setup lang="ts">
// تقرير مراكز التكلفة — استُخرج من FinanceView.vue (تقسيم الملفات الكبيرة،
// 2026-09-07).
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppButton, AppCard, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

interface CostCenterLine { code: string; name: string; revenue: number; expense: number; net: number; source: 'ledger' | 'direct' }

const toast = useToast()
const { t } = useI18n()
const { formatNumber } = useStaffFormat()
const branchId = computed(() => props.branchId)

const today = new Date().toISOString().slice(0, 10)
const firstOfMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().slice(0, 10)
const ccDateFrom = ref(firstOfMonth)
const ccDateTo = ref(today)
const ccLines = ref<CostCenterLine[]>([])
const ccTotalRevenue = ref(0)
const ccTotalExpense = ref(0)
const ccTotalNet = ref(0)
const loading = ref(false)

async function loadCostCenters() {
  loading.value = true
  try {
    const res = await api.get(ENDPOINTS.finance.costCenterReport, {
      params: { branch_id: branchId.value, date_from: ccDateFrom.value, date_to: ccDateTo.value },
    })
    ccLines.value = res.data.lines ?? []
    ccTotalRevenue.value = res.data.total_revenue ?? 0
    ccTotalExpense.value = res.data.total_expense ?? 0
    ccTotalNet.value = res.data.total_net ?? 0
  } catch { toast.error(t('backoffice.finance.loadCostCentersError')) }
  finally { loading.value = false }
}

onMounted(loadCostCenters)
</script>

<template>
  <div>
    <div class="flex flex-wrap items-end gap-3 mb-4">
      <div>
        <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.fromDate') }}</label>
        <input v-model="ccDateFrom" type="date" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm" />
      </div>
      <div>
        <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.toDate') }}</label>
        <input v-model="ccDateTo" type="date" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm" />
      </div>
      <AppButton size="sm" @click="loadCostCenters">{{ t('backoffice.finance.apply') }}</AppButton>
    </div>

    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
    <template v-else>
      <AppCard padding="none" class="mb-4">
        <div class="overflow-x-auto">
          <table class="w-full min-w-[600px]">
            <thead class="bg-stone-50 dark:bg-gray-800/60">
              <tr>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.costCenter') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.revenue') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.expense') }}</th>
                <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.net') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="line in ccLines" :key="line.code" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3 text-sm font-bold text-gray-900 dark:text-gray-100">{{ line.name }}</td>
                <td class="px-4 py-3 text-sm font-bold text-green-600 dark:text-green-300">{{ formatNumber(line.revenue) }} {{ t('backoffice.finance.egp') }}</td>
                <td class="px-4 py-3 text-sm font-bold text-red-600 dark:text-red-300">{{ formatNumber(line.expense) }} {{ t('backoffice.finance.egp') }}</td>
                <td class="px-4 py-3 text-sm font-bold" :class="line.net >= 0 ? 'text-gray-900 dark:text-gray-100' : 'text-red-700'">
                  {{ formatNumber(line.net) }} {{ t('backoffice.finance.egp') }}
                </td>
              </tr>
              <tr v-if="ccLines.length === 0">
                <td colspan="4" class="px-4 py-8">
                  <EmptyState icon="📈" :title="t('backoffice.finance.noDataThisPeriod')" />
                </td>
              </tr>
            </tbody>
            <tfoot v-if="ccLines.length">
              <tr class="border-t-2 border-stone-200 dark:border-border bg-stone-50 dark:bg-gray-800/60">
                <td class="px-4 py-3 text-sm font-black text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.total') }}</td>
                <td class="px-4 py-3 text-sm font-black text-green-700 dark:text-green-300">{{ formatNumber(ccTotalRevenue) }} {{ t('backoffice.finance.egp') }}</td>
                <td class="px-4 py-3 text-sm font-black text-red-700 dark:text-red-300">{{ formatNumber(ccTotalExpense) }} {{ t('backoffice.finance.egp') }}</td>
                <td class="px-4 py-3 text-sm font-black text-gray-900 dark:text-gray-100">{{ formatNumber(ccTotalNet) }} {{ t('backoffice.finance.egp') }}</td>
              </tr>
            </tfoot>
          </table>
        </div>
      </AppCard>
      <p class="text-[11px] text-gray-400 dark:text-gray-400">
        {{ t('backoffice.finance.costCenterHint') }}
      </p>
    </template>
  </div>
</template>
