/// <reference types="../../node_modules/.vue-global-types/vue_3.5_0_0_0.d.ts" />
/**
 * NowScreen — شاشة «الآن»
 * المقاييس السبعة (A-1 → A-7) من GET /api/v1/owner/now
 * Auto-refresh كل 60 ثانية + pull-to-refresh
 */
import { ref } from 'vue';
import { useOwnerNow } from '../composables/useOwnerData';
import { formatMoney, formatOccupancyPct } from '../composables/useFormat';
import MetricCard from '../components/MetricCard.vue';
import ErrorState from '../components/ErrorState.vue';
import SkeletonCards from '../components/SkeletonCards.vue';
const container = ref(null);
const { data, loading, error, refreshing, reload } = useOwnerNow(container);
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ref: "container",
    ...{ class: "flex-1 overflow-y-auto overscroll-contain pb-20" },
});
/** @type {typeof __VLS_ctx.container} */ ;
if (__VLS_ctx.refreshing) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "ptr-indicator" },
        role: "status",
        'aria-live': "polite",
    });
}
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
else if (__VLS_ctx.data) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "p-4 space-y-4" },
    });
    /** @type {[typeof MetricCard, ]} */ ;
    // @ts-ignore
    const __VLS_10 = __VLS_asFunctionalComponent(MetricCard, new MetricCard({
        label: "إيراد اليوم",
        value: (__VLS_ctx.formatMoney(__VLS_ctx.data.revenue_today)),
        isProvisional: (__VLS_ctx.data.period.is_provisional),
        colorScheme: "green",
    }));
    const __VLS_11 = __VLS_10({
        label: "إيراد اليوم",
        value: (__VLS_ctx.formatMoney(__VLS_ctx.data.revenue_today)),
        isProvisional: (__VLS_ctx.data.period.is_provisional),
        colorScheme: "green",
    }, ...__VLS_functionalComponentArgsRest(__VLS_10));
    /** @type {[typeof MetricCard, ]} */ ;
    // @ts-ignore
    const __VLS_13 = __VLS_asFunctionalComponent(MetricCard, new MetricCard({
        label: "كاش الأدراج المتوقع",
        value: (__VLS_ctx.formatMoney(__VLS_ctx.data.cash_in_drawers)),
        subtitle: (`${__VLS_ctx.data.open_shift_count} وردية مفتوحة`),
        colorScheme: "default",
    }));
    const __VLS_14 = __VLS_13({
        label: "كاش الأدراج المتوقع",
        value: (__VLS_ctx.formatMoney(__VLS_ctx.data.cash_in_drawers)),
        subtitle: (`${__VLS_ctx.data.open_shift_count} وردية مفتوحة`),
        colorScheme: "default",
    }, ...__VLS_functionalComponentArgsRest(__VLS_13));
    /** @type {[typeof MetricCard, ]} */ ;
    // @ts-ignore
    const __VLS_16 = __VLS_asFunctionalComponent(MetricCard, new MetricCard({
        label: "مصروفات اليوم",
        value: (__VLS_ctx.formatMoney(__VLS_ctx.data.expense_today)),
        isProvisional: (__VLS_ctx.data.period.is_provisional),
        colorScheme: "amber",
    }));
    const __VLS_17 = __VLS_16({
        label: "مصروفات اليوم",
        value: (__VLS_ctx.formatMoney(__VLS_ctx.data.expense_today)),
        isProvisional: (__VLS_ctx.data.period.is_provisional),
        colorScheme: "amber",
    }, ...__VLS_functionalComponentArgsRest(__VLS_16));
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "owner-card" },
        role: "region",
        'aria-label': "ذمم فنادق B2B",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "section-label" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "metric-value text-owner-amber mb-4" },
    });
    (__VLS_ctx.formatMoney(__VLS_ctx.data.b2b_total_outstanding));
    if (__VLS_ctx.data.b2b_receivables.length === 0) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "text-xs text-owner-muted" },
        });
    }
    else {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "space-y-2" },
        });
        for (const [item] of __VLS_getVForSourceType((__VLS_ctx.data.b2b_receivables.slice(0, 5)))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (item.contract_id),
                ...{ class: "flex items-center justify-between text-xs py-1.5 border-b border-owner-border last:border-0" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "flex items-center gap-2" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "font-semibold text-owner-text" },
            });
            (item.hotel_name);
            if (item.is_overdue) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "overdue-badge" },
                });
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "font-mono text-owner-muted" },
            });
            (__VLS_ctx.formatMoney(item.outstanding));
        }
        if (__VLS_ctx.data.b2b_receivables.length > 5) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "text-xs text-owner-muted pt-2" },
            });
            (__VLS_ctx.data.b2b_receivables.length - 5);
        }
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "owner-card" },
        role: "region",
        'aria-label': "ذمم تايم شير",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "section-label" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "metric-value text-owner-red mb-4" },
    });
    (__VLS_ctx.formatMoney(__VLS_ctx.data.timeshare_total_overdue));
    if (__VLS_ctx.data.timeshare_receivables.length === 0) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "text-xs text-owner-muted" },
        });
    }
    else {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "text-xs text-owner-muted" },
        });
        (__VLS_ctx.data.timeshare_receivables.length);
        (__VLS_ctx.data.timeshare_receivables.reduce((sum, r) => sum + r.installment_count, 0));
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "owner-card" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "section-label" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "metric-value text-owner-green mb-2" },
    });
    (__VLS_ctx.formatOccupancyPct(__VLS_ctx.data.occupancy.occupancy_pct));
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "text-xs text-owner-muted" },
    });
    (__VLS_ctx.data.occupancy.occupied_rooms);
    (__VLS_ctx.data.occupancy.total_rooms);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "owner-card" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "section-label" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "metric-value text-owner-text mb-2" },
    });
    (__VLS_ctx.formatOccupancyPct(__VLS_ctx.data.beach_capacity.utilisation_pct));
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "text-xs text-owner-muted mb-2" },
    });
    (__VLS_ctx.data.beach_capacity.capacity_used);
    (__VLS_ctx.data.beach_capacity.capacity_max);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "text-xs text-owner-amber flex items-start gap-1" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    (__VLS_ctx.data.beach_capacity.note);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "text-center text-xs text-owner-muted py-4" },
    });
    (new Date(__VLS_ctx.data.period.computed_at).toLocaleTimeString('ar-EG'));
}
/** @type {__VLS_StyleScopedClasses['flex-1']} */ ;
/** @type {__VLS_StyleScopedClasses['overflow-y-auto']} */ ;
/** @type {__VLS_StyleScopedClasses['overscroll-contain']} */ ;
/** @type {__VLS_StyleScopedClasses['pb-20']} */ ;
/** @type {__VLS_StyleScopedClasses['ptr-indicator']} */ ;
/** @type {__VLS_StyleScopedClasses['p-4']} */ ;
/** @type {__VLS_StyleScopedClasses['space-y-4']} */ ;
/** @type {__VLS_StyleScopedClasses['owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['section-label']} */ ;
/** @type {__VLS_StyleScopedClasses['metric-value']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-amber']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-4']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['space-y-2']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['justify-between']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['py-1.5']} */ ;
/** @type {__VLS_StyleScopedClasses['border-b']} */ ;
/** @type {__VLS_StyleScopedClasses['border-owner-border']} */ ;
/** @type {__VLS_StyleScopedClasses['last:border-0']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-2']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['overdue-badge']} */ ;
/** @type {__VLS_StyleScopedClasses['font-mono']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['pt-2']} */ ;
/** @type {__VLS_StyleScopedClasses['owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['section-label']} */ ;
/** @type {__VLS_StyleScopedClasses['metric-value']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-red']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-4']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['section-label']} */ ;
/** @type {__VLS_StyleScopedClasses['metric-value']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-green']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-2']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['section-label']} */ ;
/** @type {__VLS_StyleScopedClasses['metric-value']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-2']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-2']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-amber']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-start']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-1']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['py-4']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            formatMoney: formatMoney,
            formatOccupancyPct: formatOccupancyPct,
            MetricCard: MetricCard,
            ErrorState: ErrorState,
            SkeletonCards: SkeletonCards,
            container: container,
            data: data,
            loading: loading,
            error: error,
            refreshing: refreshing,
            reload: reload,
        };
    },
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
});
; /* PartiallyEnd: #4569/main.vue */
