<script setup lang="ts">
/**
 * NowScreen — شاشة «الآن»
 * المقاييس السبعة (A-1 → A-7) من GET /api/v1/owner/now
 * Sparklines من GET /api/v1/owner/now/history?days=7
 * Auto-refresh كل 60 ثانية + pull-to-refresh
 */
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useOwnerNow, useOwnerNowHistory, useOwnerCreditReceivables, useOwnerExceptions, useOwnerWatchlist } from '../composables/useOwnerData'
import { formatMoney, formatOccupancyPct } from '../composables/useFormat'
import MetricCard from '../components/MetricCard.vue'
import ErrorState from '../components/ErrorState.vue'
import SkeletonCards from '../components/SkeletonCards.vue'
import SparkLine from '../components/SparkLine.vue'
import DetailSheet from '../components/DetailSheet.vue'
import DataFreshness from '../components/DataFreshness.vue'

const router = useRouter()
const container = ref<HTMLElement | null>(null)
const { data, loading, error, refreshing, reload } = useOwnerNow(container)
const { data: historyData } = useOwnerNowHistory(7)
const { data: creditData } = useOwnerCreditReceivables()
const { data: exceptionsData, error: exceptionsError, reload: reloadExceptions } = useOwnerExceptions()
const watchlist = useOwnerWatchlist()

const importantExceptions = computed(() =>
  (exceptionsData.value?.exceptions ?? [])
    .filter(item => item.tier === 'critical' || item.tier === 'attention')
    .slice(0, 3),
)

const operatingState = computed(() => {
  if (!exceptionsData.value) {
    return { label: 'جارٍ فحص التشغيل', message: 'يتم تحميل التنبيهات الحالية.', style: 'border-owner-border' }
  }
  if (exceptionsData.value.critical_count > 0) {
    return {
      label: 'تدخل مطلوب الآن',
      message: `${exceptionsData.value.critical_count} تنبيه حرج يحتاج مراجعتك.`,
      style: 'border-owner-red/60',
    }
  }
  if (exceptionsData.value.attention_count > 0) {
    return {
      label: 'توجد نقاط للمتابعة',
      message: `${exceptionsData.value.attention_count} تنبيه يحتاج متابعة، ولا يوجد حرج الآن.`,
      style: 'border-owner-amber/60',
    }
  }
  return { label: 'التشغيل مستقر', message: 'لا توجد تنبيهات حرجة أو عاجلة الآن.', style: 'border-owner-green/50' }
})

// ── تفاصيل التفاصيل — القوائم دي أصلًا كاملة عند الجلب (5 معروضة بس) ────
type ListKey = 'b2b' | 'timeshare' | 'credit' | null
const openList = ref<ListKey>(null)
const listTitle: Record<Exclude<ListKey, null>, string> = {
  b2b: 'كل ذمم فنادق B2B',
  timeshare: 'كل ذمم الملكية الجزئية المتأخرة',
  credit: 'كل الحسابات الآجلة',
}

const metricLabels: Record<string, string> = {
  revenue_today: 'إيراد اليوم',
  cash_in_drawers: 'كاش الأدراج',
  expense_today: 'مصروفات اليوم',
}
const metricColors: Record<string, string> = {
  revenue_today: 'text-owner-green',
  cash_in_drawers: 'text-owner-text',
  expense_today: 'text-owner-amber',
}
/** يحسب قيمة أي مقياس مثبّت من data الموجودة أصلًا — بدون أي fetch إضافي */
const pinnedWithValues = computed(() => {
  if (!data.value) return []
  const values: Record<string, string> = {
    revenue_today: formatMoney(data.value.revenue_today),
    cash_in_drawers: formatMoney(data.value.cash_in_drawers),
    expense_today: formatMoney(data.value.expense_today),
  }
  return watchlist.items.value
    .filter(i => i.metric_key in values)
    .map(i => ({
      key: i.metric_key,
      label: i.label_override || metricLabels[i.metric_key] || i.metric_key,
      value: values[i.metric_key],
      color: metricColors[i.metric_key] ?? 'text-owner-text',
    }))
})

