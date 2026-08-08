/// <reference types="../../node_modules/.vue-global-types/vue_3.5_0_0_0.d.ts" />
/**
 * DateRangePicker — فلتر الفترة الزمنية لشاشات التحليل (Decision 0004 §7b).
 * أزرار سريعة: اليوم / أمبارح / هذا الأسبوع / هذا الشهر
 * + date inputs للفترة الحرة.
 * يُصدر { date_from, date_to } كـ ISO strings (YYYY-MM-DD).
 */
import { ref, watch } from 'vue';
const emit = defineEmits();
/** تنسيق تاريخ → YYYY-MM-DD */
function toISO(d) {
    return d.toISOString().slice(0, 10);
}
function today() { return new Date(); }
function makeRange(from, to) {
    return { date_from: toISO(from), date_to: toISO(to) };
}
const presets = [
    {
        label: 'اليوم',
        key: 'today',
        get: () => makeRange(today(), today()),
    },
    {
        label: 'أمس',
        key: 'yesterday',
        get: () => {
            const d = today();
            d.setDate(d.getDate() - 1);
            return makeRange(d, d);
        },
    },
    {
        label: 'هذا الأسبوع',
        key: 'week',
        get: () => {
            const t = today();
            const mon = new Date(t);
            mon.setDate(t.getDate() - t.getDay() + (t.getDay() === 0 ? -6 : 1));
            return makeRange(mon, t);
        },
    },
    {
        label: 'هذا الشهر',
        key: 'month',
        get: () => {
            const t = today();
            return makeRange(new Date(t.getFullYear(), t.getMonth(), 1), t);
        },
    },
];
// الافتراضي: هذا الشهر
const active = ref('month');
const customFrom = ref('');
const customTo = ref('');
/** يطلق الـ emit بالقيم الصحيحة */
function applyPreset(key) {
    active.value = key;
    if (key === 'custom')
        return;
    const preset = presets.find(p => p.key === key);
    if (!preset)
        return;
    const range = preset.get();
    customFrom.value = range.date_from;
    customTo.value = range.date_to;
    emit('change', range);
}
// عند تغيير custom dates يدوياً
watch([customFrom, customTo], ([from, to]) => {
    if (active.value === 'custom' && from && to && from <= to) {
        emit('change', { date_from: from, date_to: to });
    }
});
// إطلاق الافتراضي عند mount
applyPreset('month');
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "owner-card space-y-3" },
    role: "group",
    'aria-label': "فلتر الفترة الزمنية",
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "flex gap-2 flex-wrap" },
});
for (const [preset] of __VLS_getVForSourceType((__VLS_ctx.presets))) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                __VLS_ctx.applyPreset(preset.key);
            } },
        key: (preset.key),
        ...{ class: "px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors touch-target" },
        ...{ class: (__VLS_ctx.active === preset.key
                ? 'bg-owner-green text-black'
                : 'bg-owner-bg text-owner-muted border border-owner-border') },
    });
    (preset.label);
}
__VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
    ...{ onClick: (...[$event]) => {
            __VLS_ctx.active = 'custom';
        } },
    ...{ class: "px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors touch-target" },
    ...{ class: (__VLS_ctx.active === 'custom'
            ? 'bg-owner-green text-black'
            : 'bg-owner-bg text-owner-muted border border-owner-border') },
});
if (__VLS_ctx.active === 'custom') {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "flex gap-2 items-center" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "flex-1" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
        ...{ class: "block text-[10px] text-owner-muted mb-0.5" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        type: "date",
        ...{ class: "w-full bg-owner-bg border border-owner-border rounded-lg px-2 py-1.5 text-xs text-owner-text outline-none focus:border-owner-green" },
        dir: "ltr",
    });
    (__VLS_ctx.customFrom);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "flex-1" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.label, __VLS_intrinsicElements.label)({
        ...{ class: "block text-[10px] text-owner-muted mb-0.5" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        type: "date",
        ...{ class: "w-full bg-owner-bg border border-owner-border rounded-lg px-2 py-1.5 text-xs text-owner-text outline-none focus:border-owner-green" },
        dir: "ltr",
        min: (__VLS_ctx.customFrom),
    });
    (__VLS_ctx.customTo);
}
/** @type {__VLS_StyleScopedClasses['owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['space-y-3']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-2']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-wrap']} */ ;
/** @type {__VLS_StyleScopedClasses['px-3']} */ ;
/** @type {__VLS_StyleScopedClasses['py-1.5']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-lg']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['transition-colors']} */ ;
/** @type {__VLS_StyleScopedClasses['touch-target']} */ ;
/** @type {__VLS_StyleScopedClasses['px-3']} */ ;
/** @type {__VLS_StyleScopedClasses['py-1.5']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-lg']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['font-semibold']} */ ;
/** @type {__VLS_StyleScopedClasses['transition-colors']} */ ;
/** @type {__VLS_StyleScopedClasses['touch-target']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-2']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-1']} */ ;
/** @type {__VLS_StyleScopedClasses['block']} */ ;
/** @type {__VLS_StyleScopedClasses['text-[10px]']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-0.5']} */ ;
/** @type {__VLS_StyleScopedClasses['w-full']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-owner-bg']} */ ;
/** @type {__VLS_StyleScopedClasses['border']} */ ;
/** @type {__VLS_StyleScopedClasses['border-owner-border']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-lg']} */ ;
/** @type {__VLS_StyleScopedClasses['px-2']} */ ;
/** @type {__VLS_StyleScopedClasses['py-1.5']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['outline-none']} */ ;
/** @type {__VLS_StyleScopedClasses['focus:border-owner-green']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-1']} */ ;
/** @type {__VLS_StyleScopedClasses['block']} */ ;
/** @type {__VLS_StyleScopedClasses['text-[10px]']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-0.5']} */ ;
/** @type {__VLS_StyleScopedClasses['w-full']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-owner-bg']} */ ;
/** @type {__VLS_StyleScopedClasses['border']} */ ;
/** @type {__VLS_StyleScopedClasses['border-owner-border']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-lg']} */ ;
/** @type {__VLS_StyleScopedClasses['px-2']} */ ;
/** @type {__VLS_StyleScopedClasses['py-1.5']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['outline-none']} */ ;
/** @type {__VLS_StyleScopedClasses['focus:border-owner-green']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            presets: presets,
            active: active,
            customFrom: customFrom,
            customTo: customTo,
            applyPreset: applyPreset,
        };
    },
    __typeEmits: {},
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
    __typeEmits: {},
});
; /* PartiallyEnd: #4569/main.vue */
