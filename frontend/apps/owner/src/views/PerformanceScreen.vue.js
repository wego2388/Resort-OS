/// <reference types="../../node_modules/.vue-global-types/vue_3.5_0_0_0.d.ts" />
/**
 * PerformanceScreen — شاشة «الأداء»
 * مقارنة ثلاث فترات من GET /api/v1/owner/performance
 * Swipe بين الفترات بـ useSwipe من @vueuse/core
 */
import { ref, computed } from 'vue';
import { useSwipe } from '@vueuse/core';
import { useOwnerPerformance } from '../composables/useOwnerData';
import PeriodComparisonCard from '../components/PeriodComparisonCard.vue';
import ErrorState from '../components/ErrorState.vue';
import SkeletonCards from '../components/SkeletonCards.vue';
const { data, loading, error, reload } = useOwnerPerformance();
// الـ tab الحالي — يتغيّر بـ swipe أو tap
const tabs = ['today', 'week', 'month'];
const activeTab = ref('today');
const tabLabels = {
    today: 'اليوم',
    week: 'الأسبوع',
    month: 'الشهر',
};
const container = ref(null);
useSwipe(container, {
    onSwipeEnd(_e, direction) {
        const idx = tabs.indexOf(activeTab.value);
        if (direction === 'left' && idx < tabs.length - 1) {
            activeTab.value = tabs[idx + 1];
            navigator.vibrate?.(8);
        }
        if (direction === 'right' && idx > 0) {
            activeTab.value = tabs[idx - 1];
            navigator.vibrate?.(8);
        }
    },
});
const currentComparison = computed(() => {
    if (!data.value)
        return null;
    if (activeTab.value === 'today')
        return data.value.today_vs_yesterday;
    if (activeTab.value === 'week')
        return data.value.week_vs_prior_week;
    return data.value.month_vs_prior_month;
});
const currentTitle = computed(() => {
    if (activeTab.value === 'today')
        return 'اليوم مقابل أمس';
    if (activeTab.value === 'week')
        return 'الأسبوع الحالي مقابل الماضي';
    return 'الشهر الحالي مقابل الماضي';
});
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ref: "container",
    ...{ class: "flex-1 flex flex-col overflow-hidden" },
});
/** @type {typeof __VLS_ctx.container} */ ;
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "flex bg-owner-card border-b border-owner-border" },
    role: "tablist",
});
for (const [tab] of __VLS_getVForSourceType((__VLS_ctx.tabs))) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.activeTab = tab;
            } },
        key: (tab),
        ...{ class: "flex-1 py-3 text-sm font-semibold transition-colors touch-target" },
        ...{ class: (__VLS_ctx.activeTab === tab
                ? 'text-owner-green border-b-2 border-owner-green -mb-px'
                : 'text-owner-muted') },
        role: "tab",
        'aria-selected': (__VLS_ctx.activeTab === tab),
    });
    (__VLS_ctx.tabLabels[tab]);
}
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "flex-1 overflow-y-auto overscroll-contain p-4" },
});
if (__VLS_ctx.error && !__VLS_ctx.loading) {
    /** @type {[typeof ErrorState, ]} */ ;
    // @ts-ignore
    const __VLS_0 = __VLS_asFunctionalComponent(ErrorState, new ErrorState({
        ...{ 'onRetry': {} },
        message: (__VLS_ctx.error),
    }));
    const __VLS_1 = __VLS_0({
        ...{ 'onRetry': {} },
        message: (__VLS_ctx.error),
    }, ...__VLS_functionalComponentArgsRest(__VLS_0));
    let __VLS_3;
    let __VLS_4;
    let __VLS_5;
    const __VLS_6 = {
        onRetry: (__VLS_ctx.reload)
    };
    var __VLS_2;
}
else if (__VLS_ctx.loading && !__VLS_ctx.data) {
    /** @type {[typeof SkeletonCards, ]} */ ;
    // @ts-ignore
    const __VLS_7 = __VLS_asFunctionalComponent(SkeletonCards, new SkeletonCards({}));
    const __VLS_8 = __VLS_7({}, ...__VLS_functionalComponentArgsRest(__VLS_7));
}
else if (__VLS_ctx.currentComparison) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
    /** @type {[typeof PeriodComparisonCard, ]} */ ;
    // @ts-ignore
    const __VLS_10 = __VLS_asFunctionalComponent(PeriodComparisonCard, new PeriodComparisonCard({
        title: (__VLS_ctx.currentTitle),
        comparison: (__VLS_ctx.currentComparison),
    }));
    const __VLS_11 = __VLS_10({
        title: (__VLS_ctx.currentTitle),
        comparison: (__VLS_ctx.currentComparison),
    }, ...__VLS_functionalComponentArgsRest(__VLS_10));
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "text-center text-xs text-owner-muted mt-6 opacity-50" },
    });
    if (__VLS_ctx.data) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "text-center text-xs text-owner-muted mt-2" },
        });
        (new Date(__VLS_ctx.data.computed_at).toLocaleTimeString('ar-EG'));
    }
}
/** @type {__VLS_StyleScopedClasses['flex-1']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-col']} */ ;
/** @type {__VLS_StyleScopedClasses['overflow-hidden']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['border-b']} */ ;
/** @type {__VLS_StyleScopedClasses['border-owner-border']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-1']} */ ;
/** @type {__VLS_StyleScopedClasses['py-3']} */ ;
/** @type {__VLS_StyleScopedClasses['text-sm']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['transition-colors']} */ ;
/** @type {__VLS_StyleScopedClasses['touch-target']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-1']} */ ;
/** @type {__VLS_StyleScopedClasses['overflow-y-auto']} */ ;
/** @type {__VLS_StyleScopedClasses['overscroll-contain']} */ ;
/** @type {__VLS_StyleScopedClasses['p-4']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['mt-6']} */ ;
/** @type {__VLS_StyleScopedClasses['opacity-50']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['mt-2']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            PeriodComparisonCard: PeriodComparisonCard,
            ErrorState: ErrorState,
            SkeletonCards: SkeletonCards,
            data: data,
            loading: loading,
            error: error,
            reload: reload,
            tabs: tabs,
            activeTab: activeTab,
            tabLabels: tabLabels,
            container: container,
            currentComparison: currentComparison,
            currentTitle: currentTitle,
        };
    },
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
});
; /* PartiallyEnd: #4569/main.vue */
