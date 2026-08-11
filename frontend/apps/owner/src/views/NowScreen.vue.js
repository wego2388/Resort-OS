/// <reference types="../../node_modules/.vue-global-types/vue_3.5_0_0_0.d.ts" />
/**
 * NowScreen — شاشة «الآن»
 * المقاييس السبعة (A-1 → A-7) من GET /api/v1/owner/now
 * Sparklines من GET /api/v1/owner/now/history?days=7
 * Auto-refresh كل 60 ثانية + pull-to-refresh
 */
import { ref, computed } from 'vue';
import { useOwnerNow, useOwnerNowHistory, useOwnerCreditReceivables, useOwnerWatchlist } from '../composables/useOwnerData';
import { formatMoney, formatOccupancyPct } from '../composables/useFormat';
import MetricCard from '../components/MetricCard.vue';
import ErrorState from '../components/ErrorState.vue';
import SkeletonCards from '../components/SkeletonCards.vue';
import SparkLine from '../components/SparkLine.vue';
import DetailSheet from '../components/DetailSheet.vue';
const container = ref(null);
const { data, loading, error, refreshing, reload } = useOwnerNow(container);
const { data: historyData } = useOwnerNowHistory(7);
const { data: creditData } = useOwnerCreditReceivables();
const watchlist = useOwnerWatchlist();
const openList = ref(null);
const listTitle = {
    b2b: 'كل ذمم فنادق B2B',
    timeshare: 'كل ذمم التايم شير المتأخرة',
    credit: 'كل الحسابات الآجلة',
};
const metricLabels = {
    revenue_today: 'إيراد اليوم',
    cash_in_drawers: 'كاش الأدراج',
    expense_today: 'مصروفات اليوم',
};
const metricColors = {
    revenue_today: 'text-owner-green',
    cash_in_drawers: 'text-owner-text',
    expense_today: 'text-owner-amber',
};
/** يحسب قيمة أي مقياس مثبّت من data الموجودة أصلًا — بدون أي fetch إضافي */
const pinnedWithValues = computed(() => {
    if (!data.value)
        return [];
    const values = {
        revenue_today: formatMoney(data.value.revenue_today),
        cash_in_drawers: formatMoney(data.value.cash_in_drawers),
        expense_today: formatMoney(data.value.expense_today),
    };
    return watchlist.items.value
        .filter(i => i.metric_key in values)
        .map(i => ({
        key: i.metric_key,
        label: i.label_override || metricLabels[i.metric_key] || i.metric_key,
        value: values[i.metric_key],
        color: metricColors[i.metric_key] ?? 'text-owner-text',
    }));
});
/** يحوّل array من DaySnapshot لـ numbers لكل sparkline */
const spark = computed(() => {
    const days = historyData.value?.days ?? [];
    return {
        revenue: days.map(d => parseFloat(d.revenue)),
        expense: days.map(d => parseFloat(d.expense)),
        cash: days.map(d => parseFloat(d.cash_in_drawers)),
        occupancy: days.map(d => parseFloat(d.occupancy_pct)),
        beach: days.map(d => parseFloat(d.beach_utilisation_pct)),
    };
});
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
    if (__VLS_ctx.pinnedWithValues.length > 0) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "owner-card" },
            role: "region",
            'aria-label': "المفضلة",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-label mb-3" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "grid grid-cols-2 gap-3" },
        });
        for (const [m] of __VLS_getVForSourceType((__VLS_ctx.pinnedWithValues))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (m.key),
                ...{ class: "text-center" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "font-bold text-lg" },
                ...{ class: (m.color) },
            });
            (m.value);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "text-xs text-owner-muted mt-0.5" },
            });
            (m.label);
        }
    }
    /** @type {[typeof MetricCard, ]} */ ;
    // @ts-ignore
    const __VLS_10 = __VLS_asFunctionalComponent(MetricCard, new MetricCard({
        ...{ 'onTogglePin': {} },
        label: "إيراد اليوم",
        value: (__VLS_ctx.formatMoney(__VLS_ctx.data.revenue_today)),
        isProvisional: (__VLS_ctx.data.period.is_provisional),
        sparkValues: (__VLS_ctx.spark.revenue),
        colorScheme: "green",
        pinned: (__VLS_ctx.watchlist.isPinned('revenue_today')),
    }));
    const __VLS_11 = __VLS_10({
        ...{ 'onTogglePin': {} },
        label: "إيراد اليوم",
        value: (__VLS_ctx.formatMoney(__VLS_ctx.data.revenue_today)),
        isProvisional: (__VLS_ctx.data.period.is_provisional),
        sparkValues: (__VLS_ctx.spark.revenue),
        colorScheme: "green",
        pinned: (__VLS_ctx.watchlist.isPinned('revenue_today')),
    }, ...__VLS_functionalComponentArgsRest(__VLS_10));
    let __VLS_13;
    let __VLS_14;
    let __VLS_15;
    const __VLS_16 = {
        onTogglePin: (...[$event]) => {
            if (!!(__VLS_ctx.error && !__VLS_ctx.loading))
                return;
            if (!!(__VLS_ctx.loading && !__VLS_ctx.data))
                return;
            if (!(__VLS_ctx.data))
                return;
            __VLS_ctx.watchlist.togglePin('revenue_today');
        }
    };
    var __VLS_12;
    /** @type {[typeof MetricCard, ]} */ ;
    // @ts-ignore
    const __VLS_17 = __VLS_asFunctionalComponent(MetricCard, new MetricCard({
        ...{ 'onTogglePin': {} },
        label: "كاش الأدراج المتوقع",
        value: (__VLS_ctx.formatMoney(__VLS_ctx.data.cash_in_drawers)),
        subtitle: (`${__VLS_ctx.data.open_shift_count} وردية مفتوحة`),
        sparkValues: (__VLS_ctx.spark.cash),
        colorScheme: "default",
        pinned: (__VLS_ctx.watchlist.isPinned('cash_in_drawers')),
    }));
    const __VLS_18 = __VLS_17({
        ...{ 'onTogglePin': {} },
        label: "كاش الأدراج المتوقع",
        value: (__VLS_ctx.formatMoney(__VLS_ctx.data.cash_in_drawers)),
        subtitle: (`${__VLS_ctx.data.open_shift_count} وردية مفتوحة`),
        sparkValues: (__VLS_ctx.spark.cash),
        colorScheme: "default",
        pinned: (__VLS_ctx.watchlist.isPinned('cash_in_drawers')),
    }, ...__VLS_functionalComponentArgsRest(__VLS_17));
    let __VLS_20;
    let __VLS_21;
    let __VLS_22;
    const __VLS_23 = {
        onTogglePin: (...[$event]) => {
            if (!!(__VLS_ctx.error && !__VLS_ctx.loading))
                return;
            if (!!(__VLS_ctx.loading && !__VLS_ctx.data))
                return;
            if (!(__VLS_ctx.data))
                return;
            __VLS_ctx.watchlist.togglePin('cash_in_drawers');
        }
    };
    var __VLS_19;
    /** @type {[typeof MetricCard, ]} */ ;
    // @ts-ignore
    const __VLS_24 = __VLS_asFunctionalComponent(MetricCard, new MetricCard({
        ...{ 'onTogglePin': {} },
        label: "مصروفات اليوم",
        value: (__VLS_ctx.formatMoney(__VLS_ctx.data.expense_today)),
        isProvisional: (__VLS_ctx.data.period.is_provisional),
        sparkValues: (__VLS_ctx.spark.expense),
        colorScheme: "amber",
        pinned: (__VLS_ctx.watchlist.isPinned('expense_today')),
    }));
    const __VLS_25 = __VLS_24({
        ...{ 'onTogglePin': {} },
        label: "مصروفات اليوم",
        value: (__VLS_ctx.formatMoney(__VLS_ctx.data.expense_today)),
        isProvisional: (__VLS_ctx.data.period.is_provisional),
        sparkValues: (__VLS_ctx.spark.expense),
        colorScheme: "amber",
        pinned: (__VLS_ctx.watchlist.isPinned('expense_today')),
    }, ...__VLS_functionalComponentArgsRest(__VLS_24));
    let __VLS_27;
    let __VLS_28;
    let __VLS_29;
    const __VLS_30 = {
        onTogglePin: (...[$event]) => {
            if (!!(__VLS_ctx.error && !__VLS_ctx.loading))
                return;
            if (!!(__VLS_ctx.loading && !__VLS_ctx.data))
                return;
            if (!(__VLS_ctx.data))
                return;
            __VLS_ctx.watchlist.togglePin('expense_today');
        }
    };
    var __VLS_26;
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
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!!(__VLS_ctx.error && !__VLS_ctx.loading))
                            return;
                        if (!!(__VLS_ctx.loading && !__VLS_ctx.data))
                            return;
                        if (!(__VLS_ctx.data))
                            return;
                        if (!!(__VLS_ctx.data.b2b_receivables.length === 0))
                            return;
                        if (!(__VLS_ctx.data.b2b_receivables.length > 5))
                            return;
                        __VLS_ctx.openList = 'b2b';
                    } },
                ...{ class: "w-full text-xs text-owner-green font-semibold pt-2 text-center active:opacity-70" },
            });
            (__VLS_ctx.data.b2b_receivables.length);
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
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!!(__VLS_ctx.error && !__VLS_ctx.loading))
                        return;
                    if (!!(__VLS_ctx.loading && !__VLS_ctx.data))
                        return;
                    if (!(__VLS_ctx.data))
                        return;
                    if (!!(__VLS_ctx.data.timeshare_receivables.length === 0))
                        return;
                    __VLS_ctx.openList = 'timeshare';
                } },
            ...{ class: "w-full flex items-center justify-between text-xs text-owner-muted active:opacity-70" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.data.timeshare_receivables.length);
        (__VLS_ctx.data.timeshare_receivables.reduce((sum, r) => sum + r.installment_count, 0));
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: "text-owner-green font-semibold" },
        });
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "owner-card" },
        role: "region",
        'aria-label': "ذمم الحسابات الآجلة الشخصية",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "section-label" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "metric-value text-owner-amber mb-1" },
    });
    (__VLS_ctx.formatMoney(__VLS_ctx.data.credit_account_outstanding));
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "text-xs text-owner-muted mb-3" },
    });
    (__VLS_ctx.data.credit_account_count);
    if (__VLS_ctx.creditData?.overdue_count) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.creditData.overdue_count);
    }
    if (__VLS_ctx.creditData?.accounts.length) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "space-y-2" },
        });
        for (const [account] of __VLS_getVForSourceType((__VLS_ctx.creditData.accounts.slice(0, 5)))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                key: (account.account_id),
                ...{ class: "flex items-center justify-between border-b border-owner-border py-1.5 text-xs last:border-0" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "flex items-center gap-2" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "font-semibold text-owner-text" },
            });
            (account.holder_name);
            if (account.is_overdue) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "overdue-badge" },
                });
            }
            if (account.status === 'suspended') {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "text-owner-amber" },
                });
            }
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "font-mono text-owner-muted" },
            });
            (__VLS_ctx.formatMoney(account.current_balance));
        }
    }
    else {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "text-xs text-owner-muted" },
        });
    }
    if (__VLS_ctx.creditData && __VLS_ctx.creditData.accounts.length > 5) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!!(__VLS_ctx.error && !__VLS_ctx.loading))
                        return;
                    if (!!(__VLS_ctx.loading && !__VLS_ctx.data))
                        return;
                    if (!(__VLS_ctx.data))
                        return;
                    if (!(__VLS_ctx.creditData && __VLS_ctx.creditData.accounts.length > 5))
                        return;
                    __VLS_ctx.openList = 'credit';
                } },
            ...{ class: "w-full text-xs text-owner-green font-semibold pt-2 text-center active:opacity-70" },
        });
        (__VLS_ctx.creditData.accounts.length);
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
        ...{ class: "text-xs text-owner-muted mb-2" },
    });
    (__VLS_ctx.data.occupancy.occupied_rooms);
    (__VLS_ctx.data.occupancy.total_rooms);
    if (__VLS_ctx.spark.occupancy.length > 1) {
        /** @type {[typeof SparkLine, ]} */ ;
        // @ts-ignore
        const __VLS_31 = __VLS_asFunctionalComponent(SparkLine, new SparkLine({
            values: (__VLS_ctx.spark.occupancy),
        }));
        const __VLS_32 = __VLS_31({
            values: (__VLS_ctx.spark.occupancy),
        }, ...__VLS_functionalComponentArgsRest(__VLS_31));
    }
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
    if (__VLS_ctx.spark.beach.length > 1) {
        /** @type {[typeof SparkLine, ]} */ ;
        // @ts-ignore
        const __VLS_34 = __VLS_asFunctionalComponent(SparkLine, new SparkLine({
            values: (__VLS_ctx.spark.beach),
            ...{ class: "mb-2" },
        }));
        const __VLS_35 = __VLS_34({
            values: (__VLS_ctx.spark.beach),
            ...{ class: "mb-2" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_34));
    }
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
/** @type {[typeof DetailSheet, typeof DetailSheet, ]} */ ;
// @ts-ignore
const __VLS_37 = __VLS_asFunctionalComponent(DetailSheet, new DetailSheet({
    ...{ 'onClose': {} },
    open: (__VLS_ctx.openList === 'b2b'),
    title: (__VLS_ctx.listTitle.b2b),
}));
const __VLS_38 = __VLS_37({
    ...{ 'onClose': {} },
    open: (__VLS_ctx.openList === 'b2b'),
    title: (__VLS_ctx.listTitle.b2b),
}, ...__VLS_functionalComponentArgsRest(__VLS_37));
let __VLS_40;
let __VLS_41;
let __VLS_42;
const __VLS_43 = {
    onClose: (...[$event]) => {
        __VLS_ctx.openList = null;
    }
};
__VLS_39.slots.default;
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "space-y-1" },
});
for (const [item] of __VLS_getVForSourceType((__VLS_ctx.data?.b2b_receivables ?? []))) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        key: (item.contract_id),
        ...{ class: "flex items-center justify-between py-2.5 border-b border-owner-border/50 last:border-0 text-xs" },
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
        ...{ class: "font-mono text-owner-text font-semibold" },
    });
    (__VLS_ctx.formatMoney(item.outstanding));
}
var __VLS_39;
/** @type {[typeof DetailSheet, typeof DetailSheet, ]} */ ;
// @ts-ignore
const __VLS_44 = __VLS_asFunctionalComponent(DetailSheet, new DetailSheet({
    ...{ 'onClose': {} },
    open: (__VLS_ctx.openList === 'timeshare'),
    title: (__VLS_ctx.listTitle.timeshare),
}));
const __VLS_45 = __VLS_44({
    ...{ 'onClose': {} },
    open: (__VLS_ctx.openList === 'timeshare'),
    title: (__VLS_ctx.listTitle.timeshare),
}, ...__VLS_functionalComponentArgsRest(__VLS_44));
let __VLS_47;
let __VLS_48;
let __VLS_49;
const __VLS_50 = {
    onClose: (...[$event]) => {
        __VLS_ctx.openList = null;
    }
};
__VLS_46.slots.default;
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "space-y-1" },
});
for (const [item] of __VLS_getVForSourceType((__VLS_ctx.data?.timeshare_receivables ?? []))) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        key: (item.contract_id),
        ...{ class: "flex items-center justify-between py-2.5 border-b border-owner-border/50 last:border-0 text-xs" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "font-semibold text-owner-text" },
    });
    (item.contract_id);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "text-left" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "font-mono text-owner-red font-semibold" },
    });
    (__VLS_ctx.formatMoney(item.total_overdue));
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "text-owner-muted" },
    });
    (item.installment_count);
}
var __VLS_46;
/** @type {[typeof DetailSheet, typeof DetailSheet, ]} */ ;
// @ts-ignore
const __VLS_51 = __VLS_asFunctionalComponent(DetailSheet, new DetailSheet({
    ...{ 'onClose': {} },
    open: (__VLS_ctx.openList === 'credit'),
    title: (__VLS_ctx.listTitle.credit),
}));
const __VLS_52 = __VLS_51({
    ...{ 'onClose': {} },
    open: (__VLS_ctx.openList === 'credit'),
    title: (__VLS_ctx.listTitle.credit),
}, ...__VLS_functionalComponentArgsRest(__VLS_51));
let __VLS_54;
let __VLS_55;
let __VLS_56;
const __VLS_57 = {
    onClose: (...[$event]) => {
        __VLS_ctx.openList = null;
    }
};
__VLS_53.slots.default;
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "space-y-1" },
});
for (const [account] of __VLS_getVForSourceType((__VLS_ctx.creditData?.accounts ?? []))) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        key: (account.account_id),
        ...{ class: "flex items-center justify-between py-2.5 border-b border-owner-border/50 last:border-0 text-xs" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "flex items-center gap-2" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
        ...{ class: "font-semibold text-owner-text" },
    });
    (account.holder_name);
    if (account.is_overdue) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: "overdue-badge" },
        });
    }
    if (account.status === 'suspended') {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
            ...{ class: "text-owner-amber" },
        });
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
        ...{ class: "font-mono text-owner-text font-semibold" },
    });
    (__VLS_ctx.formatMoney(account.current_balance));
}
var __VLS_53;
/** @type {__VLS_StyleScopedClasses['flex-1']} */ ;
/** @type {__VLS_StyleScopedClasses['overflow-y-auto']} */ ;
/** @type {__VLS_StyleScopedClasses['overscroll-contain']} */ ;
/** @type {__VLS_StyleScopedClasses['pb-20']} */ ;
/** @type {__VLS_StyleScopedClasses['ptr-indicator']} */ ;
/** @type {__VLS_StyleScopedClasses['p-4']} */ ;
/** @type {__VLS_StyleScopedClasses['space-y-4']} */ ;
/** @type {__VLS_StyleScopedClasses['owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['section-label']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-3']} */ ;
/** @type {__VLS_StyleScopedClasses['grid']} */ ;
/** @type {__VLS_StyleScopedClasses['grid-cols-2']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-3']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['font-bold']} */ ;
/** @type {__VLS_StyleScopedClasses['text-lg']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['mt-0.5']} */ ;
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
/** @type {__VLS_StyleScopedClasses['w-full']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-green']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['pt-2']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['active:opacity-70']} */ ;
/** @type {__VLS_StyleScopedClasses['owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['section-label']} */ ;
/** @type {__VLS_StyleScopedClasses['metric-value']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-red']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-4']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['w-full']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['justify-between']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['active:opacity-70']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-green']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['section-label']} */ ;
/** @type {__VLS_StyleScopedClasses['metric-value']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-amber']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-1']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-3']} */ ;
/** @type {__VLS_StyleScopedClasses['space-y-2']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['justify-between']} */ ;
/** @type {__VLS_StyleScopedClasses['border-b']} */ ;
/** @type {__VLS_StyleScopedClasses['border-owner-border']} */ ;
/** @type {__VLS_StyleScopedClasses['py-1.5']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['last:border-0']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-2']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['overdue-badge']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-amber']} */ ;
/** @type {__VLS_StyleScopedClasses['font-mono']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['w-full']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-green']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['pt-2']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['active:opacity-70']} */ ;
/** @type {__VLS_StyleScopedClasses['owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['section-label']} */ ;
/** @type {__VLS_StyleScopedClasses['metric-value']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-green']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-2']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-2']} */ ;
/** @type {__VLS_StyleScopedClasses['owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['section-label']} */ ;
/** @type {__VLS_StyleScopedClasses['metric-value']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-2']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-2']} */ ;
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
/** @type {__VLS_StyleScopedClasses['space-y-1']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['justify-between']} */ ;
/** @type {__VLS_StyleScopedClasses['py-2.5']} */ ;
/** @type {__VLS_StyleScopedClasses['border-b']} */ ;
/** @type {__VLS_StyleScopedClasses['border-owner-border/50']} */ ;
/** @type {__VLS_StyleScopedClasses['last:border-0']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-2']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['overdue-badge']} */ ;
/** @type {__VLS_StyleScopedClasses['font-mono']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['space-y-1']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['justify-between']} */ ;
/** @type {__VLS_StyleScopedClasses['py-2.5']} */ ;
/** @type {__VLS_StyleScopedClasses['border-b']} */ ;
/** @type {__VLS_StyleScopedClasses['border-owner-border/50']} */ ;
/** @type {__VLS_StyleScopedClasses['last:border-0']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['text-left']} */ ;
/** @type {__VLS_StyleScopedClasses['font-mono']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-red']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['space-y-1']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['justify-between']} */ ;
/** @type {__VLS_StyleScopedClasses['py-2.5']} */ ;
/** @type {__VLS_StyleScopedClasses['border-b']} */ ;
/** @type {__VLS_StyleScopedClasses['border-owner-border/50']} */ ;
/** @type {__VLS_StyleScopedClasses['last:border-0']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-2']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['overdue-badge']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-amber']} */ ;
/** @type {__VLS_StyleScopedClasses['font-mono']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            formatMoney: formatMoney,
            formatOccupancyPct: formatOccupancyPct,
            MetricCard: MetricCard,
            ErrorState: ErrorState,
            SkeletonCards: SkeletonCards,
            SparkLine: SparkLine,
            DetailSheet: DetailSheet,
            container: container,
            data: data,
            loading: loading,
            error: error,
            refreshing: refreshing,
            reload: reload,
            creditData: creditData,
            watchlist: watchlist,
            openList: openList,
            listTitle: listTitle,
            pinnedWithValues: pinnedWithValues,
            spark: spark,
        };
    },
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
});
; /* PartiallyEnd: #4569/main.vue */
