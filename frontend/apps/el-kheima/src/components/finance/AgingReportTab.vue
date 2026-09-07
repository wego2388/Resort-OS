<script setup lang="ts">
// تقرير أعمار الديون (AR/AP aging) — استُخرج من FinanceView.vue (تقسيم
// الملفات الكبيرة، 2026-09-07). تاب read-only معزول بالكامل — بياخد
// branchId كـprop (بدل ما يستورد auth store لوحده) عشان يفضل مصدر الحقيقة
// الوحيد لفرع الجلسة النشط هو الأب، مطابقةً لباقي التابات.
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppButton, AppCard, AppBadge, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }

interface AgingBucketRow { label: string; count: number; amount: number }
interface ReceivableAgingRow { folio_id: number; guest_name: string; check_in: string; days_outstanding: number; balance_due: number; bucket: string }
interface PayableAgingRow { source_type: string; source_id: number; reference: string; counterparty: string; due_date: string; days_outstanding: number; remaining: number; bucket: string }
interface AgingData {
  as_of: string
  receivables: ReceivableAgingRow[]; receivables_total: number; receivables_buckets: AgingBucketRow[]
  payables: PayableAgingRow[]; payables_total: number; payables_buckets: AgingBucketRow[]
}

const toast = useToast()
const { t } = useI18n()
const { formatNumber } = useStaffFormat()

const today = new Date().toISOString().slice(0, 10)
const agingAsOf = ref(today)
const agingData = ref<AgingData | null>(null)
const loading = ref(false)
const branchId = computed(() => props.branchId)

async function loadAging() {
  loading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.finance.reportsAging, { params: { branch_id: branchId.value, as_of: agingAsOf.value } })
    agingData.value = {
      as_of: data.as_of,
      receivables: (data.receivables ?? []).map((l: Record<string, unknown>) => ({ ...l, balance_due: Number(l.balance_due) } as ReceivableAgingRow)),
      receivables_total: Number(data.receivables_total),
      receivables_buckets: (data.receivables_buckets ?? []).map((b: Record<string, unknown>) => ({ ...b, amount: Number(b.amount) } as AgingBucketRow)),
      payables: (data.payables ?? []).map((l: Record<string, unknown>) => ({ ...l, remaining: Number(l.remaining) } as PayableAgingRow)),
      payables_total: Number(data.payables_total),
      payables_buckets: (data.payables_buckets ?? []).map((b: Record<string, unknown>) => ({ ...b, amount: Number(b.amount) } as AgingBucketRow)),
    }
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.aging.loadError'))
  } finally {
    loading.value = false
  }
}
// تدرّج لوني حسب عمر الدين — بادج أخضر (0-30) → كهرماني (31-60) → برتقالي
// (61-90) → أحمر (90+، متأخر بشكل جدّي يستاهل متابعة فورية).
function agingBucketVariant(bucket: string): 'success' | 'warning' | 'danger' | 'neutral' {
  if (bucket === '0-30') return 'success'
  if (bucket === '31-60') return 'warning'
  if (bucket === '61-90') return 'danger'
  return 'danger'
}

onMounted(loadAging)
</script>

