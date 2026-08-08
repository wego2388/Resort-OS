/// <reference types="../../node_modules/.vue-global-types/vue_3.5_0_0_0.d.ts" />
/**
 * TwoFactorSetupView — 2FA setup flow حقيقي (Decision 0004 §7b).
 * يستخدم endpoints الموجودة: POST /auth/2fa/setup → POST /auth/2fa/enable
 * خطوات:
 *  1. طلب QR code من /2fa/setup
 *  2. عرض QR + secret key
 *  3. المستخدم يدخل كود التحقق من التطبيق
 *  4. تأكيد التفعيل عبر /2fa/enable
 */
import { ref, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { api, useAuthStore } from '@resort-os/core';
const router = useRouter();
const auth = useAuthStore();
const step = ref('loading');
const qrCodeUrl = ref('');
const secretKey = ref('');
const otpCode = ref('');
const errorMsg = ref('');
const verifying = ref(false);
const showSecret = ref(false);
async function loadQR() {
    step.value = 'loading';
    errorMsg.value = '';
    try {
        const res = await api.post('/api/v1/auth/2fa/setup');
        qrCodeUrl.value = res.data.qr_code_url;
        secretKey.value = res.data.secret;
        step.value = 'show_qr';
    }
    catch (e) {
        const msg = e
            .response?.data?.detail ?? 'فشل تحميل رمز QR';
        errorMsg.value = msg;
        step.value = 'error';
    }
}
async function confirmSetup() {
    if (!otpCode.value || otpCode.value.length < 6) {
        errorMsg.value = 'أدخل الرمز المكوّن من 6 أرقام';
        return;
    }
    verifying.value = true;
    errorMsg.value = '';
    try {
        await api.post('/api/v1/auth/2fa/enable', { code: otpCode.value });
        step.value = 'done';
        // حدّث auth store
        await auth.fetchUser?.();
        setTimeout(() => router.replace('/'), 1500);
    }
    catch (e) {
        const msg = e
            .response?.data?.detail ?? 'رمز التحقق غير صحيح';
        errorMsg.value = msg;
    }
    finally {
        verifying.value = false;
    }
}
onMounted(loadQR);
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
__VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
    ...{ class: "min-h-screen bg-owner-bg flex flex-col items-center justify-center px-6" },
    ...{ style: {} },
});
if (__VLS_ctx.step === 'loading') {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "text-owner-muted text-sm animate-pulse" },
    });
}
else if (__VLS_ctx.step === 'error') {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "text-4xl mb-4" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ class: "text-owner-red text-sm mb-6 text-center" },
    });
    (__VLS_ctx.errorMsg);
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.loadQR) },
        ...{ class: "bg-owner-green text-black font-bold rounded-xl px-8 py-3 text-sm" },
    });
}
else if (__VLS_ctx.step === 'done') {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "text-4xl mb-4" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({
        ...{ class: "text-owner-text font-bold mb-2 text-center" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ class: "text-owner-muted text-sm text-center" },
    });
}
else if (__VLS_ctx.step === 'show_qr') {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "text-4xl mb-6" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({
        ...{ class: "text-owner-text font-bold mb-2 text-center" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ class: "text-owner-muted text-xs mb-6 text-center max-w-xs" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "bg-white p-4 rounded-2xl mb-4 shadow-lg" },
    });
    if (__VLS_ctx.qrCodeUrl) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.img)({
            src: (__VLS_ctx.qrCodeUrl),
            alt: "رمز QR للتحقق بخطوتين",
            ...{ class: "w-48 h-48 block" },
        });
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!!(__VLS_ctx.step === 'loading'))
                    return;
                if (!!(__VLS_ctx.step === 'error'))
                    return;
                if (!!(__VLS_ctx.step === 'done'))
                    return;
                if (!(__VLS_ctx.step === 'show_qr'))
                    return;
                __VLS_ctx.showSecret = !__VLS_ctx.showSecret;
            } },
        ...{ class: "text-xs text-owner-muted underline mb-6" },
    });
    (__VLS_ctx.showSecret ? 'إخفاء' : 'عرض');
    if (__VLS_ctx.showSecret) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "bg-owner-card border border-owner-border rounded-xl px-4 py-2 text-xs font-mono text-owner-text text-center tracking-widest mb-6 select-all" },
            dir: "ltr",
        });
        (__VLS_ctx.secretKey);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!!(__VLS_ctx.step === 'loading'))
                    return;
                if (!!(__VLS_ctx.step === 'error'))
                    return;
                if (!!(__VLS_ctx.step === 'done'))
                    return;
                if (!(__VLS_ctx.step === 'show_qr'))
                    return;
                __VLS_ctx.step = 'verify';
            } },
        ...{ class: "bg-owner-green text-black font-bold rounded-xl px-8 py-3 text-sm w-full max-w-xs" },
    });
}
else if (__VLS_ctx.step === 'verify') {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
        ...{ class: "text-4xl mb-6" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.h2, __VLS_intrinsicElements.h2)({
        ...{ class: "text-owner-text font-bold mb-2 text-center" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.p, __VLS_intrinsicElements.p)({
        ...{ class: "text-owner-muted text-xs mb-6 text-center max-w-xs" },
    });
    __VLS_asFunctionalElement(__VLS_intrinsicElements.input)({
        ...{ onKeyup: (__VLS_ctx.confirmSetup) },
        value: (__VLS_ctx.otpCode),
        type: "text",
        inputmode: "numeric",
        autocomplete: "one-time-code",
        maxlength: "6",
        placeholder: "000000",
        dir: "ltr",
        ...{ class: "w-full max-w-xs bg-owner-card border border-owner-border rounded-xl px-4 py-3 text-owner-text text-center text-2xl tracking-[0.5em] outline-none focus:border-owner-green mb-4" },
        disabled: (__VLS_ctx.verifying),
    });
    if (__VLS_ctx.errorMsg) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.div, __VLS_intrinsicElements.div)({
            ...{ class: "text-xs text-owner-red bg-red-950/40 border border-red-900/50 rounded-xl px-4 py-3 mb-4 w-full max-w-xs text-center" },
            role: "alert",
        });
        (__VLS_ctx.errorMsg);
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (__VLS_ctx.confirmSetup) },
        ...{ class: "bg-owner-green text-black font-bold rounded-xl px-8 py-3 text-sm w-full max-w-xs disabled:opacity-50" },
        disabled: (__VLS_ctx.verifying || __VLS_ctx.otpCode.length < 6),
    });
    if (__VLS_ctx.verifying) {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    }
    else {
        __VLS_asFunctionalElement(__VLS_intrinsicElements.span, __VLS_intrinsicElements.span)({});
    }
    __VLS_asFunctionalElement(__VLS_intrinsicElements.button, __VLS_intrinsicElements.button)({
        ...{ onClick: (...[$event]) => {
                if (!!(__VLS_ctx.step === 'loading'))
                    return;
                if (!!(__VLS_ctx.step === 'error'))
                    return;
                if (!!(__VLS_ctx.step === 'done'))
                    return;
                if (!!(__VLS_ctx.step === 'show_qr'))
                    return;
                if (!(__VLS_ctx.step === 'verify'))
                    return;
                __VLS_ctx.step = 'show_qr';
            } },
        ...{ class: "text-xs text-owner-muted mt-4" },
    });
}
/** @type {__VLS_StyleScopedClasses['min-h-screen']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-owner-bg']} */ ;
/** @type {__VLS_StyleScopedClasses['flex']} */ ;
/** @type {__VLS_StyleScopedClasses['flex-col']} */ ;
/** @type {__VLS_StyleScopedClasses['items-center']} */ ;
/** @type {__VLS_StyleScopedClasses['justify-center']} */ ;
/** @type {__VLS_StyleScopedClasses['px-6']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['text-sm']} */ ;
/** @type {__VLS_StyleScopedClasses['animate-pulse']} */ ;
/** @type {__VLS_StyleScopedClasses['text-4xl']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-4']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-red']} */ ;
/** @type {__VLS_StyleScopedClasses['text-sm']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-6']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-owner-green']} */ ;
/** @type {__VLS_StyleScopedClasses['text-black']} */ ;
/** @type {__VLS_StyleScopedClasses['font-bold']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
/** @type {__VLS_StyleScopedClasses['px-8']} */ ;
/** @type {__VLS_StyleScopedClasses['py-3']} */ ;
/** @type {__VLS_StyleScopedClasses['text-sm']} */ ;
/** @type {__VLS_StyleScopedClasses['text-4xl']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-4']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['font-bold']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-2']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['text-sm']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['text-4xl']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-6']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['font-bold']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-2']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-6']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['max-w-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-white']} */ ;
/** @type {__VLS_StyleScopedClasses['p-4']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-2xl']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-4']} */ ;
/** @type {__VLS_StyleScopedClasses['shadow-lg']} */ ;
/** @type {__VLS_StyleScopedClasses['w-48']} */ ;
/** @type {__VLS_StyleScopedClasses['h-48']} */ ;
/** @type {__VLS_StyleScopedClasses['block']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['underline']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-6']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['border']} */ ;
/** @type {__VLS_StyleScopedClasses['border-owner-border']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
/** @type {__VLS_StyleScopedClasses['px-4']} */ ;
/** @type {__VLS_StyleScopedClasses['py-2']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['font-mono']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['tracking-widest']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-6']} */ ;
/** @type {__VLS_StyleScopedClasses['select-all']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-owner-green']} */ ;
/** @type {__VLS_StyleScopedClasses['text-black']} */ ;
/** @type {__VLS_StyleScopedClasses['font-bold']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
/** @type {__VLS_StyleScopedClasses['px-8']} */ ;
/** @type {__VLS_StyleScopedClasses['py-3']} */ ;
/** @type {__VLS_StyleScopedClasses['text-sm']} */ ;
/** @type {__VLS_StyleScopedClasses['w-full']} */ ;
/** @type {__VLS_StyleScopedClasses['max-w-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-4xl']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-6']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['font-bold']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-2']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-6']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['max-w-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['w-full']} */ ;
/** @type {__VLS_StyleScopedClasses['max-w-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-owner-card']} */ ;
/** @type {__VLS_StyleScopedClasses['border']} */ ;
/** @type {__VLS_StyleScopedClasses['border-owner-border']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
/** @type {__VLS_StyleScopedClasses['px-4']} */ ;
/** @type {__VLS_StyleScopedClasses['py-3']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-text']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['text-2xl']} */ ;
/** @type {__VLS_StyleScopedClasses['tracking-[0.5em]']} */ ;
/** @type {__VLS_StyleScopedClasses['outline-none']} */ ;
/** @type {__VLS_StyleScopedClasses['focus:border-owner-green']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-4']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-red']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-red-950/40']} */ ;
/** @type {__VLS_StyleScopedClasses['border']} */ ;
/** @type {__VLS_StyleScopedClasses['border-red-900/50']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
/** @type {__VLS_StyleScopedClasses['px-4']} */ ;
/** @type {__VLS_StyleScopedClasses['py-3']} */ ;
/** @type {__VLS_StyleScopedClasses['mb-4']} */ ;
/** @type {__VLS_StyleScopedClasses['w-full']} */ ;
/** @type {__VLS_StyleScopedClasses['max-w-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-center']} */ ;
/** @type {__VLS_StyleScopedClasses['bg-owner-green']} */ ;
/** @type {__VLS_StyleScopedClasses['text-black']} */ ;
/** @type {__VLS_StyleScopedClasses['font-bold']} */ ;
/** @type {__VLS_StyleScopedClasses['rounded-xl']} */ ;
/** @type {__VLS_StyleScopedClasses['px-8']} */ ;
/** @type {__VLS_StyleScopedClasses['py-3']} */ ;
/** @type {__VLS_StyleScopedClasses['text-sm']} */ ;
/** @type {__VLS_StyleScopedClasses['w-full']} */ ;
/** @type {__VLS_StyleScopedClasses['max-w-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['disabled:opacity-50']} */ ;
/** @type {__VLS_StyleScopedClasses['text-xs']} */ ;
/** @type {__VLS_StyleScopedClasses['text-owner-muted']} */ ;
/** @type {__VLS_StyleScopedClasses['mt-4']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            step: step,
            qrCodeUrl: qrCodeUrl,
            secretKey: secretKey,
            otpCode: otpCode,
            errorMsg: errorMsg,
            verifying: verifying,
            showSecret: showSecret,
            loadQR: loadQR,
            confirmSetup: confirmSetup,
        };
    },
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
});
; /* PartiallyEnd: #4569/main.vue */
