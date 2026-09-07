<script setup lang="ts">
// الفترات المحاسبية + الإقفال الشهري/السنوي — استُخرج من FinanceView.vue
// (تقسيم الملفات الكبيرة، 2026-09-07).
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS, useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppButton, AppCard, AppBadge, AppSpinner, useToast, useConfirm } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface PeriodRow { id: number; year: number; month: number; status: string; closed_at: string | null }

const toast = useToast()
const { confirm } = useConfirm()
const { t } = useI18n()
const { formatNumber, formatDate: fmtDateFn } = useStaffFormat()
const auth = useAuthStore()
const branchId = computed(() => props.branchId)

const periodsYear = ref(new Date().getFullYear())
const periodsRaw = ref<PeriodRow[]>([])
const periodsLoading = ref(false)
const closingMonthKey = ref<number | null>(null)
const closingYear = ref(false)
const yearCloseResult = ref<{ journal_entry_id: number; net_income: number; closed_at: string } | null>(null)

const periodsGrid = computed(() => {
  return Array.from({ length: 12 }, (_, i) => {
    const month = i + 1
    const row = periodsRaw.value.find(p => p.month === month)
    return { month, status: row?.status ?? 'open', closedAt: row?.closed_at ?? null }
  })
})
const allMonthsClosed = computed(() => periodsGrid.value.every(m => m.status === 'closed' || m.status === 'locked'))
const monthNames = computed(() => Array.from({ length: 12 }, (_, i) =>
  fmtDateFn(new Date(2000, i, 1), { month: 'long' } as Intl.DateTimeFormatOptions)))

async function loadPeriods() {
  periodsLoading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.finance.periods, { params: { branch_id: branchId.value, page: 1, size: 200 } })
    periodsRaw.value = ((data.items ?? []) as PeriodRow[]).filter(p => p.year === periodsYear.value)
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.periods.loadError'))
  } finally {
    periodsLoading.value = false
  }
}
async function closeMonth(month: number) {
  const ok = await confirm({
    message: t('backoffice.finance.periods.confirmCloseMonth', { month: monthNames.value[month - 1], year: periodsYear.value }),
    danger: true,
  })
  if (!ok) return
  closingMonthKey.value = month
  try {
    await api.post(ENDPOINTS.finance.periodClose(periodsYear.value, month), { branch_id: branchId.value })
    toast.success(t('backoffice.finance.periods.closeMonthSuccess'))
    await loadPeriods()
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.periods.closeMonthError'))
  } finally {
    closingMonthKey.value = null
  }
}
async function closeYear() {
  const ok = await confirm({
    message: t('backoffice.finance.periods.confirmCloseYear', { year: periodsYear.value }),
    danger: true, confirmText: t('backoffice.finance.periods.closeYearConfirm'), cancelText: t('backoffice.finance.cancel'),
  })
  if (!ok) return
  closingYear.value = true
  try {
    const { data } = await api.post(ENDPOINTS.finance.closeYear(periodsYear.value), null, { params: { branch_id: branchId.value } })
    yearCloseResult.value = { journal_entry_id: data.journal_entry_id, net_income: Number(data.net_income), closed_at: data.closed_at }
    toast.success(t('backoffice.finance.periods.closeYearSuccess'))
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.periods.closeYearError'))
  } finally {
    closingYear.value = false
  }
}

onMounted(loadPeriods)
</script>

<template>
  <div>
    <div class="flex flex-wrap items-end gap-3 mb-4">
      <div>
        <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.year') }}</label>
        <input v-model.number="periodsYear" type="number" min="2020" max="2100"
          class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm w-28" />
      </div>
      <AppButton size="sm" @click="loadPeriods">{{ t('backoffice.finance.apply') }}</AppButton>
      <AppButton
        v-if="auth.hasRole('admin')"
        size="sm" variant="danger" class="ms-auto"
        :disabled="!allMonthsClosed" :loading="closingYear"
        @click="closeYear"
      >🔒 {{ t('backoffice.finance.periods.closeYear') }}</AppButton>
    </div>

    <p v-if="auth.hasRole('admin') && !allMonthsClosed" class="text-xs text-amber-600 dark:text-amber-400 mb-3">
      {{ t('backoffice.finance.periods.closeYearHint') }}
    </p>

    <AppCard v-if="yearCloseResult" padding="md" class="mb-4 border-2 border-green-500/40">
      <div class="flex items-center gap-2 text-green-700 dark:text-green-300 font-bold mb-1">✅ {{ t('backoffice.finance.periods.closeYearSuccess') }}</div>
      <div class="text-sm text-gray-600 dark:text-gray-300">
        {{ t('backoffice.finance.periods.yearClosedNetIncome') }}: <strong>{{ formatNumber(yearCloseResult.net_income) }} {{ t('backoffice.finance.egp') }}</strong>
        — {{ t('backoffice.finance.ledger.reference') }} #{{ yearCloseResult.journal_entry_id }}
      </div>
    </AppCard>

    <div v-if="periodsLoading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
    <div v-else class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
      <AppCard v-for="m in periodsGrid" :key="m.month" padding="md">
        <div class="flex items-center justify-between mb-2">
          <span class="font-bold text-gray-900 dark:text-gray-100">{{ monthNames[m.month - 1] }}</span>
          <AppBadge size="sm" :variant="m.status === 'open' ? 'warning' : 'success'">
            {{ m.status === 'open' ? t('backoffice.finance.periods.open') : t('backoffice.finance.periods.closed') }}
          </AppBadge>
        </div>
        <AppButton
          v-if="m.status === 'open'"
          size="sm" variant="outline" class="w-full"
          :loading="closingMonthKey === m.month"
          @click="closeMonth(m.month)"
        >{{ t('backoffice.finance.periods.closeMonth') }}</AppButton>
        <p v-else class="text-xs text-gray-400 dark:text-gray-400">{{ fmtDateFn(m.closedAt ?? '') }}</p>
      </AppCard>
    </div>
  </div>
</template>
