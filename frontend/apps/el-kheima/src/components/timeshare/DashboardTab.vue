<script setup lang="ts">
// لوحة تحكم الملكية الجزئية (ملخص عام) — استُخرج من TimeshareView.vue
// (تقسيم الملفات الكبيرة، 2026-09-07).
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

interface Visit {
  id: number; contract_id: number; unit_id: number | null
  check_in: string; check_out: string; nights: number; status: string
  customer_name?: string; customer_phone?: string; room_type?: string
  week_number?: number; visit_start?: string
  days_until: number
}
interface OverdueClient {
  id: number; customer_name: string; customer_phone?: string | null
  room_type: string; overdue_amount?: number
  pending_count?: number; next_due?: string
}
interface SummaryData {
  active_contracts?: number; collection_rate_pct?: number; total_collected?: number
  total_value?: number; total_overdue?: number; overdue_contracts_count?: number
  this_month_due?: number; upcoming_visits?: Visit[]; overdue_clients?: OverdueClient[]
  occupied_units?: number; total_units?: number; occupancy_rate_pct?: number
  pending_visit_requests?: number; open_support_tickets?: number
}

const toast = useToast()
const { t } = useI18n()
const { formatDate, formatMoney } = useStaffFormat()
const branchId = computed(() => props.branchId)

const fmt = (v: number | string | null | undefined) => formatMoney(v, 'EGP')
const formatDateValue = (d?: string) => {
  if (!d) return '—'
  try { return formatDate(d, { day: 'numeric', month: 'short', year: 'numeric' }) }
  catch { return d }
}
function roomTypeLabel(type: string): string {
  return t(`backoffice.timeshare.unitTypes.${type}`, type)
}
function roomTypeBadge(type: string) {
  const m: Record<string, string> = {
    'Studio': 'bg-sky-100 text-sky-700 dark:bg-sky-950/60 dark:text-sky-300',
    'Chalet': 'bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300',
  }
  return `text-xs px-2 py-1 rounded-full font-bold ${m[type] || 'bg-stone-100 dark:bg-gray-700 text-stone-600 dark:text-stone-300'}`
}

const summary = ref<SummaryData>({})

async function loadSummary() {
  try { const r = await api.get('/api/v1/timeshare/cs-summary', { params: { branch_id: branchId.value } }); summary.value = r.data }
  catch (e) { toast.error(t('backoffice.timeshare.msg.loadSummaryError')) }
}

onMounted(loadSummary)
</script>