<template>
  <div>
    <div class="flex flex-wrap items-end gap-3 mb-4">
      <div>
        <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.asOfDate') }}</label>
        <input v-model="agingAsOf" type="date" class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm" />
      </div>
      <AppButton size="sm" @click="loadAging">{{ t('backoffice.finance.apply') }}</AppButton>
    </div>

    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
    <template v-else-if="agingData">
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <AppCard padding="none">
          <div class="px-4 py-3 border-b border-stone-100 dark:border-border/50 flex items-center justify-between">
            <span class="font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.aging.receivables') }}</span>
            <span class="text-sm font-bold text-green-700 dark:text-green-300">{{ formatNumber(agingData.receivables_total) }} {{ t('backoffice.finance.egp') }}</span>
          </div>
          <div class="flex flex-wrap gap-2 px-4 py-2 border-b border-stone-100 dark:border-border/50">
            <AppBadge v-for="b in agingData.receivables_buckets" :key="b.label" size="sm" :variant="agingBucketVariant(b.label)">
              {{ b.label }} — {{ b.count }} ({{ formatNumber(b.amount) }})
            </AppBadge>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full min-w-[420px]">
              <thead class="bg-stone-50 dark:bg-gray-800/60">
                <tr>
                  <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.aging.guest') }}</th>
                  <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.aging.days') }}</th>
                  <th class="px-3 py-2 text-end text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.aging.balance') }}</th>
                  <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.aging.bucket') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="l in agingData.receivables" :key="l.folio_id" class="border-t border-stone-100 dark:border-border/50">
                  <td class="px-3 py-2 text-sm text-gray-900 dark:text-gray-100">{{ l.guest_name }}</td>
                  <td class="px-3 py-2 text-sm text-gray-600 dark:text-gray-400">{{ l.days_outstanding }}</td>
                  <td class="px-3 py-2 text-sm text-end font-bold text-gray-900 dark:text-gray-100">{{ formatNumber(l.balance_due) }}</td>
                  <td class="px-3 py-2"><AppBadge size="sm" :variant="agingBucketVariant(l.bucket)">{{ l.bucket }}</AppBadge></td>
                </tr>
                <tr v-if="agingData.receivables.length === 0">
                  <td colspan="4" class="px-4 py-6"><EmptyState icon="🧾" :title="t('backoffice.finance.aging.noReceivables')" /></td>
                </tr>
              </tbody>
            </table>
          </div>
        </AppCard>

        <AppCard padding="none">
          <div class="px-4 py-3 border-b border-stone-100 dark:border-border/50 flex items-center justify-between">
            <span class="font-bold text-gray-900 dark:text-gray-100">{{ t('backoffice.finance.aging.payables') }}</span>
            <span class="text-sm font-bold text-red-700 dark:text-red-300">{{ formatNumber(agingData.payables_total) }} {{ t('backoffice.finance.egp') }}</span>
          </div>
          <div class="flex flex-wrap gap-2 px-4 py-2 border-b border-stone-100 dark:border-border/50">
            <AppBadge v-for="b in agingData.payables_buckets" :key="b.label" size="sm" :variant="agingBucketVariant(b.label)">
              {{ b.label }} — {{ b.count }} ({{ formatNumber(b.amount) }})
            </AppBadge>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full min-w-[420px]">
              <thead class="bg-stone-50 dark:bg-gray-800/60">
                <tr>
                  <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.aging.counterparty') }}</th>
                  <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.aging.days') }}</th>
                  <th class="px-3 py-2 text-end text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.aging.remaining') }}</th>
                  <th class="px-3 py-2 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.aging.bucket') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="l in agingData.payables" :key="`${l.source_type}-${l.source_id}`" class="border-t border-stone-100 dark:border-border/50">
                  <td class="px-3 py-2 text-sm text-gray-900 dark:text-gray-100">{{ l.counterparty }}</td>
                  <td class="px-3 py-2 text-sm text-gray-600 dark:text-gray-400">{{ l.days_outstanding }}</td>
                  <td class="px-3 py-2 text-sm text-end font-bold text-gray-900 dark:text-gray-100">{{ formatNumber(l.remaining) }}</td>
                  <td class="px-3 py-2"><AppBadge size="sm" :variant="agingBucketVariant(l.bucket)">{{ l.bucket }}</AppBadge></td>
                </tr>
                <tr v-if="agingData.payables.length === 0">
                  <td colspan="4" class="px-4 py-6"><EmptyState icon="📦" :title="t('backoffice.finance.aging.noPayables')" /></td>
                </tr>
              </tbody>
            </table>
          </div>
        </AppCard>
      </div>
    </template>
    <AppCard v-else padding="lg">
      <EmptyState icon="⏳" :title="t('backoffice.finance.noDataThisPeriod')" />
    </AppCard>
  </div>
</template>
