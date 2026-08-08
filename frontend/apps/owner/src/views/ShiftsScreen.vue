<script setup lang="ts">
/**
 * ShiftsScreen — Phase 7 + 7b
 * tabs: التنبيهات | مفتوحة | تاريخ
 * F-1: من يعمل الآن + حركات الكاش
 * F-2: تاريخ الورديات المغلقة (آخر 7 أيام)
 * G-1: قائمة الاستثناءات مرتّبة بالخطورة
 */
import { ref } from 'vue'
import { useOwnerShifts, useOwnerExceptions, useOwnerShiftHistory } from '../composables/useOwnerData'
import { formatMoney } from '../composables/useFormat'
import ErrorState from '../components/ErrorState.vue'
import SkeletonCards from '../components/SkeletonCards.vue'
import type { ShiftMonitorItem } from '../api/types'

const tabs = ['exceptions', 'open', 'history'] as const
type Tab = typeof tabs[number]
const activeTab = ref<Tab>('exceptions')
const tabLabels: Record<Tab, string> = {
  exceptions: 'التنبيهات',
  open:       'مفتوحة',
  history:    'تاريخ',
}

const { data: shiftsData,  loading: shiftsLoading,  error: shiftsError,  reload: shiftsReload  } = useOwnerShifts()
const { data: excData,     loading: excLoading,     error: excError,     reload: excReload     } = useOwnerExceptions()
const { data: historyData, loading: historyLoading, error: historyError, reload: historyReload } = useOwnerShiftHistory(7)

const expandedShifts = ref<Set<number>>(new Set())
function toggleShift(id: number) {
  if (expandedShifts.value.has(id)) expandedShifts.value.delete(id)
  else expandedShifts.value.add(id)
}

const tierStyle: Record<string, string> = {
  critical:  'text-owner-red border-owner-red/30 bg-red-950/20',
  attention: 'text-owner-amber border-owner-amber/30 bg-amber-950/20',
  watch:     'text-owner-muted border-owner-border bg-owner-card',
}

const tierLabel: Record<string, string> = {
  critical:  '🔴 حرج',
  attention: '🟡 انتبه',
  watch:     '⚪ رصد',
}

const varianceTierStyle: Record<ShiftMonitorItem['variance_tier'], string> = {
  critical:  'text-owner-red',
  attention: 'text-owner-amber',
  normal:    'text-owner-green',
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' })
}

