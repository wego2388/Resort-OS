<script setup lang="ts">
/**
 * PerformanceScreen — شاشة «الأداء»
 * مقارنة ثلاث فترات من GET /api/v1/owner/performance
 * Swipe بين الفترات بـ useSwipe من @vueuse/core
 */
import { ref, computed } from 'vue'
import { useSwipe } from '@vueuse/core'
import { useOwnerPerformance, useAccountBreakdownDrilldown } from '../composables/useOwnerData'
import { fetchRevenueBreakdown, fetchRevenueDetail, fetchExpenseAnalytics, fetchExpenseDetail } from '../api/owner'
import type { RevenueBreakdownResponse, RevenueDetailResponse, ExpenseAnalyticsResponse, ExpenseDetailResponse } from '../api/types'
import { formatMoney, formatMoneyFull } from '../composables/useFormat'
import PeriodComparisonCard from '../components/PeriodComparisonCard.vue'
import ErrorState from '../components/ErrorState.vue'
import SkeletonCards from '../components/SkeletonCards.vue'
import DataFreshness from '../components/DataFreshness.vue'
import DetailSheet from '../components/DetailSheet.vue'

const { data, loading, error, reload } = useOwnerPerformance()

// الـ tab الحالي — يتغيّر بـ swipe أو tap
const tabs = ['today', 'week', 'month'] as const
type Tab = typeof tabs[number]
const activeTab = ref<Tab>('today')

const tabLabels: Record<Tab, string> = {
  today: 'اليوم',
  week:  'الأسبوع',
  month: 'الشهر',
}

const container = ref<HTMLElement | null>(null)

useSwipe(container, {
  onSwipeEnd(_e, direction) {
    const idx = tabs.indexOf(activeTab.value)
    if (direction === 'left'  && idx < tabs.length - 1) {
      activeTab.value = tabs[idx + 1]
      navigator.vibrate?.(8)
    }
    if (direction === 'right' && idx > 0) {
      activeTab.value = tabs[idx - 1]
      navigator.vibrate?.(8)
    }
  },
})

const currentComparison = computed(() => {
  if (!data.value) return null
  if (activeTab.value === 'today') return data.value.today_vs_yesterday
  if (activeTab.value === 'week')  return data.value.week_vs_prior_week
  return data.value.month_vs_prior_month
})

const currentTitle = computed(() => {
  if (activeTab.value === 'today') return 'اليوم مقابل أمس'
  if (activeTab.value === 'week')  return 'الأسبوع الحالي مقابل الماضي'
  return 'الشهر الحالي مقابل الماضي'
})

// ── تفصيل الإيراد/المصروف بالحساب لنفس الفترة النشطة (2026-08-17) ──────
// نفس نمط NowScreen بالظبط، لكن الفترة هنا بتتغيّر حسب التاب (اليوم/
// الأسبوع/الشهر) بدل ما تكون دايمًا اليوم — date_from/date_to من
// comparison.current نفسها، مش تاريخ متحسوب في الفرونت إند.
const revenueDrill = useAccountBreakdownDrilldown<RevenueBreakdownResponse, RevenueDetailResponse>(
  (params) => fetchRevenueBreakdown(params),
  (params) => fetchRevenueDetail(params),
)
const expenseDrill = useAccountBreakdownDrilldown<ExpenseAnalyticsResponse, ExpenseDetailResponse>(
  (params) => fetchExpenseAnalytics(params),
  (params) => fetchExpenseDetail(params),
)

function openRevenueBreakdown() {
  if (!currentComparison.value) return
  revenueDrill.openBreakdown({
    date_from: currentComparison.value.current.date_from,
    date_to:   currentComparison.value.current.date_to,
  })
}
function openExpenseBreakdown() {
  if (!currentComparison.value) return
  expenseDrill.openBreakdown({
    date_from: currentComparison.value.current.date_from,
    date_to:   currentComparison.value.current.date_to,
  })
}

const expenseBreakdownTotal = computed(() =>
  expenseDrill.breakdown.data.value?.expense_lines.reduce(
    (sum, line) => sum + (Number.parseFloat(line.current_amount) || 0), 0,
  ) ?? null,
)

