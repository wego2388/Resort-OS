/// <reference types="../../node_modules/.vue-global-types/vue_3.5_0_0_0.d.ts" />
/**
 * ExpensesScreen — Phase 6 + 7b
 * D-1: كل فئة مصروف كنسبة % من الإيراد مع variance flags
 * E-1: تركّز الإنفاق بالموردين
 * DateRangePicker للتحكم في الفترة (Decision 0004 §7b)
 */
import { ref, computed } from 'vue';
import { useOwnerExpenseAnalytics, useOwnerProcurementAnalytics, useDetailSheet } from '../composables/useOwnerData';
import { fetchExpenseDetail, fetchSupplierDetail } from '../api/owner';
import { formatMoney, formatMoneyFull, formatPct } from '../composables/useFormat';
import ErrorState from '../components/ErrorState.vue';
import SkeletonCards from '../components/SkeletonCards.vue';
import DateRangePicker from '../components/DateRangePicker.vue';
import DetailSheet from '../components/DetailSheet.vue';
const tabs = ['expenses', 'procurement'];
const activeTab = ref('expenses');
const tabLabels = { expenses: 'المصروفات', procurement: 'المشتريات' };
const dateRange = ref(null);
const expParams = computed(() => ({ date_from: dateRange.value?.date_from, date_to: dateRange.value?.date_to }));
const procParams = computed(() => ({ date_from: dateRange.value?.date_from, date_to: dateRange.value?.date_to }));
const { data: expData, loading: expLoading, error: expError, reload: expReload, updateParams: updateExp } = useOwnerExpenseAnalytics(expParams);
const { data: procData, loading: procLoading, error: procError, reload: procReload, updateParams: updateProc } = useOwnerProcurementAnalytics(procParams);
function onDateChange(range) {
    dateRange.value = range;
    updateExp(expParams.value);
    updateProc(procParams.value);
}
// ── تفاصيل التفاصيل (Phase 8) ─────────────────────────────────────────
const expenseDetail = useDetailSheet();
function openExpenseDetail(accountCode) {
    expenseDetail.open(() => fetchExpenseDetail({
        account_code: accountCode,
        date_from: dateRange.value?.date_from,
        date_to: dateRange.value?.date_to,
    }));
}
const supplierDetail = useDetailSheet();
function openSupplierDetail(supplierId) {
    supplierDetail.open(() => fetchSupplierDetail({
        supplier_id: supplierId,
        date_from: dateRange.value?.date_from,
        date_to: dateRange.value?.date_to,
    }));
}
function formatDate(d) {
    return new Date(d).toLocaleDateString('ar-EG', { month: 'short', day: 'numeric' });
}
const poStatusLabel = { received: 'مستلم', partial: 'مستلم جزئيًا' };
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "flex-1 flex flex-col overflow-hidden" },
});
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
    ...{ class: "flex-1 overflow-y-auto overscroll-contain p-4 space-y-4" },
});
/** @type {[typeof DateRangePicker, ]} */ ;
// @ts-ignore
const __VLS_0 = __VLS_asFunctionalComponent(DateRangePicker, new DateRangePicker({
    ...{ 'onChange': {} },
}));
const __VLS_1 = __VLS_0({
    ...{ 'onChange': {} },
}, ...__VLS_functionalComponentArgsRest(__VLS_0));
let __VLS_3;
let __VLS_4;
let __VLS_5;
const __VLS_6 = {
    onChange: (__VLS_ctx.onDateChange)
};
var __VLS_2;
if (__VLS_ctx.activeTab === 'expenses') {
    if (__VLS_ctx.expError && !__VLS_ctx.expLoading) {
        /** @type {[typeof ErrorState, ]} */ ;
        // @ts-ignore
        const __VLS_7 = __VLS_asFunctionalComponent(ErrorState, new ErrorState({
            ...{ 'onRetry': {} },
            message: (__VLS_ctx.expError),
        }));
        const __VLS_8 = __VLS_7({
            ...{ 'onRetry': {} },
            message: (__VLS_ctx.expError),
        }, ...__VLS_functionalComponentArgsRest(__VLS_7));
        let __VLS_10;
        let __VLS_11;
        let __VLS_12;
        const __VLS_13 = {
            onRetry: (__VLS_ctx.expReload)
        };
        var __VLS_9;
    }
    else if (__VLS_ctx.expLoading && !__VLS_ctx.expData) {
        /** @type {[typeof SkeletonCards, ]} */ ;
        // @ts-ignore
        const __VLS_14 = __VLS_asFunctionalComponent(SkeletonCards, new SkeletonCards({}));
        const __VLS_15 = __VLS_14({}, ...__VLS_functionalComponentArgsRest(__VLS_14));
    }
    else if (__VLS_ctx.expData) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "owner-card" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-label" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "metric-value text-owner-green" },
        });
        (__VLS_ctx.formatMoney(__VLS_ctx.expData.current_revenue));
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "text-xs text-owner-muted mt-1" },
        });
        (__VLS_ctx.expData.period_from);
        (__VLS_ctx.expData.period_to);
        if (__VLS_ctx.expData.is_provisional) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "text-owner-amber ml-2" },
            });
        }
        if (__VLS_ctx.expData.payroll) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "owner-card" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "section-label" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "metric-value text-owner-amber" },
            });
            (__VLS_ctx.formatMoney(__VLS_ctx.expData.payroll.total_net));
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "text-xs text-owner-muted mt-1" },
            });
            (__VLS_ctx.formatPct(__VLS_ctx.expData.payroll.payroll_pct));
            (__VLS_ctx.expData.payroll.period_year);
            (__VLS_ctx.expData.payroll.period_month);
        }
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "owner-card" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-label mb-3" },
        });
        if (__VLS_ctx.expData.expense_lines.length === 0) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "text-xs text-owner-muted text-center py-4" },
            });
        }
        else {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "space-y-1" },
            });
            for (const [line] of __VLS_getVForSourceType((__VLS_ctx.expData.expense_lines))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!(__VLS_ctx.activeTab === 'expenses'))
                                return;
                            if (!!(__VLS_ctx.expError && !__VLS_ctx.expLoading))
                                return;
                            if (!!(__VLS_ctx.expLoading && !__VLS_ctx.expData))
                                return;
                            if (!(__VLS_ctx.expData))
                                return;
                            if (!!(__VLS_ctx.expData.expense_lines.length === 0))
                                return;
                            __VLS_ctx.openExpenseDetail(line.account_code);
                        } },
                    key: (line.account_code),
                    ...{ class: "w-full py-2 border-b border-owner-border/50 last:border-0 text-right active:bg-owner-card transition-colors rounded-lg -mx-1 px-1" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "flex items-center justify-between" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "flex items-center gap-2" },
                });
                if (line.variance_flag) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                        ...{ class: "text-owner-red text-xs" },
                        title: "variance",
                    });
                }
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "text-sm text-owner-text" },
                });
                (line.account_name);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "font-mono font-semibold text-owner-text" },
                });
                (__VLS_ctx.formatMoney(line.current_amount));
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "flex justify-between text-xs text-owner-muted mt-0.5" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
                (__VLS_ctx.formatPct(line.current_pct));
                if (line.variance_delta != null) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                        ...{ class: (parseFloat(line.variance_delta) > 0 ? 'text-owner-red' : 'text-owner-green') },
                    });
                    (parseFloat(line.variance_delta) > 0 ? '↑' : '↓');
                    (__VLS_ctx.formatPct(line.variance_delta));
                }
            }
        }
    }
}
else {
    if (__VLS_ctx.procError && !__VLS_ctx.procLoading) {
        /** @type {[typeof ErrorState, ]} */ ;
        // @ts-ignore
        const __VLS_17 = __VLS_asFunctionalComponent(ErrorState, new ErrorState({
            ...{ 'onRetry': {} },
            message: (__VLS_ctx.procError),
        }));
        const __VLS_18 = __VLS_17({
            ...{ 'onRetry': {} },
            message: (__VLS_ctx.procError),
        }, ...__VLS_functionalComponentArgsRest(__VLS_17));
        let __VLS_20;
        let __VLS_21;
        let __VLS_22;
        const __VLS_23 = {
            onRetry: (__VLS_ctx.procReload)
        };
        var __VLS_19;
    }
    else if (__VLS_ctx.procLoading && !__VLS_ctx.procData) {
        /** @type {[typeof SkeletonCards, ]} */ ;
        // @ts-ignore
        const __VLS_24 = __VLS_asFunctionalComponent(SkeletonCards, new SkeletonCards({}));
        const __VLS_25 = __VLS_24({}, ...__VLS_functionalComponentArgsRest(__VLS_24));
    }
    else if (__VLS_ctx.procData) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "owner-card" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-label" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "metric-value text-owner-amber" },
        });
        (__VLS_ctx.formatMoney(__VLS_ctx.procData.total_spend));
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "text-xs text-owner-muted mt-1" },
        });
        (__VLS_ctx.procData.period_from);
        (__VLS_ctx.procData.period_to);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "owner-card" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "section-label mb-3" },
        });
        if (__VLS_ctx.procData.suppliers.length === 0) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "text-xs text-owner-muted text-center py-4" },
            });
        }
        else {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "space-y-2" },
            });
            for (const [sup] of __VLS_getVForSourceType((__VLS_ctx.procData.suppliers))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                    ...{ onClick: (...[$event]) => {
                            if (!!(__VLS_ctx.activeTab === 'expenses'))
                                return;
                            if (!!(__VLS_ctx.procError && !__VLS_ctx.procLoading))
                                return;
                            if (!!(__VLS_ctx.procLoading && !__VLS_ctx.procData))
                                return;
                            if (!(__VLS_ctx.procData))
                                return;
                            if (!!(__VLS_ctx.procData.suppliers.length === 0))
                                return;
                            __VLS_ctx.openSupplierDetail(sup.supplier_id);
                        } },
                    key: (sup.supplier_id),
                    ...{ class: "w-full flex items-center justify-between py-2 border-b border-owner-border last:border-0 text-right active:bg-owner-card transition-colors rounded-lg -mx-1 px-1" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "flex items-center gap-2" },
                });
                if (sup.concentration_flag) {
                    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                        ...{ class: "text-owner-red text-xs" },
                    });
                }
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "text-sm font-semibold text-owner-text" },
                });
                (sup.supplier_name);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "text-xs text-owner-muted" },
                });
                (sup.order_count);
                (__VLS_ctx.formatPct(sup.spend_pct));
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "flex items-center gap-1" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "font-mono font-bold text-owner-text" },
                });
                (__VLS_ctx.formatMoney(sup.total_spend));
                __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                    ...{ class: "text-owner-muted" },
                    'aria-hidden': "true",
                });
            }
        }
        if (__VLS_ctx.procData.pr_po_variance.length > 0) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "owner-card" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "section-label mb-3" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "space-y-2" },
            });
            for (const [row] of __VLS_getVForSourceType((__VLS_ctx.procData.pr_po_variance))) {
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    key: (row.product_id),
                    ...{ class: "flex items-center justify-between py-2 border-b border-owner-border last:border-0 text-xs" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "font-semibold text-owner-text" },
                });
                (row.product_name);
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "text-owner-muted" },
                });
                (__VLS_ctx.formatMoney(row.estimated_cost));
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "text-right" },
                });
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: "font-mono text-owner-text" },
                });
                (__VLS_ctx.formatMoney(row.actual_cost));
                __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                    ...{ class: (parseFloat(row.variance_amount) > 0 ? 'text-owner-red' : 'text-owner-green') },
                });
                (parseFloat(row.variance_amount) > 0 ? '+' : '');
                (__VLS_ctx.formatMoney(row.variance_amount));
            }
        }
    }
}
/** @type {[typeof DetailSheet, typeof DetailSheet, ]} */ ;
// @ts-ignore
const __VLS_27 = __VLS_asFunctionalComponent(DetailSheet, new DetailSheet({
    ...{ 'onClose': {} },
    ...{ 'onRetry': {} },
    open: (__VLS_ctx.expenseDetail.isOpen.value),
    title: (__VLS_ctx.expenseDetail.data.value?.account_name ?? 'تفاصيل المصروف'),
    subtitle: (__VLS_ctx.expenseDetail.data.value ? __VLS_ctx.formatMoney(__VLS_ctx.expenseDetail.data.value.total_amount) : undefined),
    loading: (__VLS_ctx.expenseDetail.loading.value),
    error: (__VLS_ctx.expenseDetail.error.value),
}));
const __VLS_28 = __VLS_27({
    ...{ 'onClose': {} },
    ...{ 'onRetry': {} },
    open: (__VLS_ctx.expenseDetail.isOpen.value),
    title: (__VLS_ctx.expenseDetail.data.value?.account_name ?? 'تفاصيل المصروف'),
    subtitle: (__VLS_ctx.expenseDetail.data.value ? __VLS_ctx.formatMoney(__VLS_ctx.expenseDetail.data.value.total_amount) : undefined),
    loading: (__VLS_ctx.expenseDetail.loading.value),
    error: (__VLS_ctx.expenseDetail.error.value),
}, ...__VLS_functionalComponentArgsRest(__VLS_27));
let __VLS_30;
let __VLS_31;
let __VLS_32;
const __VLS_33 = {
    onClose: (...[$event]) => {
        __VLS_ctx.expenseDetail.close();
    }
};
const __VLS_34 = {
    onRetry: (...[$event]) => {
        __VLS_ctx.expenseDetail.retry();
    }
};
__VLS_29.slots.default;
if (__VLS_ctx.expenseDetail.data.value?.lines.length === 0) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "text-xs text-owner-muted text-center py-8" },
    });
}
else {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "space-y-1" },
    });
    for (const [line] of __VLS_getVForSourceType((__VLS_ctx.expenseDetail.data.value?.lines ?? []))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            key: (line.entry_id),
            ...{ class: "flex items-center justify-between py-2.5 border-b border-owner-border/50 last:border-0 text-xs" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "min-w-0" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "font-semibold text-owner-text truncate" },
        });
        (line.description);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "text-owner-muted mt-0.5" },
        });
        (line.reference);
        (__VLS_ctx.formatDate(line.entry_date));
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "font-mono font-semibold text-owner-text shrink-0" },
        });
        (__VLS_ctx.formatMoneyFull(line.amount));
    }
}
var __VLS_29;
/** @type {[typeof DetailSheet, typeof DetailSheet, ]} */ ;
// @ts-ignore
const __VLS_35 = __VLS_asFunctionalComponent(DetailSheet, new DetailSheet({
    ...{ 'onClose': {} },
    ...{ 'onRetry': {} },
    open: (__VLS_ctx.supplierDetail.isOpen.value),
    title: (__VLS_ctx.supplierDetail.data.value?.supplier_name ?? 'تفاصيل المورد'),
    subtitle: (__VLS_ctx.supplierDetail.data.value ? `${__VLS_ctx.supplierDetail.data.value.orders.length} أمر شراء · ${__VLS_ctx.formatMoney(__VLS_ctx.supplierDetail.data.value.total_amount)}` : undefined),
    loading: (__VLS_ctx.supplierDetail.loading.value),
    error: (__VLS_ctx.supplierDetail.error.value),
}));
const __VLS_36 = __VLS_35({
    ...{ 'onClose': {} },
    ...{ 'onRetry': {} },
    open: (__VLS_ctx.supplierDetail.isOpen.value),
    title: (__VLS_ctx.supplierDetail.data.value?.supplier_name ?? 'تفاصيل المورد'),
    subtitle: (__VLS_ctx.supplierDetail.data.value ? `${__VLS_ctx.supplierDetail.data.value.orders.length} أمر شراء · ${__VLS_ctx.formatMoney(__VLS_ctx.supplierDetail.data.value.total_amount)}` : undefined),
    loading: (__VLS_ctx.supplierDetail.loading.value),
    error: (__VLS_ctx.supplierDetail.error.value),
}, ...__VLS_functionalComponentArgsRest(__VLS_35));
let __VLS_38;
let __VLS_39;
let __VLS_40;
const __VLS_41 = {
    onClose: (...[$event]) => {
        __VLS_ctx.supplierDetail.close();
    }
};
const __VLS_42 = {
    onRetry: (...[$event]) => {
        __VLS_ctx.supplierDetail.retry();
    }
};
__VLS_37.slots.default;
if (__VLS_ctx.supplierDetail.data.value?.orders.length === 0) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "text-xs text-owner-muted text-center py-8" },
    });
}
else {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "space-y-1" },
    });
    for (const [po] of __VLS_getVForSourceType((__VLS_ctx.supplierDetail.data.value?.orders ?? []))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            key: (po.po_id),
            ...{ class: "flex items-center justify-between py-2.5 border-b border-owner-border/50 last:border-0 text-xs" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "font-semibold text-owner-text" },
        });
        (po.po_number);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "text-owner-muted mt-0.5" },
        });
        (__VLS_ctx.poStatusLabel[po.status] ?? po.status);
        (po.item_count);
        (__VLS_ctx.formatDate(po.ordered_at));
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "font-mono font-semibold text-owner-text" },
        });
        (__VLS_ctx.formatMoneyFull(po.total_amount));
    }
}
var __VLS_37;
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
/** @type {__VLS_StyleScopedClasses['space-y-4']} */ ;
/** @type {__VLS_StyleScopedClasses['owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['section-label']} */ ;
/** @type {__VLS_StyleScopedClasses['metric-value']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-green']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['mt-1']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-amber']} */ ;
/** @type {__VLS_StyleScopedClasses['ml-2']} */ ;
/** @type {__VLS_StyleScopedClasses['owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['section-label']} */ ;
/** @type {__VLS_StyleScopedClasses['metric-value']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-amber']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['mt-1']} */ ;
/** @type {__VLS_StyleScopedClasses['owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['section-label']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-3']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['py-4']} */ ;
/** @type {__VLS_StyleScopedClasses['space-y-1']} */ ;
/** @type {__VLS_StyleScopedClasses['w-full']} */ ;
/** @type {__VLS_StyleScopedClasses['py-2']} */ ;
/** @type {__VLS_StyleScopedClasses['border-b']} */ ;
/** @type {__VLS_StyleScopedClasses['border-owner-border/50']} */ ;
/** @type {__VLS_StyleScopedClasses['last:border-0']} */ ;
/** @type {__VLS_StyleScopedClasses['text-right']} */ ;
/** @type {__VLS_StyleScopedClasses['active:bg-owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['transition-colors']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-lg']} */ ;
/** @type {__VLS_StyleScopedClasses['-mx-1']} */ ;
/** @type {__VLS_StyleScopedClasses['px-1']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['justify-between']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-2']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-red']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-sm']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['font-mono']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['justify-between']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['mt-0.5']} */ ;
/** @type {__VLS_StyleScopedClasses['owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['section-label']} */ ;
/** @type {__VLS_StyleScopedClasses['metric-value']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-amber']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['mt-1']} */ ;
/** @type {__VLS_StyleScopedClasses['owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['section-label']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-3']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['py-4']} */ ;
/** @type {__VLS_StyleScopedClasses['space-y-2']} */ ;
/** @type {__VLS_StyleScopedClasses['w-full']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['justify-between']} */ ;
/** @type {__VLS_StyleScopedClasses['py-2']} */ ;
/** @type {__VLS_StyleScopedClasses['border-b']} */ ;
/** @type {__VLS_StyleScopedClasses['border-owner-border']} */ ;
/** @type {__VLS_StyleScopedClasses['last:border-0']} */ ;
/** @type {__VLS_StyleScopedClasses['text-right']} */ ;
/** @type {__VLS_StyleScopedClasses['active:bg-owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['transition-colors']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-lg']} */ ;
/** @type {__VLS_StyleScopedClasses['-mx-1']} */ ;
/** @type {__VLS_StyleScopedClasses['px-1']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-2']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-red']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-sm']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-1']} */ ;
/** @type {__VLS_StyleScopedClasses['font-mono']} */ ;
/** @type {__VLS_StyleScopedClasses['font-bold']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['section-label']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-3']} */ ;
/** @type {__VLS_StyleScopedClasses['space-y-2']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['justify-between']} */ ;
/** @type {__VLS_StyleScopedClasses['py-2']} */ ;
/** @type {__VLS_StyleScopedClasses['border-b']} */ ;
/** @type {__VLS_StyleScopedClasses['border-owner-border']} */ ;
/** @type {__VLS_StyleScopedClasses['last:border-0']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['text-right']} */ ;
/** @type {__VLS_StyleScopedClasses['font-mono']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['py-8']} */ ;
/** @type {__VLS_StyleScopedClasses['space-y-1']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['justify-between']} */ ;
/** @type {__VLS_StyleScopedClasses['py-2.5']} */ ;
/** @type {__VLS_StyleScopedClasses['border-b']} */ ;
/** @type {__VLS_StyleScopedClasses['border-owner-border/50']} */ ;
/** @type {__VLS_StyleScopedClasses['last:border-0']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['min-w-0']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['truncate']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['mt-0.5']} */ ;
/** @type {__VLS_StyleScopedClasses['font-mono']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['shrink-0']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['py-8']} */ ;
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
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['mt-0.5']} */ ;
/** @type {__VLS_StyleScopedClasses['font-mono']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            formatMoney: formatMoney,
            formatMoneyFull: formatMoneyFull,
            formatPct: formatPct,
            ErrorState: ErrorState,
            SkeletonCards: SkeletonCards,
            DateRangePicker: DateRangePicker,
            DetailSheet: DetailSheet,
            tabs: tabs,
            activeTab: activeTab,
            tabLabels: tabLabels,
            expData: expData,
            expLoading: expLoading,
            expError: expError,
            expReload: expReload,
            procData: procData,
            procLoading: procLoading,
            procError: procError,
            procReload: procReload,
            onDateChange: onDateChange,
            expenseDetail: expenseDetail,
            openExpenseDetail: openExpenseDetail,
            supplierDetail: supplierDetail,
            openSupplierDetail: openSupplierDetail,
            formatDate: formatDate,
            poStatusLabel: poStatusLabel,
        };
    },
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
});
; /* PartiallyEnd: #4569/main.vue */
