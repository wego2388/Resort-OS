/**
 * useOwnerData — fetches all owner endpoints with:
 * - auto-refresh كل 60 ثانية (Now/Shifts) / 5 دقائق (analytics)
 * - pull-to-refresh بـ useSwipe من @vueuse/core
 * - visibility-based refresh
 * - updateParams: يُعيد الجلب عند تغيير الفترة (DateRangePicker)
 * - لا caching — بيانات مالية حساسة (Decision 0004)
 */
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { useSwipe } from '@vueuse/core';
import { fetchOwnerNow, fetchOwnerNowHistory, fetchCreditReceivables, fetchOwnerPerformance, fetchSalesPerformance, fetchBeachPerformance, fetchChannelAnalytics, fetchExpenseAnalytics, fetchProcurementAnalytics, fetchShiftMonitor, fetchExceptions, fetchShiftHistory, fetchHRSummary, fetchDiscountAnalytics, fetchOwnerSearch, fetchWatchlist, addToWatchlist, removeFromWatchlist, } from '../api/owner';
const NOW_REFRESH_MS = 60000;
const PERFORMANCE_REFRESH_MS = 5 * 60000;
/**
 * Generic composable بـ auto-refresh + updateParams.
 * يقبل fetcher يأخذ params اختيارية.
 */
function useAnalyticsData(fetcherFactory, initialParams, refreshMs = PERFORMANCE_REFRESH_MS) {
    const data = ref(null);
    const loading = ref(true);
    const error = ref(null);
    let currentParams = initialParams;
    let timer = null;
    async function load(silent = false) {
        if (!silent)
            loading.value = true;
        error.value = null;
        try {
            data.value = await fetcherFactory(currentParams);
        }
        catch (e) {
            error.value = e instanceof Error ? e.message : 'خطأ في جلب البيانات';
        }
        finally {
            loading.value = false;
        }
    }
    function updateParams(params) {
        currentParams = params;
        load(true);
    }
    function onVisibilityChange() {
        if (document.visibilityState === 'visible')
            load(true);
    }
    onMounted(() => {
        load();
        timer = setInterval(() => load(true), refreshMs);
        document.addEventListener('visibilitychange', onVisibilityChange);
    });
    onUnmounted(() => {
        if (timer)
            clearInterval(timer);
        document.removeEventListener('visibilitychange', onVisibilityChange);
    });
    return { data, loading, error, reload: () => load(true), updateParams };
}
// ─── Now screen ─────────────────────────────────────────────────────
export function useOwnerNow(scrollContainer) {
    const data = ref(null);
    const loading = ref(true);
    const error = ref(null);
    const refreshing = ref(false);
    let timer = null;
    async function load(silent = false) {
        if (!silent)
            loading.value = true;
        error.value = null;
        try {
            data.value = await fetchOwnerNow();
        }
        catch (e) {
            error.value = e instanceof Error ? e.message : 'خطأ في جلب البيانات';
        }
        finally {
            loading.value = false;
            refreshing.value = false;
        }
    }
    useSwipe(scrollContainer, {
        onSwipeEnd(_e, direction) {
            if (direction === 'down' &&
                (scrollContainer.value?.scrollTop ?? 0) === 0 &&
                !refreshing.value) {
                refreshing.value = true;
                navigator.vibrate?.(10);
                load(true);
            }
        },
    });
    function onVisibilityChange() {
        if (document.visibilityState === 'visible')
            load(true);
    }
    onMounted(() => {
        load();
        timer = setInterval(() => load(true), NOW_REFRESH_MS);
        document.addEventListener('visibilitychange', onVisibilityChange);
    });
    onUnmounted(() => {
        if (timer)
            clearInterval(timer);
        document.removeEventListener('visibilitychange', onVisibilityChange);
    });
    return { data, loading, error, refreshing, reload: () => load(true) };
}
// ─── Performance ────────────────────────────────────────────────────
export function useOwnerPerformance() {
    const data = ref(null);
    const loading = ref(true);
    const error = ref(null);
    let timer = null;
    async function load(silent = false) {
        if (!silent)
            loading.value = true;
        error.value = null;
        try {
            data.value = await fetchOwnerPerformance();
        }
        catch (e) {
            error.value = e instanceof Error ? e.message : 'خطأ في جلب البيانات';
        }
        finally {
            loading.value = false;
        }
    }
    function onVisibilityChange() {
        if (document.visibilityState === 'visible')
            load(true);
    }
    onMounted(() => {
        load();
        timer = setInterval(() => load(true), PERFORMANCE_REFRESH_MS);
        document.addEventListener('visibilitychange', onVisibilityChange);
    });
    onUnmounted(() => {
        if (timer)
            clearInterval(timer);
        document.removeEventListener('visibilitychange', onVisibilityChange);
    });
    return { data, loading, error, reload: () => load(true) };
}
// ─── Now History (Sparklines) ────────────────────────────────────────
export function useOwnerNowHistory(days = 7) {
    return useAnalyticsData((d) => fetchOwnerNowHistory(d ?? 7), days, NOW_REFRESH_MS);
}
export function useOwnerCreditReceivables() {
    return useAnalyticsData(() => fetchCreditReceivables(), undefined, NOW_REFRESH_MS);
}
// ─── Phase 6 + 7b (date params) ─────────────────────────────────────
export function useOwnerSales(params) {
    const p = params && 'value' in params ? params.value : params;
    return useAnalyticsData((pp) => fetchSalesPerformance(pp), p);
}
export function useOwnerBeachPerformance(params) {
    const p = params && 'value' in params ? params.value : params;
    return useAnalyticsData((pp) => fetchBeachPerformance(pp), p);
}
export function useOwnerChannelAnalytics(params) {
    const p = params && 'value' in params ? params.value : params;
    return useAnalyticsData((pp) => fetchChannelAnalytics(pp), p);
}
export function useOwnerExpenseAnalytics(params) {
    const p = params && 'value' in params ? params.value : params;
    return useAnalyticsData((pp) => fetchExpenseAnalytics(pp), p);
}
export function useOwnerProcurementAnalytics(params) {
    const p = params && 'value' in params ? params.value : params;
    return useAnalyticsData((pp) => fetchProcurementAnalytics(pp), p);
}
// ─── Phase 7 ────────────────────────────────────────────────────────
export function useOwnerShifts() {
    return useAnalyticsData(() => fetchShiftMonitor(), undefined, NOW_REFRESH_MS);
}
export function useOwnerExceptions() {
    return useAnalyticsData(() => fetchExceptions(), undefined, NOW_REFRESH_MS);
}
// ─── Phase 7b: Shift History ─────────────────────────────────────────
export function useOwnerShiftHistory(days = 7) {
    return useAnalyticsData((d) => fetchShiftHistory(d ?? 7), days, PERFORMANCE_REFRESH_MS);
}
// ─── Phase 7c: HR Summary ────────────────────────────────────────────
export function useOwnerHRSummary() {
    return useAnalyticsData(() => fetchHRSummary(), undefined, PERFORMANCE_REFRESH_MS);
}
// ─── Phase 7d: Discount Analytics ───────────────────────────────────
export function useOwnerDiscountAnalytics(params) {
    const p = params && 'value' in params ? params.value : params;
    return useAnalyticsData((pp) => fetchDiscountAnalytics(pp), p);
}
// ─── Phase 8: تفاصيل التفاصيل — نافذة عند الطلب (لا auto-refresh) ──────
/**
 * useDetailSheet — بيدير حالة/تحميل نافذة تفاصيل واحدة (DetailSheet.vue).
 * `open(fetcher)` بتفتح النافذة وتجيب البيانات فورًا؛ `close()` بتقفلها.
 * كل شاشة بتستخدمه لأي عدد من أنواع التفاصيل — كل دوسة بتمرر fetcher
 * مختلف (fetchDiningItemDetail أو fetchExpenseDetail...إلخ).
 */
