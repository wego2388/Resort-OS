<script setup lang="ts">
/**
 * DateRangePicker — فلتر الفترة الزمنية لشاشات التحليل (Decision 0004 §7b).
 * أزرار سريعة: اليوم / أمبارح / هذا الأسبوع / هذا الشهر
 * + date inputs للفترة الحرة.
 * يُصدر { date_from, date_to } كـ ISO strings (YYYY-MM-DD).
 */
import { ref, watch } from 'vue'

const emit = defineEmits<{
  (e: 'change', value: { date_from: string; date_to: string }): void
}>()

/** تنسيق التاريخ المحلي → YYYY-MM-DD بدون تحويل UTC يغيّر يوم القاهرة. */
function toISO(d: Date): string {
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function today(): Date { return new Date() }

function makeRange(from: Date, to: Date) {
  return { date_from: toISO(from), date_to: toISO(to) }
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
      const d = today(); d.setDate(d.getDate() - 1)
      return makeRange(d, d)
    },
  },
  {
    label: 'هذا الأسبوع',
    key: 'week',
    get: () => {
      const t = today()
      const mon = new Date(t)
      mon.setDate(t.getDate() - t.getDay() + (t.getDay() === 0 ? -6 : 1))
      return makeRange(mon, t)
    },
  },
  {
    label: 'هذا الشهر',
    key: 'month',
    get: () => {
      const t = today()
      return makeRange(new Date(t.getFullYear(), t.getMonth(), 1), t)
    },
  },
] as const

type PresetKey = typeof presets[number]['key'] | 'custom'

// الافتراضي: هذا الشهر
const active = ref<PresetKey>('month')
const customFrom = ref('')
const customTo   = ref('')

/** يطلق الـ emit بالقيم الصحيحة */
function applyPreset(key: PresetKey) {
  active.value = key
  if (key === 'custom') return
  const preset = presets.find(p => p.key === key)
  if (!preset) return
  const range = preset.get()
  customFrom.value = range.date_from
  customTo.value   = range.date_to
  emit('change', range)
}

// عند تغيير custom dates يدوياً
watch([customFrom, customTo], ([from, to]) => {
  if (active.value === 'custom' && from && to && from <= to) {
    emit('change', { date_from: from, date_to: to })
  }
})

// إطلاق الافتراضي عند mount
applyPreset('month')
</script>

<template>
  <div class="owner-card space-y-3" role="group" aria-label="فلتر الفترة الزمنية">
    <div class="flex items-center justify-between gap-3">
      <span class="section-label !mb-0">الفترة</span>
      <span v-if="customFrom && customTo" class="text-[11px] text-owner-muted" dir="ltr">
        {{ customFrom }} — {{ customTo }}
      </span>
    </div>
    <!-- أزرار الـ presets -->
    <div class="flex gap-2 flex-wrap">
      <button
        v-for="preset in presets"
        :key="preset.key"
        class="px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors touch-target"
        :class="active === preset.key
          ? 'bg-owner-green text-black'
          : 'bg-owner-bg text-owner-muted border border-owner-border'"
        @click="applyPreset(preset.key)"
      >
        {{ preset.label }}
      </button>
      <button
        class="px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors touch-target"
        :class="active === 'custom'
          ? 'bg-owner-green text-black'
          : 'bg-owner-bg text-owner-muted border border-owner-border'"
        @click="active = 'custom'"
      >
        فترة مخصصة
      </button>
    </div>

    <!-- Custom date inputs — تظهر فقط عند اختيار "فترة مخصصة" -->
    <div v-if="active === 'custom'" class="flex gap-2 items-center">
      <div class="flex-1">
        <label class="block text-[10px] text-owner-muted mb-0.5">من</label>
        <input
          v-model="customFrom"
          type="date"
          class="w-full bg-owner-bg border border-owner-border rounded-lg px-2 py-1.5 text-xs text-owner-text outline-none focus:border-owner-green"
          dir="ltr"
        />
      </div>
      <div class="flex-1">
        <label class="block text-[10px] text-owner-muted mb-0.5">إلى</label>
        <input
          v-model="customTo"
          type="date"
          class="w-full bg-owner-bg border border-owner-border rounded-lg px-2 py-1.5 text-xs text-owner-text outline-none focus:border-owner-green"
          dir="ltr"
          :min="customFrom"
        />
      </div>
    </div>
  </div>
</template>