function formatEntryDate(d: string) {
  return new Date(d).toLocaleDateString('ar-EG', { month: 'short', day: 'numeric' })
}
</script>

<template>
  <div ref="container" class="flex-1 flex flex-col overflow-hidden">
    <!-- Tab bar -->
    <div class="flex bg-owner-card border-b border-owner-border" role="tablist">
      <button
        v-for="tab in tabs"
        :key="tab"
        class="flex-1 py-3 text-sm font-semibold transition-colors touch-target"
        :class="activeTab === tab
          ? 'text-owner-green border-b-2 border-owner-green -mb-px'
          : 'text-owner-muted'"
        role="tab"
        :aria-selected="activeTab === tab"
        @click="activeTab = tab"
      >
        {{ tabLabels[tab] }}
      </button>
    </div>

    <!-- Content -->
    <div class="flex-1 overflow-y-auto overscroll-contain p-4">
      <ErrorState v-if="error && !loading" :message="error" @retry="reload" />

      <SkeletonCards v-else-if="loading && !data" />

      <div v-else-if="currentComparison">
        <PeriodComparisonCard
          :title="currentTitle"
          :comparison="currentComparison"
          @click-revenue="openRevenueBreakdown"
          @click-expense="openExpenseBreakdown"
        />

        <!-- Swipe hint -->
        <div class="text-center text-xs text-owner-muted mt-6 opacity-50">
          ← اسحب للتنقل →
        </div>

        <DataFreshness v-if="data" :at="data.computed_at" :refresh="reload" />
      </div>
    </div>

    <!-- تفصيل الإيراد بالحساب لنفس الفترة النشطة (المستوى الأول) -->
    <DetailSheet
      :open="revenueDrill.breakdown.isOpen.value"
      :title="`تفصيل الإيراد بالحساب — ${currentTitle}`"
      :subtitle="revenueDrill.breakdown.data.value ? formatMoney(revenueDrill.breakdown.data.value.total_revenue) : undefined"
      :loading="revenueDrill.breakdown.loading.value"
      :error="revenueDrill.breakdown.error.value"
      @close="revenueDrill.breakdown.close()"
      @retry="revenueDrill.breakdown.retry()"
    >
      <div v-if="revenueDrill.breakdown.data.value?.revenue_lines.length === 0" class="text-xs text-owner-muted text-center py-8">
        لا يوجد إيراد مسجّل في هذه الفترة
      </div>
      <div v-else class="space-y-1">
        <button
          v-for="line in revenueDrill.breakdown.data.value?.revenue_lines ?? []"
          :key="line.account_code"
          class="w-full flex items-center justify-between py-2.5 border-b border-owner-border/50 last:border-0 text-xs text-right active:bg-owner-bg transition-colors rounded-lg -mx-1 px-1"
          @click="revenueDrill.openDetail(line.account_code)"
        >
          <span class="font-semibold text-owner-text">{{ line.account_name }}</span>
          <span class="flex items-center gap-1">
            <span class="font-mono font-semibold text-owner-green">{{ formatMoney(line.amount) }}</span>
            <span class="text-owner-muted" aria-hidden="true">‹</span>
          </span>
        </button>
      </div>
    </DetailSheet>

    <!-- تفصيل حساب إيراد معيّن — قيود اليومية الفعلية (المستوى الثاني) -->
    <DetailSheet
      :open="revenueDrill.detail.isOpen.value"
      :title="revenueDrill.detail.data.value?.account_name ?? 'تفاصيل الحساب'"
      :subtitle="revenueDrill.detail.data.value ? formatMoney(revenueDrill.detail.data.value.total_amount) : undefined"
      :loading="revenueDrill.detail.loading.value"
      :error="revenueDrill.detail.error.value"
      @close="revenueDrill.detail.close()"
      @retry="revenueDrill.detail.retry()"
    >
      <button
        class="mb-3 flex items-center gap-1 text-xs font-semibold text-owner-green"
        @click="revenueDrill.backToBreakdown()"
      >
        <span aria-hidden="true">›</span> رجوع لتفصيل الحساب
      </button>
      <div v-if="revenueDrill.detail.data.value?.lines.length === 0" class="text-xs text-owner-muted text-center py-8">
        لا توجد قيود في هذه الفترة
      </div>
      <div v-else class="space-y-1">
        <div
          v-for="line in revenueDrill.detail.data.value?.lines ?? []"
          :key="line.entry_id"
          class="flex items-center justify-between py-2.5 border-b border-owner-border/50 last:border-0 text-xs"
        >
          <div class="min-w-0">
            <div class="font-semibold text-owner-text truncate">{{ line.description }}</div>
            <div class="text-owner-muted mt-0.5">{{ line.reference }} · {{ formatEntryDate(line.entry_date) }}</div>
          </div>
          <div class="font-mono font-semibold text-owner-text shrink-0">{{ formatMoneyFull(line.amount) }}</div>
        </div>
      </div>
    </DetailSheet>

    <!-- تفصيل المصروفات بالحساب لنفس الفترة النشطة (المستوى الأول) -->
    <DetailSheet
      :open="expenseDrill.breakdown.isOpen.value"
      :title="`تفصيل المصروفات بالحساب — ${currentTitle}`"
      :subtitle="expenseBreakdownTotal != null ? formatMoney(expenseBreakdownTotal) : undefined"
      :loading="expenseDrill.breakdown.loading.value"
      :error="expenseDrill.breakdown.error.value"
      @close="expenseDrill.breakdown.close()"
      @retry="expenseDrill.breakdown.retry()"
    >
      <div v-if="expenseDrill.breakdown.data.value?.expense_lines.length === 0" class="text-xs text-owner-muted text-center py-8">
        لا توجد مصروفات مسجّلة في هذه الفترة
      </div>
      <div v-else class="space-y-1">
        <button
          v-for="line in expenseDrill.breakdown.data.value?.expense_lines ?? []"
          :key="line.account_code"
          class="w-full flex items-center justify-between py-2.5 border-b border-owner-border/50 last:border-0 text-xs text-right active:bg-owner-bg transition-colors rounded-lg -mx-1 px-1"
          @click="expenseDrill.openDetail(line.account_code)"
        >
          <span class="font-semibold text-owner-text">{{ line.account_name }}</span>
          <span class="flex items-center gap-1">
            <span class="font-mono font-semibold text-owner-amber">{{ formatMoney(line.current_amount) }}</span>
            <span class="text-owner-muted" aria-hidden="true">‹</span>
          </span>
        </button>
      </div>
    </DetailSheet>

    <!-- تفصيل حساب مصروف معيّن — قيود اليومية الفعلية (المستوى الثاني) -->
    <DetailSheet
      :open="expenseDrill.detail.isOpen.value"
      :title="expenseDrill.detail.data.value?.account_name ?? 'تفاصيل الحساب'"
      :subtitle="expenseDrill.detail.data.value ? formatMoney(expenseDrill.detail.data.value.total_amount) : undefined"
      :loading="expenseDrill.detail.loading.value"
      :error="expenseDrill.detail.error.value"
      @close="expenseDrill.detail.close()"
      @retry="expenseDrill.detail.retry()"
    >
      <button
        class="mb-3 flex items-center gap-1 text-xs font-semibold text-owner-green"
        @click="expenseDrill.backToBreakdown()"
      >
        <span aria-hidden="true">›</span> رجوع لتفصيل الحساب
      </button>
      <div v-if="expenseDrill.detail.data.value?.lines.length === 0" class="text-xs text-owner-muted text-center py-8">
        لا توجد قيود في هذه الفترة
      </div>
      <div v-else class="space-y-1">
        <div
          v-for="line in expenseDrill.detail.data.value?.lines ?? []"
          :key="line.entry_id"
          class="flex items-center justify-between py-2.5 border-b border-owner-border/50 last:border-0 text-xs"
        >
          <div class="min-w-0">
            <div class="font-semibold text-owner-text truncate">{{ line.description }}</div>
            <div class="text-owner-muted mt-0.5">{{ line.reference }} · {{ formatEntryDate(line.entry_date) }}</div>
          </div>
          <div class="font-mono font-semibold text-owner-text shrink-0">{{ formatMoneyFull(line.amount) }}</div>
        </div>
      </div>
    </DetailSheet>
  </div>
</template>
