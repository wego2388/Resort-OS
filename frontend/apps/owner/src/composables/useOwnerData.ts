/**
 * useOwnerData — fetches all owner endpoints with:
 * - auto-refresh كل 60 ثانية (Now/Shifts) / 5 دقائق (analytics)
 * - pull-to-refresh بـ useSwipe من @vueuse/core
 * - visibility-based refresh
 * - updateParams: يُعيد الجلب عند تغيير الفترة (DateRangePicker)
 * - لا caching — بيانات مالية حساسة (Decision 0004)
 */
import { ref, onMounted, onUnmounted, type Ref, type ComputedRef } from 'vue'
import { useSwipe } from '@vueuse/core'
import {
  fetchOwnerNow,
  fetchOwnerNowHistory,
  fetchCreditReceivables,
  fetchOwnerPerformance,
  fetchSalesPerformance,
  fetchBeachPerformance,
  fetchChannelAnalytics,
  fetchExpenseAnalytics,
  fetchProcurementAnalytics,
  fetchShiftMonitor,
  fetchExceptions,
  fetchShiftHistory,
  fetchHRSummary,
  fetchDiscountAnalytics,
} from '../api/owner'
import type {
  OwnerNowResponse,
  OwnerPerformanceResponse,
  NowHistoryResponse,
  SalesPerformanceResponse,
  BeachPerformanceResponse,
  ChannelAnalyticsResponse,
  ExpenseAnalyticsResponse,
  ProcurementAnalyticsResponse,
  ShiftMonitorResponse,
  ExceptionsResponse,
  ShiftHistoryResponse,
  HRSummaryResponse,
  DiscountAnalyticsResponse,
  CreditReceivablesResponse,
} from '../api/types'

const NOW_REFRESH_MS         = 60_000
const PERFORMANCE_REFRESH_MS = 5 * 60_000

type DateParams = { date_from?: string; date_to?: string }

/**
 * Generic composable بـ auto-refresh + updateParams.
 * يقبل fetcher يأخذ params اختيارية.
 */
function useAnalyticsData<T, P = void>(
  fetcherFactory: (params?: P) => Promise<T>,
  initialParams?: P,
  refreshMs = PERFORMANCE_REFRESH_MS,
) {
  const data    = ref<T | null>(null) as Ref<T | null>
  const loading = ref(true)
  const error   = ref<string | null>(null)
  let currentParams = initialParams
  let timer: ReturnType<typeof setInterval> | null = null

  async function load(silent = false) {
    if (!silent) loading.value = true
    error.value = null
    try {
      data.value = await fetcherFactory(currentParams)
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'خطأ في جلب البيانات'
    } finally {
      loading.value = false
    }
  }

  function updateParams(params: P) {
    currentParams = params
    load(true)
  }

  function onVisibilityChange() {
    if (document.visibilityState === 'visible') load(true)
  }

  onMounted(() => {
    load()
    timer = setInterval(() => load(true), refreshMs)
    document.addEventListener('visibilitychange', onVisibilityChange)
  })

  onUnmounted(() => {
    if (timer) clearInterval(timer)
    document.removeEventListener('visibilitychange', onVisibilityChange)
  })

  return { data, loading, error, reload: () => load(true), updateParams }
}

// ─── Now screen ─────────────────────────────────────────────────────

export function useOwnerNow(scrollContainer: Ref<HTMLElement | null>) {
  const data       = ref<OwnerNowResponse | null>(null)
  const loading    = ref(true)
  const error      = ref<string | null>(null)
  const refreshing = ref(false)
  let timer: ReturnType<typeof setInterval> | null = null

  async function load(silent = false) {
    if (!silent) loading.value = true
    error.value = null
    try {
      data.value = await fetchOwnerNow()
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'خطأ في جلب البيانات'
    } finally {
      loading.value    = false
      refreshing.value = false
    }
  }

  useSwipe(scrollContainer, {
    onSwipeEnd(_e, direction) {
      if (
        direction === 'down' &&
        (scrollContainer.value?.scrollTop ?? 0) === 0 &&
        !refreshing.value
      ) {
        refreshing.value = true
        navigator.vibrate?.(10)
        load(true)
      }
    },
  })

  function onVisibilityChange() {
    if (document.visibilityState === 'visible') load(true)
  }

  onMounted(() => {
    load()
    timer = setInterval(() => load(true), NOW_REFRESH_MS)
    document.addEventListener('visibilitychange', onVisibilityChange)
  })

  onUnmounted(() => {
    if (timer) clearInterval(timer)
    document.removeEventListener('visibilitychange', onVisibilityChange)
  })

  return { data, loading, error, refreshing, reload: () => load(true) }
}

