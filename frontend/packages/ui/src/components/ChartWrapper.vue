<script setup lang="ts">
/**
 * ChartWrapper — DS-compliant chart shell.
 * Wraps vue-chartjs (Chart.js v4) behind a zero-boilerplate API.
 * Consumers describe *data + intent*, never Chart.js config objects.
 *
 * Supported types: bar | line | area | pie | doughnut
 * `area` = line chart with fill:true (common resort revenue trend use case)
 *
 * DS color palette:
 *   dataset[0] → primary-700   #0B4F8A
 *   dataset[1] → gold          #C9963C
 *   dataset[2] → success       #059669
 *   dataset[3] → info          #0284C7
 *   dataset[4] → warning       #D97706
 *   dataset[5] → indigo        #6366F1
 *   dataset[6+]→ cycles back
 */
import { computed, ref, watch, onMounted, onBeforeUnmount } from 'vue'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  LineElement,
  PointElement,
  ArcElement,
  Title,
  Tooltip,
  Legend,
  Filler,
  type ChartData,
  type ChartOptions,
  type TooltipItem,
} from 'chart.js'
import { Bar, Line, Pie, Doughnut } from 'vue-chartjs'
import Skeleton from './Skeleton.vue'
import ErrorState from './ErrorState.vue'
import EmptyState from './EmptyState.vue'

ChartJS.register(
  CategoryScale, LinearScale, BarElement, LineElement, PointElement,
  ArcElement, Title, Tooltip, Legend, Filler,
)

export interface ChartDataset {
  label: string
  data: number[]
  color?: string
}

export type ChartType = 'bar' | 'line' | 'area' | 'pie' | 'doughnut'

const DS_COLORS = [
  '#0B4F8A', // primary-700
  '#C9963C', // gold
  '#059669', // success
  '#0284C7', // info
  '#D97706', // warning
  '#6366F1', // indigo
  '#DB2777', // pink
  '#0891B2', // cyan
]

const props = withDefaults(defineProps<{
  type: ChartType
  labels: string[]
  datasets: ChartDataset[]
  title?: string
  loading?: boolean
  error?: boolean
  height?: number
  /** بيضيف " ج" على الـ Y-axis labels والـ tooltips */
  currency?: boolean
  /** بيضيف "%" على الـ Y-axis labels والـ tooltips */
  percentage?: boolean
  /** الـ Y-axis يبدأ من صفر (افتراضي: true) */
  beginAtZero?: boolean
}>(), {
  height: 300,
  beginAtZero: true,
})

const emit = defineEmits<{ retry: [] }>()

// ── مكوّن الرسم حسب النوع ────────────────────────────────────────────────
const ChartComponent = computed(() => {
  if (props.type === 'pie') return Pie
  if (props.type === 'doughnut') return Doughnut
  if (props.type === 'bar') return Bar
  return Line // line + area
})

// ── بناء datasets بألوان DS تلقائياً ─────────────────────────────────────
const chartData = computed<ChartData<any>>(() => {
  const isCircular = props.type === 'pie' || props.type === 'doughnut'

  if (isCircular) {
    // Pie/Doughnut: مجموعة ألوان لكل slice
    const single = props.datasets[0]
    return {
      labels: props.labels,
      datasets: [{
        label: single?.label ?? '',
        data: single?.data ?? [],
        backgroundColor: DS_COLORS,
        borderColor: '#ffffff',
        borderWidth: 2,
      }],
    }
  }

  return {
    labels: props.labels,
    datasets: props.datasets.map((ds, i) => {
      const color = ds.color ?? DS_COLORS[i % DS_COLORS.length]
      const isArea = props.type === 'area'
      return {
        label: ds.label,
        data: ds.data,
        backgroundColor: isArea
          ? hexToRgba(color, 0.15)
          : (props.type === 'bar' ? hexToRgba(color, 0.85) : color),
        borderColor: color,
        borderWidth: props.type === 'bar' ? 0 : 2,
        pointBackgroundColor: color,
        pointRadius: props.type === 'bar' ? 0 : 3,
        pointHoverRadius: props.type === 'bar' ? 0 : 5,
        fill: isArea,
        tension: isArea ? 0.4 : 0.3,
        borderRadius: props.type === 'bar' ? 6 : 0,
      }
    }),
  }
})

// ── Chart.js options ───────────────────────────────────────────────────────
const chartOptions = computed<ChartOptions<any>>(() => {
  const isCircular = props.type === 'pie' || props.type === 'doughnut'
  const suffix = props.currency ? ' ج' : props.percentage ? '%' : ''

  const base: ChartOptions<any> = {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 300 },
    plugins: {
      legend: {
        display: props.datasets.length > 1 || isCircular,
        position: 'bottom' as const,
        labels: {
          font: { family: 'Cairo, Tajawal, sans-serif', size: 12 },
          padding: 16,
          usePointStyle: true,
          pointStyleWidth: 8,
        },
      },
      title: {
        display: false, // نعرضه في الـ template بدل ما Chart.js يعرضه
      },
      tooltip: {
        rtl: true,
        titleFont: { family: 'Cairo, Tajawal, sans-serif' },
        bodyFont: { family: 'Cairo, Tajawal, sans-serif' },
        callbacks: {
          label: (ctx: TooltipItem<any>) => {
            const val = typeof ctx.raw === 'number' ? ctx.raw : 0
            const formatted = val.toLocaleString('ar-EG')
            return ` ${ctx.dataset.label}: ${formatted}${suffix}`
          },
        },
      },
    },
  }

  if (!isCircular) {
    base.scales = {
      x: {
        grid: { display: false },
        ticks: {
          font: { family: 'Cairo, Tajawal, sans-serif', size: 11 },
          color: '#78716C',
        },
      },
      y: {
        beginAtZero: props.beginAtZero,
        grid: { color: '#F5F4F2' },
        ticks: {
          font: { family: 'Cairo, Tajawal, sans-serif', size: 11 },
          color: '#78716C',
          callback: (value: number) => `${value.toLocaleString('ar-EG')}${suffix}`,
        },
      },
    }
  }

  return base
})

const hasData = computed(() =>
  props.datasets.length > 0 && props.datasets.some(ds => ds.data.length > 0),
)

// ── helper: hex → rgba ─────────────────────────────────────────────────────
function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${alpha})`
}
</script>

<template>
  <div class="bg-white dark:bg-surface rounded-xl border border-stone-200 dark:border-border shadow-elevation-1 overflow-hidden">
    <!-- Header -->
    <div v-if="title" class="px-5 pt-4 pb-2 border-b border-stone-100 dark:border-border/50">
      <h3 class="text-sm font-semibold text-gray-800 dark:text-gray-200">{{ title }}</h3>
    </div>

    <!-- States -->
    <div v-if="loading" class="p-5 space-y-3">
      <Skeleton class="h-4 w-1/3" />
      <Skeleton :style="{ height: height + 'px' }" />
    </div>

    <ErrorState
      v-else-if="error"
      message="تعذّر تحميل البيانات"
      @retry="emit('retry')"
    />

    <EmptyState
      v-else-if="!hasData"
      icon="chart"
      title="لا توجد بيانات"
    />

    <!-- Chart -->
    <div v-else class="p-4" :style="{ height: height + 'px' }">
      <component
        :is="ChartComponent"
        :data="chartData"
        :options="chartOptions"
        style="height: 100%; width: 100%;"
      />
    </div>
  </div>
</template>