<template>
  <div class="space-y-5">
    <div class="grid grid-cols-2 lg:grid-cols-5 gap-3">
      <AppCard padding="md">
        <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase tracking-wide mb-2">{{ t('backoffice.timeshare.activeContracts') }}</p>
        <p class="text-2xl font-black text-gray-900 dark:text-gray-100">{{ summary.active_contracts || 0 }}</p>
      </AppCard>
      <AppCard padding="md">
        <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase tracking-wide mb-2">{{ t('backoffice.timeshare.occupancyRate') }}</p>
        <p class="text-2xl font-black text-sky-600 dark:text-sky-300">{{ summary.occupancy_rate_pct ?? 0 }}%</p>
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">{{ t('backoffice.timeshare.occupancyOfTotal', { occupied: summary.occupied_units || 0, total: summary.total_units || 0 }) }}</p>
      </AppCard>
      <AppCard padding="md">
        <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase tracking-wide mb-2">{{ t('backoffice.timeshare.collectionRate') }}</p>
        <p :class="['text-2xl font-black', (summary.collection_rate_pct||0) >= 50 ? 'text-green-600 dark:text-green-300' : 'text-amber-500 dark:text-amber-300']">
          {{ summary.collection_rate_pct || 0 }}%
        </p>
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">{{ t('backoffice.timeshare.ofTotal', { collected: fmt(summary.total_collected), total: fmt(summary.total_value) }) }}</p>
      </AppCard>
      <AppCard padding="md">
        <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase tracking-wide mb-2">{{ t('backoffice.timeshare.overdueAmounts') }}</p>
        <p class="text-2xl font-black text-red-500">{{ fmt(summary.total_overdue) }}</p>
        <p class="text-xs text-gray-500 dark:text-gray-400 mt-1">{{ t('backoffice.timeshare.overdueContractsCount', { count: summary.overdue_contracts_count || 0 }) }}</p>
      </AppCard>
      <AppCard padding="md">
        <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase tracking-wide mb-2">{{ t('backoffice.timeshare.dueThisMonth') }}</p>
        <p class="text-2xl font-black text-amber-500">{{ fmt(summary.this_month_due) }}</p>
      </AppCard>
    </div>

    <div class="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <AppCard padding="md">
        <div class="flex items-center justify-between mb-4">
          <p class="font-black text-sm text-gray-900 dark:text-gray-100">📅 {{ t('backoffice.timeshare.upcomingVisits') }}</p>
          <AppBadge variant="info" size="sm">{{ summary.upcoming_visits?.length || 0 }}</AppBadge>
        </div>
        <EmptyState v-if="!summary.upcoming_visits?.length" icon="📅" :title="t('backoffice.timeshare.noUpcomingVisits')" />
        <div v-else class="space-y-2">
          <div v-for="v in summary.upcoming_visits" :key="v.id" class="flex items-center justify-between gap-3 p-3 rounded-xl bg-stone-50 dark:bg-gray-800/60 border border-stone-100 dark:border-border/50">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-1 flex-wrap">
                <span class="font-bold text-xs text-gray-900 dark:text-gray-100">{{ v.customer_name }}</span>
                <span v-if="v.room_type" :class="roomTypeBadge(v.room_type)">{{ roomTypeLabel(v.room_type) }}</span>
              </div>
              <div class="text-xs text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.weekNumber', { week: v.week_number }) }} · {{ v.visit_start ? formatDateValue(v.visit_start) : '—' }}</div>
            </div>
            <div class="text-end flex-shrink-0">
              <div :class="['text-sm font-black', v.days_until === 0 ? 'text-red-500 dark:text-red-300' : v.days_until <= 7 ? 'text-amber-500 dark:text-amber-300' : 'text-green-600 dark:text-green-300']">
                {{ v.days_until === 0 ? t('backoffice.timeshare.today') : v.days_until === 1 ? t('backoffice.timeshare.tomorrow') : t('backoffice.timeshare.inDays', { days: v.days_until }) }}
              </div>
              <div v-if="v.customer_phone" class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{{ v.customer_phone }}</div>
            </div>
          </div>
        </div>
      </AppCard>

      <AppCard padding="md">
        <div class="flex items-center justify-between mb-4">
          <p class="font-black text-sm text-gray-900 dark:text-gray-100">🔴 {{ t('backoffice.timeshare.overdueClients') }}</p>
          <AppBadge variant="danger" size="sm">{{ summary.overdue_clients?.length || 0 }}</AppBadge>
        </div>
        <EmptyState v-if="!summary.overdue_clients?.length" icon="🎉" :title="t('backoffice.timeshare.noOverdue')" />
        <div v-else class="space-y-2">
          <div v-for="c in summary.overdue_clients" :key="c.id" class="flex items-center justify-between gap-3 p-3 rounded-xl bg-red-50 dark:bg-red-950/30 border border-red-100 dark:border-red-900/60">
            <div class="flex-1 min-w-0">
              <div class="flex items-center gap-2 mb-1 flex-wrap">
                <span class="font-bold text-xs text-gray-900 dark:text-gray-100">{{ c.customer_name }}</span>
                <span :class="roomTypeBadge(c.room_type)">{{ roomTypeLabel(c.room_type) }}</span>
              </div>
              <div class="text-xs text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.pendingInstallmentCount', { count: c.pending_count }) }}<span v-if="c.next_due"> · {{ t('backoffice.timeshare.dueOn', { date: formatDateValue(c.next_due) }) }}</span></div>
            </div>
            <div class="text-end flex-shrink-0">
              <div class="text-sm font-black text-red-500">{{ fmt(c.overdue_amount) }}</div>
              <a v-if="c.customer_phone" :href="`tel:${c.customer_phone}`" class="inline-flex min-h-[44px] items-center text-xs text-gray-500 dark:text-gray-400 hover:text-amber-600 dark:hover:text-amber-300">📞 {{ c.customer_phone }}</a>
            </div>
          </div>
        </div>
      </AppCard>
    </div>
  </div>
</template>
