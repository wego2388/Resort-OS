/// <reference types="../../node_modules/.vue-global-types/vue_3.5_0_0_0.d.ts" />
/**
 * AppShell — الغلاف الرئيسي للـ owner app.
 * - Safe area top/bottom (iPhone notch/Dynamic Island)
 * - Bottom navigation (Now + Performance + Sales + Expenses + Shifts + HR)
 * - Logout button في الـ header (Decision 0004 §7b)
 * - RouterView في المنتصف
 */
import { computed, ref } from 'vue';
import { useRoute, useRouter, RouterView } from 'vue-router';
import { useAuthStore } from '@resort-os/core';
import SearchOverlay from '../components/SearchOverlay.vue';
const route = useRoute();
const router = useRouter();
const auth = useAuthStore();
const searchOpen = ref(false);
const navItems = [
    { name: 'now', label: 'الآن', icon: '⚡' },
    { name: 'performance', label: 'الأداء', icon: '📊' },
    { name: 'sales', label: 'المبيعات', icon: '🛒' },
    { name: 'expenses', label: 'المصروفات', icon: '💰' },
    { name: 'shifts', label: 'الورديات', icon: '🔔' },
    { name: 'hr', label: 'الموظفين', icon: '👥' },
];
const activeNav = computed(() => route.name);
const loggingOut = ref(false);
async function handleLogout() {
    if (loggingOut.value)
        return;
    loggingOut.value = true;
    try {
        await auth.logout();
    }
    finally {
        loggingOut.value = false;
    }
    router.replace('/login');
}
function vibrate(ms = 6) {
    try {
        navigator.vibrate?.(ms);
    }
    catch { /* unsupported */ }
}
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "flex flex-col h-dvh bg-owner-bg" },
    ...{ style: {} },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.header, __VLS_intrinsicElements.header)({
    ...{ class: "flex items-center justify-between px-4 py-3 bg-owner-card border-b border-owner-border shrink-0" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.h1, __VLS_intrinsicElements.h1)({
    ...{ class: "text-sm font-bold text-owner-text" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "flex items-center gap-3" },
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "text-xs text-owner-muted hidden xs:block" },
});
(new Date().toLocaleDateString('ar-EG', { weekday: 'long', day: 'numeric', month: 'short' }));
__VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
    ...{ onClick: (...[$event]) => {
            __VLS_ctx.searchOpen = true;
        } },
    ...{ class: "touch-target text-owner-muted active:text-owner-green transition-colors" },
    'aria-label': "بحث",
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.svg, __VLS_intrinsicElements.svg)({
    ...{ class: "w-5 h-5" },
    fill: "none",
    viewBox: "0 0 24 24",
    stroke: "currentColor",
    'stroke-width': "2",
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.circle)({
    cx: "11",
    cy: "11",
    r: "7",
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.path)({
    'stroke-linecap': "round",
    d: "M21 21l-4.35-4.35",
});
__VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
    ...{ onClick: (__VLS_ctx.handleLogout) },
    ...{ class: "text-xs text-owner-muted hover:text-owner-red active:text-owner-red transition-colors touch-target px-1" },
    disabled: (__VLS_ctx.loggingOut),
    'aria-label': "تسجيل الخروج",
});
if (__VLS_ctx.loggingOut) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
}
else {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
}
/** @type {[typeof SearchOverlay, ]} */ ;
// @ts-ignore
const __VLS_0 = __VLS_asFunctionalComponent(SearchOverlay, new SearchOverlay({
    ...{ 'onClose': {} },
    open: (__VLS_ctx.searchOpen),
}));
const __VLS_1 = __VLS_0({
    ...{ 'onClose': {} },
    open: (__VLS_ctx.searchOpen),
}, ...__VLS_functionalComponentArgsRest(__VLS_0));
let __VLS_3;
let __VLS_4;
let __VLS_5;
const __VLS_6 = {
    onClose: (...[$event]) => {
        __VLS_ctx.searchOpen = false;
    }
};
var __VLS_2;
__VLS_asFunctionalElement(__VLS_intrinsicElements.main, __VLS_intrinsicElements.main)({
    ...{ class: "flex-1 flex flex-col overflow-hidden" },
});
const __VLS_7 = {}.RouterView;
/** @type {[typeof __VLS_components.RouterView, ]} */ ;
// @ts-ignore
const __VLS_8 = __VLS_asFunctionalComponent(__VLS_7, new __VLS_7({}));
const __VLS_9 = __VLS_8({}, ...__VLS_functionalComponentArgsRest(__VLS_8));
__VLS_asFunctionalElement(__VLS_intrinsicElements.nav, __VLS_intrinsicElements.nav)({
    ...{ class: "bottom-nav" },
    role: "navigation",
    'aria-label': "التنقل الرئيسي",
});
for (const [item] of __VLS_getVForSourceType((__VLS_ctx.navItems))) {
    const __VLS_11 = {}.RouterLink;
    /** @type {[typeof __VLS_components.RouterLink, typeof __VLS_components.RouterLink, ]} */ ;
    // @ts-ignore
    const __VLS_12 = __VLS_asFunctionalComponent(__VLS_11, new __VLS_11({
        ...{ 'onClick': {} },
        key: (item.name),
        to: (`/${item.name}`),
        ...{ class: "bottom-nav-item" },
        ...{ class: ({ active: __VLS_ctx.activeNav === item.name }) },
        'aria-current': (__VLS_ctx.activeNav === item.name ? 'page' : undefined),
    }));
    const __VLS_13 = __VLS_12({
        ...{ 'onClick': {} },
        key: (item.name),
        to: (`/${item.name}`),
        ...{ class: "bottom-nav-item" },
        ...{ class: ({ active: __VLS_ctx.activeNav === item.name }) },
        'aria-current': (__VLS_ctx.activeNav === item.name ? 'page' : undefined),
    }, ...__VLS_functionalComponentArgsRest(__VLS_12));
    let __VLS_15;
    let __VLS_16;
    let __VLS_17;
    const __VLS_18 = {
        onClick: (...[$event]) => {
            __VLS_ctx.vibrate();
        }
    };
    __VLS_14.slots.default;
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
        ...{ class: "text-lg leading-none" },
        'aria-hidden': "true",
    });
    (item.icon);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({
        ...{ class: "text-[10px]" },
    });
    (item.label);
    var __VLS_14;
}
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-col']} */ ;
/** @type {__VLS_StyleScopedClasses['h-dvh']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-owner-bg']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['justify-between']} */ ;
/** @type {__VLS_StyleScopedClasses['px-4']} */ ;
/** @type {__VLS_StyleScopedClasses['py-3']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['border-b']} */ ;
/** @type {__VLS_StyleScopedClasses['border-owner-border']} */ ;
/** @type {__VLS_StyleScopedClasses['shrink-0']} */ ;
/** @type {__VLS_StyleScopedClasses['text-sm']} */ ;
/** @type {__VLS_StyleScopedClasses['font-bold']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['gap-3']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['hidden']} */ ;
/** @type {__VLS_StyleScopedClasses['xs:block']} */ ;
/** @type {__VLS_StyleScopedClasses['touch-target']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['active:text-owner-green']} */ ;
/** @type {__VLS_StyleScopedClasses['transition-colors']} */ ;
/** @type {__VLS_StyleScopedClasses['w-5']} */ ;
/** @type {__VLS_StyleScopedClasses['h-5']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['hover:text-owner-red']} */ ;
/** @type {__VLS_StyleScopedClasses['active:text-owner-red']} */ ;
/** @type {__VLS_StyleScopedClasses['transition-colors']} */ ;
/** @type {__VLS_StyleScopedClasses['touch-target']} */ ;
/** @type {__VLS_StyleScopedClasses['px-1']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-1']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-col']} */ ;
/** @type {__VLS_StyleScopedClasses['overflow-hidden']} */ ;
/** @type {__VLS_StyleScopedClasses['bottom-nav']} */ ;
/** @type {__VLS_StyleScopedClasses['bottom-nav-item']} */ ;
/** @type {__VLS_StyleScopedClasses['text-lg']} */ ;
/** @type {__VLS_StyleScopedClasses['leading-none']} */ ;
/** @type {__VLS_StyleScopedClasses['text-[10px]']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            RouterView: RouterView,
            SearchOverlay: SearchOverlay,
            searchOpen: searchOpen,
            navItems: navItems,
            activeNav: activeNav,
            loggingOut: loggingOut,
            handleLogout: handleLogout,
            vibrate: vibrate,
        };
    },
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
});
; /* PartiallyEnd: #4569/main.vue */
