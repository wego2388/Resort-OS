<script setup lang="ts">
// نظرة عامة (إيراد/مصروف/صافي الشهر الحالي) — استُخرج من FinanceView.vue
// (تقسيم الملفات الكبيرة، 2026-09-07).
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

const toast = useToast()
const { t } = useI18n()
const { formatNumber } = useStaffFormat()
const branchId = computed(() => props.branchId)

const loading = ref(false)
const financeData = ref<{ total_revenue: number; total_expense: number; net_income: number } | null>(null)

const today = new Date().toISOString().slice(0, 10)
const firstOfMonth = new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().slice(0, 10)

async function loadOverview() {
  loading.value = true
  try {
    const res = await api.get(ENDPOINTS.finance.reportsIncomeStatement, {
      params: { branch_id: branchId.value, date_from: firstOfMonth, date_to: today },
    })
    financeData.value = {
      total_revenue: Number(res.data.total_revenue),
      total_expense: Number(res.data.total_expense),
      net_income: Number(res.data.net_income),
    }
  } catch {
    toast.error(t('backoffice.finance.loadIncomeStatementError'))
  } finally {
    loading.value = false
  }
}

onMounted(loadOverview)
</script>

<template>
  <div>
    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
    <div v-else-if="financeData" class="grid grid-cols-1 md:grid-cols-3 gap-4">
      <AppCard padding="lg" class="text-center">
        <div class="text-sm text-gray-500 dark:text-gray-400 mb-2">{{ t('backoffice.finance.totalRevenue') }}</div>
        <div class="text-3xl font-black text-green-600 dark:text-green-300">{{ formatNumber(financeData.total_revenue) }}</div>
        <div class="text-xs text-gray-400 dark:text-gray-400 mt-1">{{ t('backoffice.finance.egpWord') }}</div>
      </AppCard>
      <AppCard padding="lg" class="text-center">
        <div class="text-sm text-gray-500 dark:text-gray-400 mb-2">{{ t('backoffice.finance.totalExpense') }}</div>
        <div class="text-3xl font-black text-red-500">{{ formatNumber(financeData.total_expense) }}</div>
        <div class="text-xs text-gray-400 dark:text-gray-400 mt-1">{{ t('backoffice.finance.egpWord') }}</div>
      </AppCard>
      <AppCard padding="lg" class="text-center">
        <div class="text-sm text-gray-500 dark:text-gray-400 mb-2">{{ t('backoffice.finance.netIncome') }}</div>
        <div :class="['text-3xl font-black', financeData.net_income >= 0 ? 'text-blue-700 dark:text-blue-300' : 'text-red-500 dark:text-red-300']">
          {{ formatNumber(financeData.net_income) }}
        </div>
        <div class="text-xs text-gray-400 dark:text-gray-400 mt-1">{{ t('backoffice.finance.egpWord') }}</div>
      </AppCard>
    </div>
    <AppCard v-else padding="lg">
      <EmptyState icon="📊" :title="t('backoffice.finance.noFinancialData')" />
    </AppCard>
  </div>
</template>
