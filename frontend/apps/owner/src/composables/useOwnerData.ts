/**
 * useOwnerData — fetches all owner endpoints with:
 * - auto-refresh كل 60 ثانية (Now/Shifts) / 5 دقائق (analytics)
 * - pull-to-refresh بـ useSwipe من @vueuse/core
 * - visibility-based refresh
 * - updateParams: يُعيد الجلب عند تغيير الفترة (DateRangePicker)
 * - لا caching — بيانات مالية حساسة (Decision 0004)
 */
import { ref, computed, onMounted, onUnmounted, type Ref, type ComputedRef } from 'vue'
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
  fetchOwnerSearch,
  fetchWatchlist,
  addToWatchlist,
  removeFromWatchlist,
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
  SearchResultItem,
  OwnerWatchlistRead,
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

// ─── Phase 8: تفاصيل التفاصيل — نافذة عند الطلب (لا auto-refresh) ──────

/**
 * useDetailSheet — بيدير حالة/تحميل نافذة تفاصيل واحدة (DetailSheet.vue).
 * `open(fetcher)` بتفتح النافذة وتجيب البيانات فورًا؛ `close()` بتقفلها.
 * كل شاشة بتستخدمه لأي عدد من أنواع التفاصيل — كل دوسة بتمرر fetcher
 * مختلف (fetchDiningItemDetail أو fetchExpenseDetail...إلخ).
 */
export function useDetailSheet<T>() {
  const isOpen  = ref(false)
  const data    = ref<T | null>(null) as Ref<T | null>
  const loading = ref(false)
  const error   = ref<string | null>(null)
  let lastFetcher: (() => Promise<T>) | null = null

  async function load() {
    loading.value = true
    error.value = null
    try {
      data.value = lastFetcher ? await lastFetcher() : null
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'تعذّر تحميل التفاصيل'
    } finally {
      loading.value = false
    }
  }

  function open(fetcher: () => Promise<T>) {
    lastFetcher = fetcher
    isOpen.value = true
    data.value = null
    load()
  }

  function close() {
    isOpen.value = false
  }

  return { isOpen, data, loading, error, open, close, retry: load }
}

/**
 * useAccountBreakdownDrilldown — تفصيل رقم (إيراد/مصروف) بالحساب، لحظة
 * ضغط عليه، بمستويين: (1) قائمة الحسابات المكوّنة للرقم، (2) قيود
 * اليومية الفعلية داخل حساب معيّن منها (2026-08-17، طلب Mohamed الصريح).
 *
 * مبني فوق useDetailSheet مرتين (breakdown + detail) بدل اختراع state
 * جديد — نفس الشاشة (DetailSheet.vue) بتتعرض مرة واحدة بس في كل وقت،
 * والانتقال بين المستويين بيقفل واحد ويفتح التاني (نفس إحساس "push
 * navigation" الطبيعي في تطبيقات الموبايل، من غير sheet فوق sheet).
 *
 * مشترك بين NowScreen (فترة = اليوم) وPerformanceScreen (فترة = اليوم/
 * الأسبوع/الشهر — أي تبويب نشط) — نفس الـfetchers، فترة مختلفة بس.
 */
export function useAccountBreakdownDrilldown<TBreakdown, TDetail>(
  fetchBreakdown: (params: DateParams) => Promise<TBreakdown>,
  fetchDetail: (params: { account_code: string } & DateParams) => Promise<TDetail>,
) {
  const breakdown = useDetailSheet<TBreakdown>()
  const detail = useDetailSheet<TDetail>()
  let lastParams: DateParams = {}

  function openBreakdown(params: DateParams) {
    lastParams = params
    breakdown.open(() => fetchBreakdown(params))
  }

  function openDetail(accountCode: string) {
    breakdown.close()
    detail.open(() => fetchDetail({ account_code: accountCode, ...lastParams }))
  }

  function backToBreakdown() {
    detail.close()
    breakdown.open(() => fetchBreakdown(lastParams))
  }

  function closeAll() {
    breakdown.close()
    detail.close()
  }

  return { breakdown, detail, openBreakdown, openDetail, backToBreakdown, closeAll }
}

// ─── Phase 8: بحث عام — debounced ────────────────────────────────────

export function useOwnerSearch() {
  const query   = ref('')
  const results = ref<SearchResultItem[]>([])
  const loading = ref(false)
  const error   = ref<string | null>(null)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let requestSeq = 0

  async function runSearch(q: string) {
    const seq = ++requestSeq
    loading.value = true
    error.value = null
    try {
      const res = await fetchOwnerSearch(q)
      if (seq === requestSeq) results.value = res.results
    } catch (e: unknown) {
      if (seq === requestSeq) error.value = e instanceof Error ? e.message : 'تعذّر البحث'
    } finally {
      if (seq === requestSeq) loading.value = false
    }
  }

  function onInput(value: string) {
    query.value = value
    if (debounceTimer) clearTimeout(debounceTimer)
    const trimmed = value.trim()
    if (trimmed.length < 2) {
      results.value = []
      loading.value = false
      return
    }
    debounceTimer = setTimeout(() => runSearch(trimmed), 350)
  }

  function clear() {
    query.value = ''
    results.value = []
    error.value = null
    if (debounceTimer) clearTimeout(debounceTimer)
  }

  onUnmounted(() => {
    if (debounceTimer) clearTimeout(debounceTimer)
  })

  return { query, results, loading, error, onInput, clear }
}

// ─── المفضلة (Watchlist) — ميزة كانت جاهزة في الباك إند بالكامل من غير
// أي واجهة تستخدمها خالص. المالك يقدر يثبّت أهم أرقامه الشخصية فوق. ────

export function useOwnerWatchlist() {
  const items = ref<OwnerWatchlistRead[]>([])
  const loaded = ref(false)

  async function load() {
    try {
      items.value = await fetchWatchlist()
    } catch {
      items.value = []
    } finally {
      loaded.value = true
    }
  }

  const pinnedKeys = computed(() => new Set(items.value.map(i => i.metric_key)))

  function isPinned(metricKey: string) {
    return pinnedKeys.value.has(metricKey)
  }

  async function togglePin(metricKey: string) {
    const existing = items.value.find(i => i.metric_key === metricKey)
    if (existing) {
      // Optimistic: نشيلها فورًا من الشاشة، نرجّعها لو الطلب فشل
      const prev = items.value
      items.value = items.value.filter(i => i.id !== existing.id)
      try {
        await removeFromWatchlist(existing.id)
      } catch {
        items.value = prev
      }
    } else {
      try {
        const created = await addToWatchlist(metricKey, items.value.length)
        items.value = [...items.value, created]
      } catch {
        /* فشل الإضافة — نسيب الحالة زي ما هي، المستخدم يقدر يجرب تاني */
      }
    }
  }

  onMounted(load)

  return { items, loaded, isPinned, togglePin }
}
