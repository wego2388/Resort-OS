/// <reference types="../../node_modules/.vue-global-types/vue_3.5_0_0_0.d.ts" />
/**
 * SparkLine — SVG inline لآخر N نقطة.
 * بدون chart.js — 7 نقاط لا تستحق 200KB dependency.
 * الـ trend محسوب من الـ values مباشرة.
 */
import { computed } from 'vue';
const props = withDefaults(defineProps(), {
    color: '#22C55E',
    height: 40,
    showDot: true,
});
const WIDTH = 140;
const HEIGHT = computed(() => props.height);
const PAD = 4;
const points = computed(() => {
    const vals = props.values;
    if (!vals.length)
        return '';
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const range = max - min || 1;
    const xStep = (WIDTH - PAD * 2) / Math.max(vals.length - 1, 1);
    return vals.map((v, i) => {
        const x = PAD + i * xStep;
        const y = HEIGHT.value - PAD - ((v - min) / range) * (HEIGHT.value - PAD * 2);
        return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(' ');
});
const lastDot = computed(() => {
    const vals = props.values;
    if (!vals.length)
        return null;
    const min = Math.min(...vals);
    const max = Math.max(...vals);
    const range = max - min || 1;
    const xStep = (WIDTH - PAD * 2) / Math.max(vals.length - 1, 1);
    const i = vals.length - 1;
    return {
        x: PAD + i * xStep,
        y: HEIGHT.value - PAD - ((vals[i] - min) / range) * (HEIGHT.value - PAD * 2),
    };
});
// trend: صاعد/هابط/ثابت
const trend = computed(() => {
    const v = props.values;
    if (v.length < 2)
        return 'flat';
    const last = v[v.length - 1];
    const first = v[0];
    if (last > first)
        return 'up';
    if (last < first)
        return 'down';
    return 'flat';
});
const lineColor = computed(() => {
    if (props.color !== '#22C55E')
        return props.color;
    if (trend.value === 'up')
        return '#22C55E';
    if (trend.value === 'down')
        return '#EF4444';
    return '#A8A29E';
});
debugger; /* PartiallyEnd: #3632/scriptSetup.vue */
const __VLS_withDefaultsArg = (function (t) { return t; })({
    color: '#22C55E',
    height: 40,
    showDot: true,
});
const __VLS_ctx = {};
let __VLS_components;
let __VLS_directives;
__VLS_asFunctionalElement(__VLS_intrinsicElements.svg, __VLS_intrinsicElements.svg)({
    viewBox: (`0 0 ${__VLS_ctx.WIDTH} ${__VLS_ctx.HEIGHT}`),
    height: (__VLS_ctx.HEIGHT),
    width: "100%",
    ...{ class: "sparkline" },
    'aria-hidden': "true",
    preserveAspectRatio: "none",
});
if (__VLS_ctx.points) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.polyline)({
        points: (__VLS_ctx.points),
        fill: "none",
        stroke: (__VLS_ctx.lineColor),
        'stroke-width': "1.5",
        'stroke-linecap': "round",
        'stroke-linejoin': "round",
        opacity: "0.85",
    });
}
if (__VLS_ctx.showDot && __VLS_ctx.lastDot) {
    __VLS_asFunctionalElement(__VLS_intrinsicElements.circle)({
        cx: (__VLS_ctx.lastDot.x),
        cy: (__VLS_ctx.lastDot.y),
        r: "2.5",
        fill: (__VLS_ctx.lineColor),
    });
}
/** @type {__VLS_StyleScopedClasses['sparkline']} */ ;
var __VLS_dollars;
const __VLS_self = (await import('vue')).defineComponent({
    setup() {
        return {
            WIDTH: WIDTH,
            HEIGHT: HEIGHT,
            points: points,
            lastDot: lastDot,
            lineColor: lineColor,
        };
    },
    __typeProps: {},
    props: {},
});
export default (await import('vue')).defineComponent({
    setup() {
        return {};
    },
    __typeProps: {},
    props: {},
});
; /* PartiallyEnd: #4569/main.vue */
