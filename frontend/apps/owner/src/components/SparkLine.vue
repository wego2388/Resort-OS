<script setup lang="ts">
/**
 * SparkLine — SVG inline لآخر N نقطة.
 * بدون chart.js — 7 نقاط لا تستحق 200KB dependency.
 * الـ trend محسوب من الـ values مباشرة.
 */
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  values: number[]
  /** لون صريح اختياري — لو مش متمرر، اللون بياخد اتجاه القيم (صاعد/هابط/ثابت)
   * من متغيرات الـ CSS الحالية (--owner-green/red/muted)، فبيتغيّر صح مع
   * تبديل الوضع الفاتح/الداكن من غير أي منطق إضافي هنا. */
  color?: string
  height?: number
  showDot?: boolean
}>(), {
  height: 40,
  showDot: true,
})

const WIDTH  = 140
const HEIGHT = computed(() => props.height)
const PAD    = 4

const points = computed(() => {
  const vals = props.values
  if (!vals.length) return ''

  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const range = max - min || 1

  const xStep = (WIDTH - PAD * 2) / Math.max(vals.length - 1, 1)

  return vals.map((v, i) => {
    const x = PAD + i * xStep
    const y = HEIGHT.value - PAD - ((v - min) / range) * (HEIGHT.value - PAD * 2)
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
})

const lastDot = computed(() => {
  const vals = props.values
  if (!vals.length) return null
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const range = max - min || 1
  const xStep = (WIDTH - PAD * 2) / Math.max(vals.length - 1, 1)
  const i = vals.length - 1
  return {
    x: PAD + i * xStep,
    y: HEIGHT.value - PAD - ((vals[i] - min) / range) * (HEIGHT.value - PAD * 2),
  }
})

// trend: صاعد/هابط/ثابت
const trend = computed(() => {
  const v = props.values
  if (v.length < 2) return 'flat'
  const last  = v[v.length - 1]
  const first = v[0]
  if (last > first) return 'up'
  if (last < first) return 'down'
  return 'flat'
})

const lineColor = computed(() => {
  if (props.color) return props.color
  if (trend.value === 'up')   return 'rgb(var(--owner-green))'
  if (trend.value === 'down') return 'rgb(var(--owner-red))'
  return 'rgb(var(--owner-muted))'
})
</script>

<template>
  <svg
    :viewBox="`0 0 ${WIDTH} ${HEIGHT}`"
    :height="HEIGHT"
    width="100%"
    class="sparkline"
    aria-hidden="true"
    preserveAspectRatio="none"
  >
    <polyline
      v-if="points"
      :points="points"
      fill="none"
      :stroke="lineColor"
      stroke-width="1.5"
      stroke-linecap="round"
      stroke-linejoin="round"
      opacity="0.85"
    />
    <!-- النقطة الأخيرة -->
    <circle
      v-if="showDot && lastDot"
      :cx="lastDot.x"
      :cy="lastDot.y"
      r="2.5"
      :fill="lineColor"
    />
  </svg>
</template>
