<script setup lang="ts">
// لوحة أداء الموظفين (wagdy.md P-11) — استُخرج من HRView.vue (تقسيم
// الملفات الكبيرة، 2026-09-07). GET /hr/leaderboard كان موجود بالكامل
// (مبيعات حقيقية من المطعم/الكافيه/الشاطئ مجمّعة بالموظف) من غير أي شاشة
// تعرضه.
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppButton, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

interface LeaderboardEntry {
  user_id: number; employee_name?: string | null; employee_code?: string | null
  total_sales: number; order_count: number
}

const toast = useToast()
const { t } = useI18n()
const { formatNumber } = useStaffFormat()
const branchId = computed(() => props.branchId)

function firstOfMonthStr(): string {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
}
function todayStr(): string {
  return new Date().toISOString().slice(0, 10)
}

const leaderboard = ref<LeaderboardEntry[]>([])
const leaderboardLoading = ref(false)
const leaderboardFrom = ref(firstOfMonthStr())
const leaderboardTo = ref(todayStr())

async function fetchLeaderboard() {
  leaderboardLoading.value = true
  try {
    const res = await api.get('/api/v1/hr/leaderboard', {
      params: { branch_id: branchId.value, date_from: leaderboardFrom.value, date_to: leaderboardTo.value },
    })
    leaderboard.value = res.data
  } catch (e) {
    toast.error(t('backoffice.hr.msg.loadLeaderboardError'))
  } finally { leaderboardLoading.value = false }
}

const leaderboardMedal = (rank: number) => rank === 0 ? '🥇' : rank === 1 ? '🥈' : rank === 2 ? '🥉' : `#${rank + 1}`

onMounted(fetchLeaderboard)
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-end gap-3">
      <div>
        <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.hr.fromDate') }}</label>
        <input v-model="leaderboardFrom" type="date"
          class="px-3 py-1.5 rounded-lg border border-stone-200 dark:border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
      </div>
      <div>
        <label class="block text-xs font-medium text-gray-500 dark:text-gray-400 mb-1">{{ t('backoffice.hr.toDate') }}</label>
        <input v-model="leaderboardTo" type="date"
          class="px-3 py-1.5 rounded-lg border border-stone-200 dark:border-border text-sm focus:outline-none focus:ring-2 focus:ring-primary-500" />
      </div>
      <AppButton size="sm" @click="fetchLeaderboard">{{ t('backoffice.hr.refresh') }}</AppButton>
    </div>

    <AppSpinner v-if="leaderboardLoading" />
    <EmptyState v-else-if="!leaderboard.length" icon="🏆" :title="t('backoffice.hr.noSalesRecorded')"
      :subtitle="t('backoffice.hr.noSalesRecordedHint')" />
    <AppCard v-else padding="none">
      <div class="overflow-x-auto">
        <table class="w-full min-w-[600px]">
          <thead class="bg-stone-50 dark:bg-gray-800/60">
            <tr>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.rank') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.employee') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.totalSales') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.hr.orderCount') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(entry, i) in leaderboard" :key="entry.user_id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
              <td class="px-4 py-3 text-lg font-black">{{ leaderboardMedal(i) }}</td>
              <td class="px-4 py-3 text-sm font-semibold text-gray-900 dark:text-gray-100">
                {{ entry.employee_name ?? t('backoffice.hr.employeeHash', { id: entry.user_id }) }}
                <span v-if="entry.employee_code" class="text-gray-400 dark:text-gray-400 font-normal">({{ entry.employee_code }})</span>
              </td>
              <td class="px-4 py-3 text-sm font-bold text-green-700 dark:text-green-300">{{ formatNumber(Number(entry.total_sales)) }} {{ t('backoffice.hr.egp') }}</td>
              <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300">{{ entry.order_count }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </AppCard>
  </div>
</template>
