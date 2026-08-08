<script setup lang="ts">
/**
 * PeriodComparisonCard — بطاقة مقارنة فترتين.
 * Phase 7e: collapsible outlet breakdown تحت الأرقام الرئيسية.
 */
import { ref } from 'vue'
import type { PeriodComparison } from '../api/types'
import { formatMoney, formatPct, deltaClass, deltaArrow } from '../composables/useFormat'

defineProps<{
  title: string
  comparison: PeriodComparison
  loading?: boolean
}>()

const showBreakdown = ref(false)
</script>

<template>
  <div class="owner-card" role="region" :aria-label="title">
    <!-- Title -->
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-sm font-bold text-owner-text">{{ title }}</h3>
      <div class="flex gap-2 text-xs text-owner-muted">
        <span>{{ comparison.current.label }}</span>
        <span>vs</span>
        <span>{{ comparison.prior.label }}</span>
      </div>
    </div>

    <template v-if="loading">
      <div class="space-y-3">
        <div v-for="i in 3" :key="i" class="skeleton h-12 rounded" />
      </div>
    </template>

    <template v-else>
      <!-- ثلاثة صفوف: إيراد / مصروف / صافي -->
      <div class="space-y-3">
        <!-- إيراد -->
        <div class="flex items-center justify-between py-2 border-b border-owner-border">
          <span class="text-xs text-owner-muted">الإيراد</span>
          <div class="text-right">
            <div class="text-sm font-bold text-owner-text">
              {{ formatMoney(comparison.current.total_revenue) }}
            </div>
            <div
              class="text-xs font-semibold flex items-center gap-1 justify-end"
              :class="deltaClass(comparison.revenue_delta)"
            >
              <span>{{ deltaArrow(comparison.revenue_delta) }}</span>
              <span>{{ formatPct(comparison.revenue_pct) }}</span>
            </div>
          </div>
        </div>

        <!-- مصروف -->
        <div class="flex items-center justify-between py-2 border-b border-owner-border">
          <span class="text-xs text-owner-muted">المصروفات</span>
          <div class="text-right">
            <div class="text-sm font-bold text-owner-text">
              {{ formatMoney(comparison.current.total_expense) }}
            </div>
            <div
              class="text-xs font-semibold flex items-center gap-1 justify-end"
              :class="deltaClass(typeof comparison.expense_delta === 'string'
                ? -parseFloat(comparison.expense_delta)
                : -(comparison.expense_delta as number))"
            >
              <span>{{ deltaArrow(comparison.expense_delta) }}</span>
              <span>{{ formatPct(comparison.expense_pct) }}</span>
            </div>
          </div>
        </div>

        <!-- صافي الدخل -->
        <div class="flex items-center justify-between py-2">
          <span class="text-xs font-bold text-owner-text">صافي الدخل</span>
          <div class="text-right">
            <div
              class="text-base font-bold"
              :class="{
                'text-owner-green': parseFloat(String(comparison.current.net_income)) > 0,
                'text-owner-red':   parseFloat(String(comparison.current.net_income)) < 0,
                'text-owner-muted': parseFloat(String(comparison.current.net_income)) === 0,
              }"
            >
              {{ formatMoney(comparison.current.net_income) }}
            </div>
            <div
              class="text-xs font-semibold flex items-center gap-1 justify-end"
              :class="deltaClass(comparison.net_income_delta)"
            >
              <span>{{ deltaArrow(comparison.net_income_delta) }}</span>
              <span>{{ formatPct(comparison.net_income_pct) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Phase 7e: Outlet Breakdown — collapsible -->
      <div
        v-if="comparison.breakdown"
        class="mt-3 pt-3 border-t border-owner-border"
      >
        <button
          class="w-full flex items-center justify-between text-xs text-owner-muted"
          @click="showBreakdown = !showBreakdown"
        >
          <span>تفصيل الإيراد بالمنفذ</span>
          <span>{{ showBreakdown ? '▲' : '▼' }}</span>
        </button>

        <div v-if="showBreakdown" class="mt-2 space-y-1.5">
          <div
            v-if="comparison.breakdown.dining_revenue != null"
            class="flex items-center justify-between text-xs"
          >
            <span class="text-owner-muted">🍽 المطعم</span>
            <span class="font-mono text-owner-text">{{ formatMoney(comparison.breakdown.dining_revenue) }}</span>
          </div>
          <div
            v-if="comparison.breakdown.beach_revenue != null"
            class="flex items-center justify-between text-xs"
          >
            <span class="text-owner-muted">🏖 الشاطئ</span>
            <span class="font-mono text-owner-text">{{ formatMoney(comparison.breakdown.beach_revenue) }}</span>
          </div>
          <div
            v-if="comparison.breakdown.rooms_revenue != null"
            class="flex items-center justify-between text-xs"
          >
            <span class="text-owner-muted">🏨 الغرف</span>
            <span class="font-mono text-owner-text">{{ formatMoney(comparison.breakdown.rooms_revenue) }}</span>
          </div>
          <div
            v-if="comparison.breakdown.other_revenue != null"
            class="flex items-center justify-between text-xs"
          >
            <span class="text-owner-muted">📦 أخرى</span>
            <span class="font-mono text-owner-text">{{ formatMoney(comparison.breakdown.other_revenue) }}</span>
          </div>
          <div
            v-if="!comparison.breakdown.dining_revenue &&
                  !comparison.breakdown.beach_revenue &&
                  !comparison.breakdown.rooms_revenue &&
                  !comparison.breakdown.other_revenue"
            class="text-xs text-owner-muted text-center py-2"
          >
            تفصيل المنافذ غير متاح لهذه الفترة
          </div>
        </div>
      </div>

      <!-- Provisional notice -->
      <div
        v-if="comparison.current.is_provisional"
        class="mt-3 flex items-center gap-1 text-xs text-owner-amber"
        role="status"
      >
        <span>⚠</span>
        <span>الفترة الحالية غير مقفولة — الأرقام مؤقتة</span>
      </div>
    </template>
  </div>
</template>
