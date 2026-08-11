/// <reference types="../../node_modules/.vue-global-types/vue_3.5_0_0_0.d.ts" />
/**
 * DetailSheet — نافذة تفاصيل موحّدة (bottom sheet) تُستخدم في كل شاشات
 * الأونر. تدوس على أي سطر إجمالي (صنف/فئة مصروف/مورد...) → تفتح النافذة
 * دي بالسجلات الخام اللي كوّنت الرقم، بدل شاشة منفصلة لكل حالة.
 *
 * الاستخدام: <DetailSheet :open :title :subtitle :loading :error @close
 * @retry> ... default slot لصفوف المحتوى، اللي بيختلف شكله حسب النوع ... </DetailSheet>
 */
import { watch } from 'vue';
const props = defineProps();
const emit = defineEmits();
// يمنع scroll الصفحة اللي تحت وقت فتح النافذة
watch(() => props.open, (isOpen) => {
    document.body.style.overflow = isOpen ? 'hidden' : '';
});
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
/** @type {__VLS_StyleScopedClasses['sheet-fade-enter-active']} */ ;
/** @type {__VLS_StyleScopedClasses['sheet-fade-leave-active']} */ ;
/** @type {__VLS_StyleScopedClasses['sheet-slide-enter-active']} */ ;
/** @type {__VLS_StyleScopedClasses['sheet-slide-leave-active']} */ ;
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
    name: "sheet-fade",
}));
const __VLS_6 = __VLS_5({
    name: "sheet-fade",
}, ...__VLS_functionalComponentArgsRest(__VLS_5));
__VLS_7.slots.default;
if (__VLS_ctx.open) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.open))
                    return;
                __VLS_ctx.emit('close');
            } },
        ...{ class: "fixed inset-0 z-50 bg-black/60" },
    });
    const __VLS_8 = {}.Transition;
    /** @type {[typeof __VLS_components.Transition, typeof __VLS_components.Transition, ]} */ ;
    // @ts-ignore
    const __VLS_9 = __VLS_asFunctionalComponent(__VLS_8, new __VLS_8({
        name: "sheet-slide",
        appear: true,
    }));
    const __VLS_10 = __VLS_9({
        name: "sheet-slide",
        appear: true,
    }, ...__VLS_functionalComponentArgsRest(__VLS_9));
    __VLS_11.slots.default;
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "absolute inset-x-0 bottom-0 max-h-[85vh] flex flex-col bg-owner-bg rounded-t-2xl border-t border-owner-border shadow-2xl" },
        ...{ style: {} },
        role: "dialog",
        'aria-modal': "true",
        'aria-label': (__VLS_ctx.title),
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "flex justify-center pt-2 pb-1 shrink-0" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div)({
        ...{ class: "w-10 h-1 rounded-full bg-owner-border" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "flex items-start justify-between gap-3 px-4 pb-3 border-b border-owner-border shrink-0" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "min-w-0" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({
        ...{ class: "text-sm font-bold text-owner-text truncate" },
    });
    (__VLS_ctx.title);
    if (__VLS_ctx.subtitle) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "text-xs text-owner-muted mt-0.5" },
        });
        (__VLS_ctx.subtitle);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!(__VLS_ctx.open))
                    return;
                __VLS_ctx.emit('close');
            } },
        ...{ class: "touch-target shrink-0 text-owner-muted active:text-owner-text transition-colors" },
        'aria-label': "إغلاق",
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
        d: "M6 18L18 6M6 6l12 12",
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "flex-1 overflow-y-auto overscroll-contain px-4 py-3" },
    });
    if (__VLS_ctx.loading) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "space-y-2 py-4" },
        });
        for (const [i] of __VLS_getVForSourceType((5))) {
            __VLS_asFunctionalElement(__VLS_intrinsicElements.div)({
                key: (i),
                ...{ class: "skeleton h-14 rounded-xl" },
            });
        }
    }
    else if (__VLS_ctx.error) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "flex flex-col items-center justify-center py-12 text-center" },
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "text-3xl mb-3" },
            'aria-hidden': "true",
        });
        __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
            ...{ class: "text-owner-muted text-xs mb-4" },
        });
        (__VLS_ctx.error);
        __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
            ...{ onClick: (...[$event]) => {
                    if (!(__VLS_ctx.open))
                        return;
                    if (!!(__VLS_ctx.loading))
                        return;
                    if (!(__VLS_ctx.error))
                        return;
                    __VLS_ctx.emit('retry');
                } },
            ...{ class: "touch-target bg-owner-card border border-owner-border rounded-xl px-5 text-xs font-semibold text-owner-text active:opacity-70" },
        });
    }
    else {
        var __VLS_12 = {};
    }
    var __VLS_11;
}
var __VLS_7;
var __VLS_3;
/** @type {__VLS_StyleScopedClasses['fixed']} */ ;
/** @type {__VLS_StyleScopedClasses['inset-0']} */ ;
/** @type {__VLS_StyleScopedClasses['z-50']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-black/60']} */ ;
/** @type {__VLS_StyleScopedClasses['absolute']} */ ;
/** @type {__VLS_StyleScopedClasses['inset-x-0']} */ ;
/** @type {__VLS_StyleScopedClasses['bottom-0']} */ ;
/** @type {__VLS_StyleScopedClasses['max-h-[85vh]']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-col']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-owner-bg']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-t-2xl']} */ ;
/** @type {__VLS_StyleScopedClasses['border-t']} */ ;
/** @type {__VLS_StyleScopedClasses['border-owner-border']} */ ;
/** @type {__VLS_StyleScopedClasses['shadow-2xl']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['justify-center']} */ ;
/** @type {__VLS_StyleScopedClasses['pt-2']} */ ;
/** @type {__VLS_StyleScopedClasses['pb-1']} */ ;
/** @type {__VLS_StyleScopedClasses['shrink-0']} */ ;
/** @type {__VLS_StyleScopedClasses['w-10']} */ ;
/** @type {__VLS_StyleScopedClasses['h-1']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-full']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-owner-border']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-start']} */ ;
/** @type {__VLS_StyleScopedClasses['justify-between']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-3']} */ ;
/** @type {__VLS_StyleScopedClasses['px-4']} */ ;
/** @type {__VLS_StyleScopedClasses['pb-3']} */ ;
/** @type {__VLS_StyleScopedClasses['border-b']} */ ;
/** @type {__VLS_StyleScopedClasses['border-owner-border']} */ ;
/** @type {__VLS_StyleScopedClasses['shrink-0']} */ ;
/** @type {__VLS_StyleScopedClasses['min-w-0']} */ ;
/** @type {__VLS_StyleScopedClasses['text-sm']} */ ;
/** @type {__VLS_StyleScopedClasses['font-bold']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['truncate']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['mt-0.5']} */ ;
/** @type {__VLS_StyleScopedClasses['touch-target']} */ ;
/** @type {__VLS_StyleScopedClasses['shrink-0']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['active:text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['transition-colors']} */ ;
/** @type {__VLS_StyleScopedClasses['w-5']} */ ;
/** @type {__VLS_StyleScopedClasses['h-5']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-1']} */ ;
/** @type {__VLS_StyleScopedClasses['overflow-y-auto']} */ ;
/** @type {__VLS_StyleScopedClasses['overscroll-contain']} */ ;
/** @type {__VLS_StyleScopedClasses['px-4']} */ ;
/** @type {__VLS_StyleScopedClasses['py-3']} */ ;
/** @type {__VLS_StyleScopedClasses['space-y-2']} */ ;
/** @type {__VLS_StyleScopedClasses['py-4']} */ ;
/** @type {__VLS_StyleScopedClasses['skeleton']} */ ;
/** @type {__VLS_StyleScopedClasses['h-14']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-col']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['justify-center']} */ ;
/** @type {__VLS_StyleScopedClasses['py-12']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['text-3xl']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-3']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-4']} */ ;
/** @type {__VLS_StyleScopedClasses['touch-target']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['border']} */ ;
/** @type {__VLS_StyleScopedClasses['border-owner-border']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
/** @type {__VLS_StyleScopedClasses['px-5']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['active:opacity-70']} */ ;
// @ts-ignore
var __VLS_13 = __VLS_12;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            emit: emit,
        };
    },
    __typeEmits: {},
    __typeProps: {},
});
const __VLS_component = (await import('vue')).defineComponent({
    setup() {
        return {};
    },
    __typeEmits: {},
    __typeProps: {},
});
export default {};
; /* PartiallyEnd: #4569/main.vue */
