<script setup lang="ts">
// دورة إهلاك الأصول الثابتة — استُخرج من FinanceView.vue (تقسيم الملفات
// الكبيرة، 2026-09-07).
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppButton, AppCard, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface DepreciationEntry { id: number; asset_id: number; year: number; month: number; amount: number; accumulated_after: number }
interface Asset { id: number; code: string; name: string }

const toast = useToast()
const { t } = useI18n()
const { formatNumber } = useStaffFormat()
const branchId = computed(() => props.branchId)

const loading = ref(false)
const depreciationEntries = ref<DepreciationEntry[]>([])
const assetsById = ref<Record<number, string>>({})
const depYear = ref(new Date().getFullYear())
const depMonth = ref(new Date().getMonth() + 1)
const runningDepreciation = ref(false)
const lastRunResult = ref<{ total_amount: number; entries_count: number; skipped: string[] } | null>(null)

async function loadDepreciation() {
  loading.value = true
  try {
    const [entriesRes, assetsRes] = await Promise.all([
      api.get(ENDPOINTS.finance.depreciationEntries, { params: { branch_id: branchId.value, size: 100 } }),
      api.get(ENDPOINTS.maintenance.assets, { params: { branch_id: branchId.value, size: 100 } }),
    ])
    depreciationEntries.value = entriesRes.data.items ?? []
    const map: Record<number, string> = {}
    for (const a of (assetsRes.data.items ?? []) as Asset[]) map[a.id] = a.name
    assetsById.value = map
  } catch { toast.error(t('backoffice.finance.loadDepreciationError')) }
  finally { loading.value = false }
}

async function runDepreciation() {
  runningDepreciation.value = true
  lastRunResult.value = null
  try {
    const { data } = await api.post(ENDPOINTS.finance.depreciationRun, {
      branch_id: branchId.value, year: depYear.value, month: depMonth.value,
    })
    lastRunResult.value = {
      total_amount: Number(data.total_amount),
      entries_count: data.entries.length,
      skipped: data.skipped_assets,
    }
    toast.success(t('backoffice.finance.depreciationPostedToast', { count: data.entries.length, amount: formatNumber(Number(data.total_amount)) }))
    await loadDepreciation()
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.finance.runDepreciationError'))
  } finally {
    runningDepreciation.value = false
  }
}

onMounted(loadDepreciation)
</script>

<template>
  <div>
    <AppCard class="mb-4">
      <div class="flex flex-wrap items-end gap-3">
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.year') }}</label>
          <input v-model.number="depYear" type="number" min="2020" max="2100"
            class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm w-28" />
        </div>
        <div>
          <label class="block text-xs text-gray-400 dark:text-gray-400 mb-1">{{ t('backoffice.finance.month') }}</label>
          <input v-model.number="depMonth" type="number" min="1" max="12"
            class="border border-stone-200 dark:border-border rounded-lg px-3 py-1.5 text-sm w-20" />
        </div>
        <AppButton size="sm" :loading="runningDepreciation" @click="runDepreciation">
          {{ t('backoffice.finance.runDepreciationCycle') }}
        </AppButton>
      </div>
      <div v-if="lastRunResult" class="mt-3 text-sm">
        <p class="font-semibold text-green-700 dark:text-green-300">
          {{ t('backoffice.finance.depreciationRunSummary', { count: lastRunResult.entries_count, amount: formatNumber(lastRunResult.total_amount) }) }}
        </p>
        <p v-if="lastRunResult.skipped.length" class="text-gray-400 dark:text-gray-400 text-xs mt-1">
          {{ t('backoffice.finance.skippedList', { names: lastRunResult.skipped.join('، ') }) }}
        </p>
      </div>
    </AppCard>

    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
    <AppCard v-else padding="none">
      <div class="overflow-x-auto">
        <table class="w-full min-w-[600px]">
          <thead class="bg-stone-50 dark:bg-gray-800/60">
            <tr>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.asset') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.month') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.depreciationAmount') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.finance.accumulatedAfter') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="e in depreciationEntries" :key="e.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
              <td class="px-4 py-3 text-sm font-medium text-gray-900 dark:text-gray-100">{{ assetsById[e.asset_id] ?? t('backoffice.finance.assetHash', { id: e.asset_id }) }}</td>
              <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-400">{{ e.month }}/{{ e.year }}</td>
              <td class="px-4 py-3 text-sm font-bold text-red-500">{{ formatNumber(Number(e.amount)) }} {{ t('backoffice.finance.egp') }}</td>
              <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ formatNumber(Number(e.accumulated_after)) }} {{ t('backoffice.finance.egp') }}</td>
            </tr>
            <tr v-if="depreciationEntries.length === 0">
              <td colspan="4" class="px-4 py-8">
                <EmptyState icon="📉" :title="t('backoffice.finance.noDepreciationEntries')" :subtitle="t('backoffice.finance.noDepreciationEntriesHint')" />
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </AppCard>
  </div>
</template>