export function useDetailSheet() {
    const isOpen = ref(false);
    const data = ref(null);
    const loading = ref(false);
    const error = ref(null);
    let lastFetcher = null;
    async function load() {
        loading.value = true;
        error.value = null;
        try {
            data.value = lastFetcher ? await lastFetcher() : null;
        }
        catch (e) {
            error.value = e instanceof Error ? e.message : 'تعذّر تحميل التفاصيل';
        }
        finally {
            loading.value = false;
        }
    }
    function open(fetcher) {
        lastFetcher = fetcher;
        isOpen.value = true;
        data.value = null;
        load();
    }
    function close() {
        isOpen.value = false;
    }
    return { isOpen, data, loading, error, open, close, retry: load };
}
// ─── Phase 8: بحث عام — debounced ────────────────────────────────────
export function useOwnerSearch() {
    const query = ref('');
    const results = ref([]);
    const loading = ref(false);
    const error = ref(null);
    let debounceTimer = null;
    let requestSeq = 0;
    async function runSearch(q) {
        const seq = ++requestSeq;
        loading.value = true;
        error.value = null;
        try {
            const res = await fetchOwnerSearch(q);
            if (seq === requestSeq)
                results.value = res.results;
        }
        catch (e) {
            if (seq === requestSeq)
                error.value = e instanceof Error ? e.message : 'تعذّر البحث';
        }
        finally {
            if (seq === requestSeq)
                loading.value = false;
        }
    }
    function onInput(value) {
        query.value = value;
        if (debounceTimer)
            clearTimeout(debounceTimer);
        const trimmed = value.trim();
        if (trimmed.length < 2) {
            results.value = [];
            loading.value = false;
            return;
        }
        debounceTimer = setTimeout(() => runSearch(trimmed), 350);
    }
    function clear() {
        query.value = '';
        results.value = [];
        error.value = null;
        if (debounceTimer)
            clearTimeout(debounceTimer);
    }
    onUnmounted(() => {
        if (debounceTimer)
            clearTimeout(debounceTimer);
    });
    return { query, results, loading, error, onInput, clear };
}
// ─── المفضلة (Watchlist) — ميزة كانت جاهزة في الباك إند بالكامل من غير
// أي واجهة تستخدمها خالص. المالك يقدر يثبّت أهم أرقامه الشخصية فوق. ────
export function useOwnerWatchlist() {
    const items = ref([]);
    const loaded = ref(false);
    async function load() {
        try {
            items.value = await fetchWatchlist();
        }
        catch {
            items.value = [];
        }
        finally {
            loaded.value = true;
        }
    }
    const pinnedKeys = computed(() => new Set(items.value.map(i => i.metric_key)));
    function isPinned(metricKey) {
        return pinnedKeys.value.has(metricKey);
    }
    async function togglePin(metricKey) {
        const existing = items.value.find(i => i.metric_key === metricKey);
        if (existing) {
            // Optimistic: نشيلها فورًا من الشاشة، نرجّعها لو الطلب فشل
            const prev = items.value;
            items.value = items.value.filter(i => i.id !== existing.id);
            try {
                await removeFromWatchlist(existing.id);
            }
            catch {
                items.value = prev;
            }
        }
        else {
            try {
                const created = await addToWatchlist(metricKey, items.value.length);
                items.value = [...items.value, created];
            }
            catch {
                /* فشل الإضافة — نسيب الحالة زي ما هي، المستخدم يقدر يجرب تاني */
            }
        }
    }
    onMounted(load);
    return { items, loaded, isPinned, togglePin };
}