// ─── Performance ────────────────────────────────────────────────────

export function useOwnerPerformance() {
  const data    = ref<OwnerPerformanceResponse | null>(null)
  const loading = ref(true)
  const error   = ref<string | null>(null)
  let timer: ReturnType<typeof setInterval> | null = null

  async function load(silent = false) {
    if (!silent) loading.value = true
    error.value = null
    try {
      data.value = await fetchOwnerPerformance()
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'خطأ في جلب البيانات'
    } finally {
      loading.value = false
    }
  }

  function onVisibilityChange() {
    if (document.visibilityState === 'visible') load(true)
  }

  onMounted(() => {
    load()
    timer = setInterval(() => load(true), PERFORMANCE_REFRESH_MS)
    document.addEventListener('visibilitychange', onVisibilityChange)
  })

  onUnmounted(() => {
    if (timer) clearInterval(timer)
    document.removeEventListener('visibilitychange', onVisibilityChange)
  })

  return { data, loading, error, reload: () => load(true) }
}

// ─── Now History (Sparklines) ────────────────────────────────────────

export function useOwnerNowHistory(days = 7) {
  return useAnalyticsData<NowHistoryResponse, number>(
    (d) => fetchOwnerNowHistory(d ?? 7),
    days,
    NOW_REFRESH_MS,
  )
}

export function useOwnerCreditReceivables() {
  return useAnalyticsData<CreditReceivablesResponse>(
    () => fetchCreditReceivables(),
    undefined,
    NOW_REFRESH_MS,
  )
}

// ─── Phase 6 + 7b (date params) ─────────────────────────────────────

export function useOwnerSales(
  params?: ComputedRef<DateParams & { outlet?: string; limit?: number }> | DateParams,
) {
  const p = params && 'value' in params ? params.value : params
  return useAnalyticsData<SalesPerformanceResponse, typeof p>(
    (pp) => fetchSalesPerformance(pp as Parameters<typeof fetchSalesPerformance>[0]),
    p,
  )
}

export function useOwnerBeachPerformance(
  params?: ComputedRef<DateParams> | DateParams,
) {
  const p = params && 'value' in params ? params.value : params
  return useAnalyticsData<BeachPerformanceResponse, typeof p>(
    (pp) => fetchBeachPerformance(pp),
    p,
  )
}

export function useOwnerChannelAnalytics(
  params?: ComputedRef<DateParams> | DateParams,
) {
  const p = params && 'value' in params ? params.value : params
  return useAnalyticsData<ChannelAnalyticsResponse, typeof p>(
    (pp) => fetchChannelAnalytics(pp),
    p,
  )
}

export function useOwnerExpenseAnalytics(
  params?: ComputedRef<DateParams> | DateParams,
) {
  const p = params && 'value' in params ? params.value : params
  return useAnalyticsData<ExpenseAnalyticsResponse, typeof p>(
    (pp) => fetchExpenseAnalytics(pp),
    p,
  )
}

export function useOwnerProcurementAnalytics(
  params?: ComputedRef<DateParams> | DateParams,
) {
  const p = params && 'value' in params ? params.value : params
  return useAnalyticsData<ProcurementAnalyticsResponse, typeof p>(
    (pp) => fetchProcurementAnalytics(pp),
    p,
  )
}

// ─── Phase 7 ────────────────────────────────────────────────────────

export function useOwnerShifts() {
  return useAnalyticsData<ShiftMonitorResponse>(
    () => fetchShiftMonitor(),
    undefined,
    NOW_REFRESH_MS,
  )
}

export function useOwnerExceptions() {
  return useAnalyticsData<ExceptionsResponse>(
    () => fetchExceptions(),
    undefined,
    NOW_REFRESH_MS,
  )
}

// ─── Phase 7b: Shift History ─────────────────────────────────────────

export function useOwnerShiftHistory(days = 7) {
  return useAnalyticsData<ShiftHistoryResponse, number>(
    (d) => fetchShiftHistory(d ?? 7),
    days,
    PERFORMANCE_REFRESH_MS,
  )
}

// ─── Phase 7c: HR Summary ────────────────────────────────────────────

export function useOwnerHRSummary() {
  return useAnalyticsData<HRSummaryResponse>(
    () => fetchHRSummary(),
    undefined,
    PERFORMANCE_REFRESH_MS,
  )
}

// ─── Phase 7d: Discount Analytics ───────────────────────────────────

export function useOwnerDiscountAnalytics(
  params?: ComputedRef<DateParams> | DateParams,
) {
  const p = params && 'value' in params ? params.value : params
  return useAnalyticsData<DiscountAnalyticsResponse, typeof p>(
    (pp) => fetchDiscountAnalytics(pp),
    p,
  )
}
