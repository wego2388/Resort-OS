import { ref, nextTick, watch } from 'vue';
import { useRouter } from 'vue-router';
import { useOwnerSearch, useDetailSheet } from '../composables/useOwnerData';
import { fetchDiningItemDetail, fetchSupplierDetail, fetchExpenseDetail, fetchProductDetail } from '../api/owner';
import { formatMoney, formatMoneyFull } from '../composables/useFormat';
import DetailSheet from './DetailSheet.vue';
const props = defineProps();
const emit = defineEmits();
const router = useRouter();
const { query, results, loading, onInput, clear } = useOwnerSearch();
const inputRef = ref(null);
watch(() => props.open, async (isOpen) => {
    if (isOpen) {
        await nextTick();
        inputRef.value?.focus();
    }
    else {
        clear();
    }
});
const typeIcon = {
    dining_item: '🍽',
    product: '📦',
    supplier: '🚚',
    expense_account: '💰',
    employee: '👤',
};
const typeLabel = {
    dining_item: 'صنف',
    product: 'منتج مخزون',
    supplier: 'مورد',
    expense_account: 'حساب مصروف',
    employee: 'موظف',
};
const itemDetail = useDetailSheet();
const supplierDetail = useDetailSheet();
const expenseDetail = useDetailSheet();
const productDetail = useDetailSheet();
function handleResultClick(r) {
    if (r.entity_type === 'dining_item') {
        itemDetail.open(() => fetchDiningItemDetail({ item_id: r.entity_id }));
    }
    else if (r.entity_type === 'supplier') {
        supplierDetail.open(() => fetchSupplierDetail({ supplier_id: r.entity_id }));
    }
    else if (r.entity_type === 'expense_account' && r.value_label) {
        expenseDetail.open(() => fetchExpenseDetail({ account_code: r.value_label }));
    }
    else if (r.entity_type === 'product') {
        productDetail.open(() => fetchProductDetail({ product_id: r.entity_id }));
    }
    else if (r.entity_type === 'employee') {
        emit('close');
        router.push('/hr');
    }
}
function formatDateTime(iso) {
    return new Date(iso).toLocaleString('ar-EG', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}
function formatDate(d) {
    return new Date(d).toLocaleDateString('ar-EG', { month: 'short', day: 'numeric' });
}
const movementTypeLabel = {
    purchase_in: 'شراء وارد', consumption: 'استهلاك', adjustment: 'تعديل جرد',
    transfer_in: 'تحويل وارد', transfer_out: 'تحويل صادر', spoilage: 'تالف',
};
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
/** @type {__VLS_StyleScopedClasses['search-fade-enter-active']} */ ;
/** @type {__VLS_StyleScopedClasses['search-fade-leave-active']} */ ;
// CSS variable injection 
// CSS variable injection end 
const __VLS_0 = {}.Teleport;
/** @type {[typeof __VLS_components.Teleport, typeof __VLS_components.Teleport, ]} */ ;
// @ts-ignore
const __VLS_1 = __VLS_asFunctionalComponent(__VLS_0, new __VLS_0({
    to: "body",
}));
const __VLS_2 = __VLS_1({
    to: "body",
}, ...__VLS_functionalComponentArgsRest(__VLS_1));
__VLS_3.slots.default;
const __VLS_4 = {}.Transition;
/** @type {[typeof __VLS_components.Transition, typeof __VLS_components.Transition, ]} */ ;
// @ts-ignore
const __VLS_5 = __VLS_asFunctionalComponent(__VLS_4, new __VLS_4({
    name: "search-fade",
}));
const __VLS_6 = __VLS_5({
    name: "search-fade",
}, ...__VLS_functionalComponentArgsRest(__VLS_5));
__VLS_7.slots.default;
if (__VLS_ctx.open) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "fixed inset-0 z-[60] bg-owner-bg flex flex-col" },
        ...{ style: {} },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "flex items-center gap-2 px-4 py-3 border-b border-owner-border shrink-0" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.open))
                    return;
                __VLS_ctx.emit('close');
            } },
        ...{ class: "touch-target text-owner-muted active:text-owner-text shrink-0" },
        'aria-label': "رجوع",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.svg, __VLS_intrinsicElements.svg)({
        ...{ class: "w-5 h-5" },
        fill: "none",
        viewBox: "0 0 24 24",
        stroke: "currentColor",
        'stroke-width': "2",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.path)({
        'stroke-linecap': "round",
        'stroke-linejoin': "round",
        d: "M9 5l7 7-7 7",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        ...{ onInput: (...[$event]) => {
                if (!(__VLS_ctx.open))
                    return;
                __VLS_ctx.onInput($event.target.value);
            } },
        ref: "inputRef",
        value: (__VLS_ctx.query),
        type: "search",
        placeholder: "ابحث عن أي صنف، منتج، مورد، مصروف، موظف...",
        ...{ class: "flex-1 bg-owner-card border border-owner-border rounded-xl px-4 py-2.5 text-sm text-owner-text outline-none focus:border-owner-green" },
        dir: "rtl",
    });
    /** @type {typeof __VLS_ctx.inputRef} */ ;
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "flex-1 overflow-y-auto overscroll-contain" },
    });
    if (__VLS_ctx.query.trim().length < 2) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "text-center text-xs text-owner-muted py-16 px-6" },
        });
    }
    else if (__VLS_ctx.loading) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "p-4 space-y-2" },
        });
        for (const [i] of __VLS_getVForSourceType((4))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div)({
                key: (i),
                ...{ class: "skeleton h-14 rounded-xl" },
            });
        }
    }
    else if (__VLS_ctx.results.length === 0) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "text-center text-xs text-owner-muted py-16" },
        });
        (__VLS_ctx.query);
    }
    else {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "p-2" },
        });
        for (const [r] of __VLS_getVForSourceType((__VLS_ctx.results))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
                ...{ onClick: (...[$event]) => {
                        if (!(__VLS_ctx.open))
                            return;
                        if (!!(__VLS_ctx.query.trim().length < 2))
                            return;
                        if (!!(__VLS_ctx.loading))
                            return;
                        if (!!(__VLS_ctx.results.length === 0))
                            return;
                        __VLS_ctx.handleResultClick(r);
                    } },
                key: (`${r.entity_type}-${r.entity_id}`),
                ...{ class: "w-full flex items-center gap-3 py-3 px-2 border-b border-owner-border/50 last:border-0 text-right active:bg-owner-card transition-colors rounded-lg" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "text-xl shrink-0" },
                'aria-hidden': "true",
            });
            (__VLS_ctx.typeIcon[r.entity_type] ?? '•');
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "min-w-0 flex-1" },
            });
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "text-sm font-semibold text-owner-text truncate" },
            });
            (r.title);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
                ...{ class: "text-xs text-owner-muted" },
            });
            (r.subtitle ?? __VLS_ctx.typeLabel[r.entity_type] ?? r.entity_type);
            __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
                ...{ class: "text-owner-muted shrink-0" },
                'aria-hidden': "true",
            });
        }
    }
}
var __VLS_7;
/** @type {[typeof DetailSheet, typeof DetailSheet, ]} */ ;
// @ts-ignore
const __VLS_8 = __VLS_asFunctionalComponent(DetailSheet, new DetailSheet({
    ...{ 'onClose': {} },
    ...{ 'onRetry': {} },
    open: (__VLS_ctx.itemDetail.isOpen.value),
    title: (__VLS_ctx.itemDetail.data.value?.item_name ?? 'تفاصيل الصنف'),
    subtitle: (__VLS_ctx.itemDetail.data.value ? `آخر 30 يوم · ${__VLS_ctx.formatMoney(__VLS_ctx.itemDetail.data.value.total_revenue)}` : undefined),
    loading: (__VLS_ctx.itemDetail.loading.value),
    error: (__VLS_ctx.itemDetail.error.value),
}));
const __VLS_9 = __VLS_8({
    ...{ 'onClose': {} },
    ...{ 'onRetry': {} },
    open: (__VLS_ctx.itemDetail.isOpen.value),
    title: (__VLS_ctx.itemDetail.data.value?.item_name ?? 'تفاصيل الصنف'),
    subtitle: (__VLS_ctx.itemDetail.data.value ? `آخر 30 يوم · ${__VLS_ctx.formatMoney(__VLS_ctx.itemDetail.data.value.total_revenue)}` : undefined),
    loading: (__VLS_ctx.itemDetail.loading.value),
    error: (__VLS_ctx.itemDetail.error.value),
}, ...__VLS_functionalComponentArgsRest(__VLS_8));
let __VLS_11;
let __VLS_12;
let __VLS_13;
const __VLS_14 = {
    onClose: (...[$event]) => {
        __VLS_ctx.itemDetail.close();
    }
};
const __VLS_15 = {
    onRetry: (...[$event]) => {
        __VLS_ctx.itemDetail.retry();
    }
};
__VLS_10.slots.default;
if (__VLS_ctx.itemDetail.data.value?.transactions.length === 0) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "text-xs text-owner-muted text-center py-8" },
    });
}
else {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "space-y-1" },
    });
    for (const [tx] of __VLS_getVForSourceType((__VLS_ctx.itemDetail.data.value?.transactions ?? []))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            key: (tx.order_id),
            ...{ class: "flex items-center justify-between py-2.5 border-b border-owner-border/50 last:border-0 text-xs" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "min-w-0" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "font-semibold text-owner-text" },
        });
        (tx.order_number);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "text-owner-muted mt-0.5" },
        });
        (tx.outlet_name);
        (__VLS_ctx.formatDateTime(tx.ordered_at));
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "font-mono font-semibold text-owner-text shrink-0" },
        });
        (__VLS_ctx.formatMoneyFull(tx.line_total));
    }
}
var __VLS_10;
/** @type {[typeof DetailSheet, typeof DetailSheet, ]} */ ;
// @ts-ignore
const __VLS_16 = __VLS_asFunctionalComponent(DetailSheet, new DetailSheet({
    ...{ 'onClose': {} },
    ...{ 'onRetry': {} },
    open: (__VLS_ctx.supplierDetail.isOpen.value),
    title: (__VLS_ctx.supplierDetail.data.value?.supplier_name ?? 'تفاصيل المورد'),
    subtitle: (__VLS_ctx.supplierDetail.data.value ? `${__VLS_ctx.supplierDetail.data.value.orders.length} أمر شراء · ${__VLS_ctx.formatMoney(__VLS_ctx.supplierDetail.data.value.total_amount)}` : undefined),
    loading: (__VLS_ctx.supplierDetail.loading.value),
    error: (__VLS_ctx.supplierDetail.error.value),
}));
const __VLS_17 = __VLS_16({
    ...{ 'onClose': {} },
    ...{ 'onRetry': {} },
    open: (__VLS_ctx.supplierDetail.isOpen.value),
    title: (__VLS_ctx.supplierDetail.data.value?.supplier_name ?? 'تفاصيل المورد'),
    subtitle: (__VLS_ctx.supplierDetail.data.value ? `${__VLS_ctx.supplierDetail.data.value.orders.length} أمر شراء · ${__VLS_ctx.formatMoney(__VLS_ctx.supplierDetail.data.value.total_amount)}` : undefined),
    loading: (__VLS_ctx.supplierDetail.loading.value),
    error: (__VLS_ctx.supplierDetail.error.value),
}, ...__VLS_functionalComponentArgsRest(__VLS_16));
let __VLS_19;
let __VLS_20;
let __VLS_21;
const __VLS_22 = {
    onClose: (...[$event]) => {
        __VLS_ctx.supplierDetail.close();
    }
};
const __VLS_23 = {
    onRetry: (...[$event]) => {
        __VLS_ctx.supplierDetail.retry();
    }
};
__VLS_18.slots.default;
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
        (po.item_count);
        (__VLS_ctx.formatDate(po.ordered_at));
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "font-mono font-semibold text-owner-text" },
        });
        (__VLS_ctx.formatMoneyFull(po.total_amount));
    }
}
var __VLS_18;
/** @type {[typeof DetailSheet, typeof DetailSheet, ]} */ ;
// @ts-ignore
const __VLS_24 = __VLS_asFunctionalComponent(DetailSheet, new DetailSheet({
    ...{ 'onClose': {} },
    ...{ 'onRetry': {} },
    open: (__VLS_ctx.expenseDetail.isOpen.value),
    title: (__VLS_ctx.expenseDetail.data.value?.account_name ?? 'تفاصيل المصروف'),
    subtitle: (__VLS_ctx.expenseDetail.data.value ? __VLS_ctx.formatMoney(__VLS_ctx.expenseDetail.data.value.total_amount) : undefined),
    loading: (__VLS_ctx.expenseDetail.loading.value),
    error: (__VLS_ctx.expenseDetail.error.value),
}));
const __VLS_25 = __VLS_24({
    ...{ 'onClose': {} },
    ...{ 'onRetry': {} },
    open: (__VLS_ctx.expenseDetail.isOpen.value),
    title: (__VLS_ctx.expenseDetail.data.value?.account_name ?? 'تفاصيل المصروف'),
    subtitle: (__VLS_ctx.expenseDetail.data.value ? __VLS_ctx.formatMoney(__VLS_ctx.expenseDetail.data.value.total_amount) : undefined),
    loading: (__VLS_ctx.expenseDetail.loading.value),
    error: (__VLS_ctx.expenseDetail.error.value),
}, ...__VLS_functionalComponentArgsRest(__VLS_24));
let __VLS_27;
let __VLS_28;
let __VLS_29;
const __VLS_30 = {
    onClose: (...[$event]) => {
        __VLS_ctx.expenseDetail.close();
    }
};
const __VLS_31 = {
    onRetry: (...[$event]) => {
        __VLS_ctx.expenseDetail.retry();
    }
};
__VLS_26.slots.default;
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
var __VLS_26;
/** @type {[typeof DetailSheet, typeof DetailSheet, ]} */ ;
// @ts-ignore
const __VLS_32 = __VLS_asFunctionalComponent(DetailSheet, new DetailSheet({
    ...{ 'onClose': {} },
    ...{ 'onRetry': {} },
    open: (__VLS_ctx.productDetail.isOpen.value),
    title: (__VLS_ctx.productDetail.data.value?.product_name ?? 'تفاصيل المنتج'),
    subtitle: (__VLS_ctx.productDetail.data.value ? `الرصيد الحالي: ${__VLS_ctx.productDetail.data.value.current_stock} ${__VLS_ctx.productDetail.data.value.unit}` : undefined),
    loading: (__VLS_ctx.productDetail.loading.value),
    error: (__VLS_ctx.productDetail.error.value),
}));
const __VLS_33 = __VLS_32({
    ...{ 'onClose': {} },
    ...{ 'onRetry': {} },
    open: (__VLS_ctx.productDetail.isOpen.value),
    title: (__VLS_ctx.productDetail.data.value?.product_name ?? 'تفاصيل المنتج'),
    subtitle: (__VLS_ctx.productDetail.data.value ? `الرصيد الحالي: ${__VLS_ctx.productDetail.data.value.current_stock} ${__VLS_ctx.productDetail.data.value.unit}` : undefined),
    loading: (__VLS_ctx.productDetail.loading.value),
    error: (__VLS_ctx.productDetail.error.value),
}, ...__VLS_functionalComponentArgsRest(__VLS_32));
let __VLS_35;
let __VLS_36;
let __VLS_37;
const __VLS_38 = {
    onClose: (...[$event]) => {
        __VLS_ctx.productDetail.close();
    }
};
const __VLS_39 = {
    onRetry: (...[$event]) => {
        __VLS_ctx.productDetail.retry();
    }
};
__VLS_34.slots.default;
if (__VLS_ctx.productDetail.data.value?.movements.length === 0) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "text-xs text-owner-muted text-center py-8" },
    });
}
else {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "space-y-1" },
    });
    for (const [m] of __VLS_getVForSourceType((__VLS_ctx.productDetail.data.value?.movements ?? []))) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            key: (m.movement_id),
            ...{ class: "flex items-center justify-between py-2.5 border-b border-owner-border/50 last:border-0 text-xs" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({});
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "font-semibold text-owner-text" },
        });
        (__VLS_ctx.movementTypeLabel[m.movement_type] ?? m.movement_type);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "text-owner-muted mt-0.5" },
        });
        (m.warehouse_name);
        (__VLS_ctx.formatDateTime(m.moved_at));
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "font-mono font-semibold" },
            ...{ class: (parseFloat(m.quantity) < 0 ? 'text-owner-red' : 'text-owner-green') },
        });
        (parseFloat(m.quantity) > 0 ? '+' : '');
        (m.quantity);
    }
}
var __VLS_34;
var __VLS_3;
/** @type {__VLS_StyleScopedClasses['fixed']} */ ;
/** @type {__VLS_StyleScopedClasses['inset-0']} */ ;
/** @type {__VLS_StyleScopedClasses['z-[60]']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-owner-bg']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-col']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-2']} */ ;
/** @type {__VLS_StyleScopedClasses['px-4']} */ ;
/** @type {__VLS_StyleScopedClasses['py-3']} */ ;
/** @type {__VLS_StyleScopedClasses['border-b']} */ ;
/** @type {__VLS_StyleScopedClasses['border-owner-border']} */ ;
/** @type {__VLS_StyleScopedClasses['shrink-0']} */ ;
/** @type {__VLS_StyleScopedClasses['touch-target']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['active:text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['shrink-0']} */ ;
/** @type {__VLS_StyleScopedClasses['w-5']} */ ;
/** @type {__VLS_StyleScopedClasses['h-5']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-1']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['border']} */ ;
/** @type {__VLS_StyleScopedClasses['border-owner-border']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
/** @type {__VLS_StyleScopedClasses['px-4']} */ ;
/** @type {__VLS_StyleScopedClasses['py-2.5']} */ ;
/** @type {__VLS_StyleScopedClasses['text-sm']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['outline-none']} */ ;
/** @type {__VLS_StyleScopedClasses['focus:border-owner-green']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-1']} */ ;
/** @type {__VLS_StyleScopedClasses['overflow-y-auto']} */ ;
/** @type {__VLS_StyleScopedClasses['overscroll-contain']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['py-16']} */ ;
/** @type {__VLS_StyleScopedClasses['px-6']} */ ;
/** @type {__VLS_StyleScopedClasses['p-4']} */ ;
/** @type {__VLS_StyleScopedClasses['space-y-2']} */ ;
/** @type {__VLS_StyleScopedClasses['skeleton']} */ ;
/** @type {__VLS_StyleScopedClasses['h-14']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['py-16']} */ ;
/** @type {__VLS_StyleScopedClasses['p-2']} */ ;
/** @type {__VLS_StyleScopedClasses['w-full']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-3']} */ ;
/** @type {__VLS_StyleScopedClasses['py-3']} */ ;
/** @type {__VLS_StyleScopedClasses['px-2']} */ ;
/** @type {__VLS_StyleScopedClasses['border-b']} */ ;
/** @type {__VLS_StyleScopedClasses['border-owner-border/50']} */ ;
/** @type {__VLS_StyleScopedClasses['last:border-0']} */ ;
/** @type {__VLS_StyleScopedClasses['text-right']} */ ;
/** @type {__VLS_StyleScopedClasses['active:bg-owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['transition-colors']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-lg']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xl']} */ ;
/** @type {__VLS_StyleScopedClasses['shrink-0']} */ ;
/** @type {__VLS_StyleScopedClasses['min-w-0']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-1']} */ ;
/** @type {__VLS_StyleScopedClasses['text-sm']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['truncate']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
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
/** @type {__VLS_StyleScopedClasses['min-w-0']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
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
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            formatMoney: formatMoney,
            formatMoneyFull: formatMoneyFull,
            DetailSheet: DetailSheet,
            emit: emit,
            query: query,
            results: results,
            loading: loading,
            onInput: onInput,
            inputRef: inputRef,
            typeIcon: typeIcon,
            typeLabel: typeLabel,
            itemDetail: itemDetail,
            supplierDetail: supplierDetail,
            expenseDetail: expenseDetail,
            productDetail: productDetail,
            handleResultClick: handleResultClick,
            formatDateTime: formatDateTime,
            formatDate: formatDate,
            movementTypeLabel: movementTypeLabel,
        };
    },
    __typeEmits: {},
    __typeProps: {},
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
    __typeEmits: {},
    __typeProps: {},
});
; /* PartiallyEnd: #4569/main.vue */