function formatDateTime(iso: string) {
  return new Date(iso).toLocaleString('ar-EG', {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}
</script>

<template>
  <div class="flex-1 flex flex-col overflow-hidden">
    <!-- Tab bar -->
    <div class="flex bg-owner-card border-b border-owner-border" role="tablist">
      <button
        v-for="tab in tabs"
        :key="tab"
        class="flex-1 py-3 text-sm font-semibold transition-colors touch-target relative"
        :class="activeTab === tab
          ? 'text-owner-green border-b-2 border-owner-green -mb-px'
          : 'text-owner-muted'"
        role="tab"
        :aria-selected="activeTab === tab"
        @click="activeTab = tab"
      >
        {{ tabLabels[tab] }}
        <span
          v-if="tab === 'exceptions' && excData && excData.critical_count > 0"
          class="absolute top-1.5 right-3 bg-owner-red text-black text-xs font-bold rounded-full w-4 h-4 flex items-center justify-center"
        >{{ excData.critical_count }}</span>
      </button>
    </div>

    <div class="flex-1 overflow-y-auto overscroll-contain p-4 space-y-3">

      <!-- ── التنبيهات ──────────────────────────────────────────── -->
      <template v-if="activeTab === 'exceptions'">
        <ErrorState v-if="excError && !excLoading" :message="excError" @retry="excReload" />
        <SkeletonCards v-else-if="excLoading && !excData" />
        <template v-else-if="excData">
          <div class="owner-card">
            <div class="flex gap-4 text-sm">
              <div class="text-center flex-1">
                <div class="font-bold text-owner-red text-xl">{{ excData.critical_count }}</div>
                <div class="text-xs text-owner-muted">حرج</div>
              </div>
              <div class="text-center flex-1">
                <div class="font-bold text-owner-amber text-xl">{{ excData.attention_count }}</div>
                <div class="text-xs text-owner-muted">انتبه</div>
              </div>
              <div class="text-center flex-1">
                <div class="font-bold text-owner-muted text-xl">{{ excData.watch_count }}</div>
                <div class="text-xs text-owner-muted">رصد</div>
              </div>
            </div>
          </div>
          <div v-if="excData.exceptions.length === 0" class="owner-card text-center py-6">
            <div class="text-2xl mb-2">✅</div>
            <div class="text-sm text-owner-muted">لا توجد تنبيهات الآن</div>
          </div>
          <div
            v-for="exc in excData.exceptions"
            :key="exc.exception_id"
            class="owner-card border"
            :class="tierStyle[exc.tier] ?? tierStyle.watch"
            role="alert"
          >
            <div class="flex items-start justify-between gap-2 mb-2">
              <div>
                <div class="text-xs font-bold mb-0.5">{{ tierLabel[exc.tier] ?? exc.tier }}</div>
                <div class="text-sm font-bold text-owner-text">{{ exc.title }}</div>
              </div>
              <div class="text-right shrink-0">
                <div class="font-mono font-bold text-sm">{{ formatMoney(exc.impact) }}</div>
                <div class="text-xs text-owner-muted">تأثير</div>
              </div>
            </div>
            <div class="text-xs text-owner-muted mb-2">{{ exc.detail }}</div>
            <div class="flex gap-3 text-xs text-owner-muted">
              <span v-if="exc.entity_name">{{ exc.entity_name }}</span>
              <span>{{ exc.category }}</span>
              <span>{{ exc.status }}</span>
            </div>
          </div>
          <div class="text-center text-xs text-owner-muted py-2">
            محسوب: {{ new Date(excData.computed_at).toLocaleTimeString('ar-EG') }}
          </div>
        </template>
      </template>

      <!-- ── الورديات المفتوحة ──────────────────────────────────── -->
      <template v-else-if="activeTab === 'open'">
        <ErrorState v-if="shiftsError && !shiftsLoading" :message="shiftsError" @retry="shiftsReload" />
        <SkeletonCards v-else-if="shiftsLoading && !shiftsData" />
        <template v-else-if="shiftsData">
          <div class="owner-card">
            <div class="section-label">ورديات مفتوحة الآن</div>
            <div class="metric-value text-owner-text">{{ shiftsData.open_count }}</div>
          </div>
          <div v-if="shiftsData.shifts.length === 0" class="owner-card text-center py-6">
            <div class="text-sm text-owner-muted">لا توجد ورديات مفتوحة</div>
          </div>
          <div v-for="shift in shiftsData.shifts" :key="shift.shift_id" class="owner-card">
            <button class="w-full flex items-center justify-between" @click="toggleShift(shift.shift_id)">
              <div class="text-right">
                <div class="text-sm font-bold text-owner-text">{{ shift.cashier_name }}</div>
                <div class="text-xs text-owner-muted">منذ {{ formatTime(shift.opened_at) }}</div>
              </div>
              <div class="text-left">
                <div class="font-mono font-bold text-sm" :class="varianceTierStyle[shift.variance_tier]">
                  {{ formatMoney(shift.expected_cash) }}
                </div>
                <div class="text-xs text-owner-muted">{{ shift.invoice_count }} فاتورة</div>
              </div>
            </button>
            <div v-if="expandedShifts.has(shift.shift_id)" class="mt-3 pt-3 border-t border-owner-border space-y-2">
              <div class="grid grid-cols-2 gap-2 text-xs">
                <div><div class="text-owner-muted">مبيعات</div><div class="font-mono font-semibold text-owner-text">{{ formatMoney(shift.total_sales) }}</div></div>
                <div><div class="text-owner-muted">كاش فعلي</div><div class="font-mono font-semibold text-owner-text">{{ formatMoney(shift.total_cash) }}</div></div>
                <div><div class="text-owner-muted">رأس مال</div><div class="font-mono font-semibold text-owner-text">{{ formatMoney(shift.opening_float) }}</div></div>
                <div v-if="shift.variance != null">
                  <div class="text-owner-muted">الفرق</div>
                  <div class="font-mono font-semibold" :class="parseFloat(shift.variance) < 0 ? 'text-owner-red' : 'text-owner-green'">{{ formatMoney(shift.variance) }}</div>
                </div>
              </div>
              <div v-if="shift.cash_movements.length > 0" class="pt-2">
                <div class="text-xs text-owner-muted mb-1">حركات الكاش</div>
                <div
                  v-for="mv in shift.cash_movements"
                  :key="mv.id"
                  class="flex items-center justify-between py-1 text-xs border-b border-owner-border/30 last:border-0"
                >
                  <div>
                    <span class="text-owner-text">{{ mv.reason }}</span>
                    <span class="text-owner-muted ml-1">— {{ mv.performed_by_name }}</span>
                  </div>
                  <span class="font-mono" :class="mv.direction === 'out' ? 'text-owner-red' : 'text-owner-green'">
                    {{ mv.direction === 'out' ? '-' : '+' }}{{ formatMoney(mv.amount) }}
                  </span>
                </div>
              </div>
            </div>
          </div>
          <div class="text-center text-xs text-owner-muted py-2">
            محسوب: {{ new Date(shiftsData.computed_at).toLocaleTimeString('ar-EG') }}
          </div>
        </template>
      </template>

      <!-- ── تاريخ الورديات المغلقة ────────────────────────────── -->
      <template v-else>
        <ErrorState v-if="historyError && !historyLoading" :message="historyError" @retry="historyReload" />
        <SkeletonCards v-else-if="historyLoading && !historyData" />
        <template v-else-if="historyData">
          <div v-if="historyData.shifts.length === 0" class="owner-card text-center py-6">
            <div class="text-sm text-owner-muted">لا توجد ورديات مغلقة خلال آخر 7 أيام</div>
          </div>
          <div v-for="shift in historyData.shifts" :key="shift.shift_id" class="owner-card">
            <div class="flex items-start justify-between">
              <div>
                <div class="text-sm font-bold text-owner-text">{{ shift.cashier_name }}</div>
                <div class="text-xs text-owner-muted">
                  {{ formatDateTime(shift.opened_at) }} ← {{ formatDateTime(shift.closed_at) }}
                </div>
              </div>
              <div class="text-right">
                <div
                  class="font-mono font-bold text-sm"
                  :class="shift.variance_tier === 'critical' ? 'text-owner-red'
                        : shift.variance_tier === 'attention' ? 'text-owner-amber'
                        : 'text-owner-green'"
                >
                  {{ shift.variance != null ? formatMoney(shift.variance) : '—' }}
                </div>
                <div class="text-xs text-owner-muted">فرق الكاش</div>
              </div>
            </div>
            <div class="grid grid-cols-3 gap-2 text-xs mt-2 pt-2 border-t border-owner-border">
              <div><div class="text-owner-muted">مبيعات</div><div class="font-mono text-owner-text">{{ formatMoney(shift.total_sales) }}</div></div>
              <div><div class="text-owner-muted">كاش فعلي</div><div class="font-mono text-owner-text">{{ formatMoney(shift.total_cash) }}</div></div>
              <div><div class="text-owner-muted">فواتير</div><div class="font-mono text-owner-text">{{ shift.invoice_count }}</div></div>
            </div>
            <div v-if="shift.cash_movements.length > 0" class="mt-2 pt-2 border-t border-owner-border/50">
              <div class="text-xs text-owner-muted mb-1">حركات الكاش ({{ shift.cash_movements.length }})</div>
              <div
                v-for="mv in shift.cash_movements"
                :key="mv.id"
                class="flex items-center justify-between py-0.5 text-xs"
              >
                <span class="text-owner-muted truncate">{{ mv.reason }}</span>
                <span class="font-mono shrink-0" :class="mv.direction === 'out' ? 'text-owner-red' : 'text-owner-green'">
                  {{ mv.direction === 'out' ? '-' : '+' }}{{ formatMoney(mv.amount) }}
                </span>
              </div>
            </div>
          </div>
          <div class="text-center text-xs text-owner-muted py-2">
            محسوب: {{ new Date(historyData.computed_at).toLocaleTimeString('ar-EG') }}
          </div>
        </template>
      </template>

    </div>
  </div>
</template>
