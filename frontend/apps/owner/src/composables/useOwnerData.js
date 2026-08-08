/**
 * useOwnerData — fetches all owner endpoints with:
 * - auto-refresh كل 60 ثانية (Now/Shifts) / 5 دقائق (analytics)
 * - pull-to-refresh بـ useSwipe من @vueuse/core
 * - visibility-based refresh
 * - updateParams: يُعيد الجلب عند تغيير الفترة (DateRangePicker)
 * - لا caching — بيانات مالية حساسة (Decision 0004)
 */
import { ref, onMounted, onUnmounted } from 'vue';
import { useSwipe } from '@vueuse/core';
import { fetchOwnerNow, fetchOwnerNowHistory, fetchCreditReceivables, fetchOwnerPerformance, fetchSalesPerformance, fetchBeachPerformance, fetchChannelAnalytics, fetchExpenseAnalytics, fetchProcurementAnalytics, fetchShiftMonitor, fetchExceptions, fetchShiftHistory, fetchHRSummary, fetchDiscountAnalytics, } from '../api/owner';
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