/** يحوّل array من DaySnapshot لـ numbers لكل sparkline */
const spark = computed(() => {
  const days = historyData.value?.days ?? []
  return {
    revenue:   days.map(d => parseFloat(d.revenue)),
    expense:   days.map(d => parseFloat(d.expense)),
    cash:      days.map(d => parseFloat(d.cash_in_drawers)),
    occupancy: days.map(d => parseFloat(d.occupancy_pct)),
    beach:     days.map(d => parseFloat(d.beach_utilisation_pct)),
  }
})
</script>

<template>
  <div ref="container" class="flex-1 overflow-y-auto overscroll-contain">
    <!-- Pull-to-refresh indicator -->
    <div v-if="refreshing" class="ptr-indicator" role="status" aria-live="polite">
      ⏳ جارٍ التحديث...
    </div>

    <!-- Error state -->
    <ErrorState v-if="error && !loading" :message="error" @retry="reload" />

    <!-- Loading skeleton -->
    <SkeletonCards v-else-if="loading && !data" />

    <!-- Content -->
    <div v-else-if="data" class="p-4 space-y-5">
      <!-- القرار أولاً: ملخص واضح لما يحتاج تدخل المالك الآن. -->
      <section class="owner-card border-2" :class="operatingState.style" aria-labelledby="operating-state-title">
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class="section-label !mb-1">حالة التشغيل</div>
            <h2 id="operating-state-title" class="text-base font-bold text-owner-text">{{ operatingState.label }}</h2>
            <p class="mt-1 text-xs leading-5 text-owner-muted">{{ operatingState.message }}</p>
          </div>
          <button
            v-if="exceptionsData && exceptionsData.exceptions.length > 0"
            type="button"
            class="min-h-11 shrink-0 rounded-lg border border-owner-border px-3 text-xs font-bold text-owner-green active:bg-owner-bg"
            @click="router.push('/shifts')"
          >
            كل التنبيهات
          </button>
        </div>

        <div v-if="importantExceptions.length" class="mt-3 divide-y divide-owner-border border-t border-owner-border">
          <button
            v-for="item in importantExceptions"
            :key="item.exception_id"
            type="button"
            class="flex min-h-12 w-full items-center justify-between gap-3 py-2 text-right"
            @click="router.push('/shifts')"
          >
            <span class="min-w-0">
              <span class="block truncate text-xs font-bold text-owner-text">{{ item.title }}</span>
              <span class="block truncate text-[11px] text-owner-muted">{{ item.detail }}</span>
            </span>
            <span class="shrink-0 text-owner-muted" aria-hidden="true">‹</span>
          </button>
        </div>

        <button
          v-else-if="exceptionsError"
          type="button"
          class="mt-3 min-h-11 w-full rounded-lg border border-owner-border text-xs font-semibold text-owner-amber"
          @click="reloadExceptions"
        >
          تعذّر تحميل التنبيهات — حاول مرة أخرى
        </button>
      </section>

      <!-- المفضلة — أهم أرقامك المثبّتة، لقطة سريعة فوق الشاشة -->
      <div v-if="pinnedWithValues.length > 0" class="owner-card" role="region" aria-label="المفضلة">
        <div class="section-label mb-3">أرقامك المثبّتة</div>
        <div class="grid grid-cols-2 gap-3">
          <div v-for="m in pinnedWithValues" :key="m.key" class="text-center">
            <div class="font-bold text-lg" :class="m.color">{{ m.value }}</div>
            <div class="text-xs text-owner-muted mt-0.5">{{ m.label }}</div>
          </div>
        </div>
      </div>

      <section aria-labelledby="today-money-title">
        <div class="screen-section-title">
          <h2 id="today-money-title">حركة اليوم</h2>
          <small>مقارنة مرئية لآخر ٧ أيام</small>
        </div>
        <div class="grid gap-3 lg:grid-cols-3">
          <MetricCard
            label="إيراد اليوم"
            :value="formatMoney(data.revenue_today)"
            :is-provisional="data.period.is_provisional"
            :spark-values="spark.revenue"
            color-scheme="green"
            :pinned="watchlist.isPinned('revenue_today')"
            @toggle-pin="watchlist.togglePin('revenue_today')"
          />

          <MetricCard
            label="كاش الأدراج المتوقع"
            :value="formatMoney(data.cash_in_drawers)"
            :subtitle="`${data.open_shift_count} وردية مفتوحة`"
            :spark-values="spark.cash"
            color-scheme="default"
            :pinned="watchlist.isPinned('cash_in_drawers')"
            @toggle-pin="watchlist.togglePin('cash_in_drawers')"
          />

          <MetricCard
            label="مصروفات اليوم"
            :value="formatMoney(data.expense_today)"
            :is-provisional="data.period.is_provisional"
            :spark-values="spark.expense"
            color-scheme="amber"
            :pinned="watchlist.isPinned('expense_today')"
            @toggle-pin="watchlist.togglePin('expense_today')"
          />
        </div>
      </section>

      <div class="screen-section-title">
        <h2>مبالغ تحتاج تحصيل</h2>
        <small>حسب السجلات الحالية</small>
      </div>

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
          <button
            v-if="data.b2b_receivables.length > 5"
            class="w-full text-xs text-owner-green font-semibold pt-2 text-center active:opacity-70"
            @click="openList = 'b2b'"
          >
            عرض كل الـ{{ data.b2b_receivables.length }} عقد ‹
          </button>
        </div>
      </div>

      <!-- A-5: ذمم ملكية جزئية -->
      <div class="owner-card" role="region" aria-label="ذمم ملكية جزئية">
        <div class="section-label">ذمم ملكية جزئية</div>
        
        <div class="metric-value text-owner-red mb-4">
          {{ formatMoney(data.timeshare_total_overdue) }}
        </div>

        <div v-if="data.timeshare_receivables.length === 0" class="text-xs text-owner-muted">
          لا توجد أقساط متأخرة
        </div>

        <button
          v-else
          class="w-full flex items-center justify-between text-xs text-owner-muted active:opacity-70"
          @click="openList = 'timeshare'"
        >
          <span>
            {{ data.timeshare_receivables.length }} عقد ·
            {{ data.timeshare_receivables.reduce((sum, r) => sum + r.installment_count, 0) }} قسط متأخر
          </span>
          <span class="text-owner-green font-semibold">عرض الكل ‹</span>
        </button>
      </div>

      <div class="screen-section-title">
        <h2>التشغيل الآن</h2>
        <small>الغرف والشاطئ</small>
      </div>

      <!-- A-6: إشغال الغرف -->
      <div class="owner-card" role="region" aria-label="ذمم الحسابات الآجلة الشخصية">
        <div class="section-label">حسابات العملاء والموظفين الآجلة</div>
        <div class="metric-value text-owner-amber mb-1">
          {{ formatMoney(data.credit_account_outstanding) }}
        </div>
        <div class="text-xs text-owner-muted mb-3">
          {{ data.credit_account_count }} حساب برصيد مستحق
          <span v-if="creditData?.overdue_count"> · {{ creditData.overdue_count }} متأخر</span>
        </div>
        <div v-if="creditData?.accounts.length" class="space-y-2">
          <div
            v-for="account in creditData.accounts.slice(0, 5)"
            :key="account.account_id"
            class="flex items-center justify-between border-b border-owner-border py-1.5 text-xs last:border-0"
          >
            <div class="flex items-center gap-2">
              <span class="font-semibold text-owner-text">{{ account.holder_name }}</span>
              <span v-if="account.is_overdue" class="overdue-badge">متأخر</span>
              <span v-if="account.status === 'suspended'" class="text-owner-amber">معلق</span>
            </div>
            <span class="font-mono text-owner-muted">{{ formatMoney(account.current_balance) }}</span>
          </div>
        </div>
        <div v-else class="text-xs text-owner-muted">لا توجد ذمم شخصية مستحقة</div>
        <button
          v-if="creditData && creditData.accounts.length > 5"
          class="w-full text-xs text-owner-green font-semibold pt-2 text-center active:opacity-70"
          @click="openList = 'credit'"
        >
          عرض كل الـ{{ creditData.accounts.length }} حساب ‹
        </button>
      </div>

      <!-- A-6: إشغال الغرف -->
      <div class="owner-card">
        <div class="section-label">إشغال الغرف الآن</div>
        
        <div class="metric-value text-owner-green mb-2">
          {{ formatOccupancyPct(data.occupancy.occupancy_pct) }}
        </div>

        <div class="text-xs text-owner-muted mb-2">
          {{ data.occupancy.occupied_rooms }} من {{ data.occupancy.total_rooms }} غرفة
        </div>

        <SparkLine v-if="spark.occupancy.length > 1" :values="spark.occupancy" />
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

        <SparkLine v-if="spark.beach.length > 1" :values="spark.beach" class="mb-2" />

        <div class="text-xs text-owner-amber flex items-start gap-1">
          <span>⚠</span>
          <span>{{ data.beach_capacity.note }}</span>
        </div>
      </div>

      <DataFreshness :at="data.period.computed_at" :refresh="reload" />
    </div>

    <!-- تفاصيل كل القوائم — البيانات كاملة أصلًا في data، مفيش fetch جديد -->
    <DetailSheet
      :open="openList === 'b2b'"
      :title="listTitle.b2b"
      @close="openList = null"
    >
      <div class="space-y-1">
        <div
          v-for="item in data?.b2b_receivables ?? []"
          :key="item.contract_id"
          class="flex items-center justify-between py-2.5 border-b border-owner-border/50 last:border-0 text-xs"
        >
          <div class="flex items-center gap-2">
            <span class="font-semibold text-owner-text">{{ item.hotel_name }}</span>
            <span v-if="item.is_overdue" class="overdue-badge">متأخر</span>
          </div>
          <span class="font-mono text-owner-text font-semibold">{{ formatMoney(item.outstanding) }}</span>
        </div>
      </div>
    </DetailSheet>

    <DetailSheet
      :open="openList === 'timeshare'"
      :title="listTitle.timeshare"
      @close="openList = null"
    >
      <div class="space-y-1">
        <div
          v-for="item in data?.timeshare_receivables ?? []"
          :key="item.contract_id"
          class="flex items-center justify-between py-2.5 border-b border-owner-border/50 last:border-0 text-xs"
        >
          <div class="font-semibold text-owner-text">عقد #{{ item.contract_id }}</div>
          <div class="text-left">
            <div class="font-mono text-owner-red font-semibold">{{ formatMoney(item.total_overdue) }}</div>
            <div class="text-owner-muted">{{ item.installment_count }} قسط</div>
          </div>
        </div>
      </div>
    </DetailSheet>

    <DetailSheet
      :open="openList === 'credit'"
      :title="listTitle.credit"
      @close="openList = null"
    >
      <div class="space-y-1">
        <div
          v-for="account in creditData?.accounts ?? []"
          :key="account.account_id"
          class="flex items-center justify-between py-2.5 border-b border-owner-border/50 last:border-0 text-xs"
        >
          <div class="flex items-center gap-2">
            <span class="font-semibold text-owner-text">{{ account.holder_name }}</span>
            <span v-if="account.is_overdue" class="overdue-badge">متأخر</span>
            <span v-if="account.status === 'suspended'" class="text-owner-amber">معلق</span>
          </div>
          <span class="font-mono text-owner-text font-semibold">{{ formatMoney(account.current_balance) }}</span>
        </div>
      </div>
    </DetailSheet>
  </div>
</template>
