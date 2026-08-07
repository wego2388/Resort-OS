<script setup lang="ts">
/**
 * NowScreen — شاشة «الآن»
 * المقاييس السبعة (A-1 → A-7) من GET /api/v1/owner/now
 * Auto-refresh كل 60 ثانية + pull-to-refresh
 */
import { ref } from 'vue'
import { useOwnerNow } from '../composables/useOwnerData'
import { formatMoney, formatOccupancyPct } from '../composables/useFormat'
import MetricCard from '../components/MetricCard.vue'
import ErrorState from '../components/ErrorState.vue'
import SkeletonCards from '../components/SkeletonCards.vue'

const container = ref<HTMLElement | null>(null)
const { data, loading, error, refreshing, reload } = useOwnerNow(container)
</script>

<template>
  <div ref="container" class="flex-1 overflow-y-auto overscroll-contain pb-20">
    <!-- Pull-to-refresh indicator -->
    <div v-if="refreshing" class="ptr-indicator" role="status" aria-live="polite">
      ⏳ جارٍ التحديث...
    </div>

    <!-- Error state -->
    <ErrorState v-if="error && !loading" :message="error" @retry="reload" />

    <!-- Loading skeleton -->
    <SkeletonCards v-else-if="loading && !data" />

    <!-- Content -->
    <div v-else-if="data" class="p-4 space-y-4">
      <!-- A-1: إيراد اليوم -->
      <MetricCard
        label="إيراد اليوم"
        :value="formatMoney(data.revenue_today)"
        :is-provisional="data.period.is_provisional"
        color-scheme="green"
      />

      <!-- A-2: كاش الأدراج -->
      <MetricCard
        label="كاش الأدراج المتوقع"
        :value="formatMoney(data.cash_in_drawers)"
        :subtitle="`${data.open_shift_count} وردية مفتوحة`"
        color-scheme="default"
      />

      <!-- A-3: مصروفات اليوم -->
      <MetricCard
        label="مصروفات اليوم"
        :value="formatMoney(data.expense_today)"
        :is-provisional="data.period.is_provisional"
        color-scheme="amber"
      />

      <!-- A-4: ذمم B2B -->
      <div class="owner-card" role="region" aria-label="ذمم فنادق B2B">
        <div class="section-label">ذمم فنادق B2B</div>
        
        <div class="metric-value text-owner-amber mb-4">
          {{ formatMoney(data.b2b_total_outstanding) }}
        </div>

        <div v-if="data.b2b_receivables.length === 0" class="text-xs text-owner-muted">
          لا توجد ذمم B2B
        </div>

        <div v-else class="space-y-2">
          <div
            v-for="item in data.b2b_receivables.slice(0, 5)"
            :key="item.contract_id"
            class="flex items-center justify-between text-xs py-1.5 border-b border-owner-border last:border-0"
          >
            <div class="flex items-center gap-2">
              <span class="font-semibold text-owner-text">{{ item.hotel_name }}</span>
              <span v-if="item.is_overdue" class="overdue-badge">متأخر</span>
            </div>
            <span class="font-mono text-owner-muted">{{ formatMoney(item.outstanding) }}</span>
          </div>
          <div v-if="data.b2b_receivables.length > 5" class="text-xs text-owner-muted pt-2">
            + {{ data.b2b_receivables.length - 5 }} عقد آخر
          </div>
        </div>
      </div>

      <!-- A-5: ذمم تايم شير -->
      <div class="owner-card" role="region" aria-label="ذمم تايم شير">
        <div class="section-label">ذمم تايم شير</div>
        
        <div class="metric-value text-owner-red mb-4">
          {{ formatMoney(data.timeshare_total_overdue) }}
        </div>

        <div v-if="data.timeshare_receivables.length === 0" class="text-xs text-owner-muted">
          لا توجد أقساط متأخرة
        </div>

        <div v-else class="text-xs text-owner-muted">
          {{ data.timeshare_receivables.length }} عقد · 
          {{ data.timeshare_receivables.reduce((sum, r) => sum + r.installment_count, 0) }} قسط متأخر
        </div>
      </div>

      <!-- A-6: إشغال الغرف -->
      <div class="owner-card">
        <div class="section-label">إشغال الغرف الآن</div>
        
        <div class="metric-value text-owner-green mb-2">
          {{ formatOccupancyPct(data.occupancy.occupancy_pct) }}
        </div>

        <div class="text-xs text-owner-muted">
          {{ data.occupancy.occupied_rooms }} من {{ data.occupancy.total_rooms }} غرفة
        </div>
      </div>

      <!-- A-7: سعة الشاطئ -->
      <div class="owner-card">
        <div class="section-label">سعة الشاطئ اليوم</div>
        
        <div class="metric-value text-owner-text mb-2">
          {{ formatOccupancyPct(data.beach_capacity.utilisation_pct) }}
        </div>

        <div class="text-xs text-owner-muted mb-2">
          {{ data.beach_capacity.capacity_used }} / {{ data.beach_capacity.capacity_max }} تذكرة
        </div>

        <div class="text-xs text-owner-amber flex items-start gap-1">
          <span>⚠</span>
          <span>{{ data.beach_capacity.note }}</span>
        </div>
      </div>

      <!-- Footer timestamp -->
      <div class="text-center text-xs text-owner-muted py-4">
        آخر تحديث: {{ new Date(data.period.computed_at).toLocaleTimeString('ar-EG') }}
      </div>
    </div>
  </div>
</template>
