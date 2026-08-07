<script setup lang="ts">
/**
 * PerformanceScreen — شاشة «الأداء»
 * مقارنة ثلاث فترات من GET /api/v1/owner/performance
 * Swipe بين الفترات بـ useSwipe من @vueuse/core
 */
import { ref, computed } from 'vue'
import { useSwipe } from '@vueuse/core'
import { useOwnerPerformance } from '../composables/useOwnerData'
import PeriodComparisonCard from '../components/PeriodComparisonCard.vue'
import ErrorState from '../components/ErrorState.vue'
import SkeletonCards from '../components/SkeletonCards.vue'

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
        />

        <!-- Swipe hint -->
        <div class="text-center text-xs text-owner-muted mt-6 opacity-50">
          ← اسحب للتنقل →
        </div>

        <!-- computed_at -->
        <div v-if="data" class="text-center text-xs text-owner-muted mt-2">
          محسوب: {{ new Date(data.computed_at).toLocaleTimeString('ar-EG') }}
        </div>
      </div>
    </div>
  </div>
</template>
