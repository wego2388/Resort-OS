/// <reference types="../../node_modules/.vue-global-types/vue_3.5_0_0_0.d.ts" />
/**
 * MetricCard — بطاقة المقياس الأساسية.
 * رقم واحد كبير + label + sparkline + delta + provisional badge.
 * قرار 0004: لا يُقدَّم رقم provisional كأنه نهائي.
 */
import SparkLine from './SparkLine.vue';
import { deltaClass, deltaArrow } from '../composables/useFormat';
const props = defineProps();
const emit = defineEmits();
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "owner-card" },
    role: "region",
    'aria-label': (__VLS_ctx.label),
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "flex items-start justify-between mb-3" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
    ...{ class: "text-xs font-semibold text-owner-muted uppercase tracking-wider" },
});
(__VLS_ctx.label);
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "flex items-center gap-2" },
});
if (__VLS_ctx.isProvisional) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
        ...{ class: "provisional-badge" },
        role: "status",
        'aria-label': "غير نهائي",
    });
}
if (__VLS_ctx.pinned !== undefined) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.pinned !== undefined))
                    return;
                __VLS_ctx.emit('toggle-pin');
            } },
        ...{ class: "touch-target -m-2 p-2 text-lg leading-none transition-colors" },
        ...{ class: (__VLS_ctx.pinned ? 'text-owner-amber' : 'text-owner-border active:text-owner-muted') },
        'aria-label': (__VLS_ctx.pinned ? 'إلغاء التثبيت' : 'تثبيت في المفضلة'),
    });
    (__VLS_ctx.pinned ? '★' : '☆');
}
if (__VLS_ctx.loading) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div)({
        ...{ class: "skeleton h-9 w-3/4 mb-3 rounded" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div)({
        ...{ class: "skeleton h-10 w-full mb-2 rounded" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div)({
        ...{ class: "skeleton h-4 w-1/3 rounded" },
    });
}
else {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "metric-value mb-1" },
        ...{ class: ({
                'text-owner-green': __VLS_ctx.colorScheme === 'green',
                'text-owner-red': __VLS_ctx.colorScheme === 'red',
                'text-owner-amber': __VLS_ctx.colorScheme === 'amber',
                'text-owner-text': !__VLS_ctx.colorScheme || __VLS_ctx.colorScheme === 'default',
            }) },
    });
    (__VLS_ctx.value);
    if (__VLS_ctx.subtitle) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "text-xs text-owner-muted mb-2" },
        });
        (__VLS_ctx.subtitle);
    }
    if (__VLS_ctx.sparkValues && __VLS_ctx.sparkValues.length > 1) {
        /** @type {[typeof SparkLine, ]} */ ;
        // @ts-ignore
        const __VLS_0 = __VLS_asFunctionalComponent(SparkLine, new SparkLine({
            values: (__VLS_ctx.sparkValues),
            ...{ class: "mb-2" },
        }));
        const __VLS_1 = __VLS_0({
            values: (__VLS_ctx.sparkValues),
            ...{ class: "mb-2" },
        }, ...__VLS_functionalComponentArgsRest(__VLS_0));
    }
    if (__VLS_ctx.delta || __VLS_ctx.deltaValue !== undefined) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "text-xs font-semibold flex items-center gap-1" },
            ...{ class: (__VLS_ctx.deltaClass(__VLS_ctx.deltaValue)) },
            'aria-live': "polite",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.deltaArrow(__VLS_ctx.deltaValue));
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
        (__VLS_ctx.delta);
    }
}
/** @type {__VLS_StyleScopedClasses['owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-start']} */ ;
/** @type {__VLS_StyleScopedClasses['justify-between']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-3']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['uppercase']} */ ;
/** @type {__VLS_StyleScopedClasses['tracking-wider']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-2']} */ ;
/** @type {__VLS_StyleScopedClasses['provisional-badge']} */ ;
/** @type {__VLS_StyleScopedClasses['touch-target']} */ ;
/** @type {__VLS_StyleScopedClasses['-m-2']} */ ;
/** @type {__VLS_StyleScopedClasses['p-2']} */ ;
/** @type {__VLS_StyleScopedClasses['text-lg']} */ ;
/** @type {__VLS_StyleScopedClasses['leading-none']} */ ;
/** @type {__VLS_StyleScopedClasses['transition-colors']} */ ;
/** @type {__VLS_StyleScopedClasses['skeleton']} */ ;
/** @type {__VLS_StyleScopedClasses['h-9']} */ ;
/** @type {__VLS_StyleScopedClasses['w-3/4']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-3']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded']} */ ;
/** @type {__VLS_StyleScopedClasses['skeleton']} */ ;
/** @type {__VLS_StyleScopedClasses['h-10']} */ ;
/** @type {__VLS_StyleScopedClasses['w-full']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-2']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded']} */ ;
/** @type {__VLS_StyleScopedClasses['skeleton']} */ ;
/** @type {__VLS_StyleScopedClasses['h-4']} */ ;
/** @type {__VLS_StyleScopedClasses['w-1/3']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded']} */ ;
/** @type {__VLS_StyleScopedClasses['metric-value']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-1']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-2']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-2']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-1']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            SparkLine: SparkLine,
            deltaClass: deltaClass,
            deltaArrow: deltaArrow,
            emit: emit,
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
