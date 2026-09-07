<script setup lang="ts">
/**
 * SparkLine — SVG inline لآخر N نقطة.
 * بدون chart.js — 7 نقاط لا تستحق 200KB dependency.
 * الـ trend محسوب من الـ values مباشرة.
 *
 * 2026-08-19: تحسينات بعد ملاحظة محمد ("مؤشر الرسم البياني محتاج
 * تحسينات") — منحنى ناعم بدل خطوط مستقيمة متكسّرة، تعبئة تدرّجية خفيفة
 * تحت الخط (شكل sparkline قياسي في تطبيقات مالية حقيقية)، وprop جديد
 * `invert` لعكس دلالة اللون لمقاييس زي المصروفات (نزول = كويس = أخضر،
 * عكس الإيراد تمامًا) — كان اللون بيتحدد بـ"صاعد=أخضر/هابط=أحمر" دايمًا
 * بغض النظر عن نوع المقياس، وده غلط منطقيًا لأي مقياس "الأقل أحسن".
 */
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  values: number[]
  /** لون صريح اختياري — لو مش متمرر، اللون بياخد اتجاه القيم (صاعد/هابط/ثابت)
   * من متغيرات الـ CSS الحالية (--owner-green/red/muted)، فبيتغيّر صح مع
   * تبديل الوضع الفاتح/الداكن من غير أي منطق إضافي هنا. */
  color?: string
  /** true للمقاييس اللي "الأقل فيها أحسن" (زي المصروفات) — بيعكس دلالة
   * اللون: نزول = أخضر (كويس)، صعود = أحمر (وحش). الافتراضي false يناسب
   * أي مقياس "الأكتر فيه أحسن" زي الإيراد. */
  invert?: boolean
  height?: number
  showDot?: boolean
}>(), {
  height: 40,
  showDot: true,
  invert: false,
})

const WIDTH  = 140
const HEIGHT = computed(() => props.height)
const PAD    = 4

// gradientId فريد لكل instance — عشان لو أكتر من sparkline على نفس
// الصفحة، الـ<linearGradient id> متتلخبطش مع بعض (IDs عالمية في الـDOM).
const gradientId = `spark-fill-${Math.random().toString(36).slice(2, 9)}`

const coords = computed(() => {
  const vals = props.values
  if (!vals.length) return []

  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const range = max - min || 1
  const xStep = (WIDTH - PAD * 2) / Math.max(vals.length - 1, 1)

  return vals.map((v, i) => ({
    x: PAD + i * xStep,
    y: HEIGHT.value - PAD - ((v - min) / range) * (HEIGHT.value - PAD * 2),
  }))
})

/** منحنى ناعم عبر نقاط المنتصف بين كل نقطتين متتاليتين (Q command) —
 * تقنية خفيفة معروفة لتنعيم خط SVG من غير مكتبة رسم كاملة. */
const linePath = computed(() => {
  const pts = coords.value
  if (pts.length === 0) return ''
  if (pts.length === 1) return `M ${pts[0].x},${pts[0].y}`

  let d = `M ${pts[0].x},${pts[0].y}`
  for (let i = 1; i < pts.length; i++) {
    const prev = pts[i - 1]
    const curr = pts[i]
    const midX = (prev.x + curr.x) / 2
    const midY = (prev.y + curr.y) / 2
    d += ` Q ${prev.x},${prev.y} ${midX},${midY}`
  }
  const last = pts[pts.length - 1]
  d += ` L ${last.x},${last.y}`
  return d
})

/** نفس منحنى الخط، مقفول لأسفل عند خط القاعدة — للتعبئة التدرّجية. */
const areaPath = computed(() => {
  const pts = coords.value
  if (pts.length < 2) return ''
  const baseline = HEIGHT.value - PAD
  return `${linePath.value} L ${pts[pts.length - 1].x},${baseline} L ${pts[0].x},${baseline} Z`
})

const lastDot = computed(() => {
  const pts = coords.value
  return pts.length ? pts[pts.length - 1] : null
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

/** "good" = الاتجاه ده إيجابي فعليًا للمقياس ده (بعد مراعاة invert) —
 * بيحدد اللون الفعلي، منفصل عن اتجاه الرقم الخام (up/down). */
const isGoodTrend = computed(() => {
  if (trend.value === 'flat') return null
  const rising = trend.value === 'up'
  return props.invert ? !rising : rising
})

const lineColor = computed(() => {
  if (props.color) return props.color
  if (isGoodTrend.value === true)  return 'rgb(var(--owner-green))'
  if (isGoodTrend.value === false) return 'rgb(var(--owner-red))'
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
    <defs>
      <linearGradient :id="gradientId" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" :stop-color="lineColor" stop-opacity="0.25" />
        <stop offset="100%" :stop-color="lineColor" stop-opacity="0" />
      </linearGradient>
    </defs>

    <!-- تعبئة تدرّجية خفيفة تحت المنحنى -->
    <path v-if="areaPath" :d="areaPath" :fill="`url(#${gradientId})`" stroke="none" />

    <!-- المنحنى الناعم -->
    <path
      v-if="linePath"
      :d="linePath"
      fill="none"
      :stroke="lineColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
    />

    <!-- توهّج خفيف خلف النقطة الأخيرة + النقطة نفسها -->
    <template v-if="showDot && lastDot">
      <circle :cx="lastDot.x" :cy="lastDot.y" r="5" :fill="lineColor" opacity="0.18" />
      <circle :cx="lastDot.x" :cy="lastDot.y" r="2.5" :fill="lineColor" />
    </template>
  </svg>
</template>
