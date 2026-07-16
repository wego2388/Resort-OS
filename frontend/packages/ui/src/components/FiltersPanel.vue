<script setup lang="ts">
/**
 * FiltersPanel — لوحة فلترة موحّدة لكل الجداول.
 *
 * variant='inline'  → حقول أفقية فوق الجدول (desktop)
 * variant='drawer'  → زرار "فلترة" يفتح AppDrawer (mobile أو فلاتر كثيرة)
 *
 * الاستخدام:
 *   <FiltersPanel
 *     :fields="[{ key:'status', label:'الحالة', type:'select', options:[...] }]"
 *     v-model="filters"
 *     @apply="reload()"
 *     @reset="reload()"
 *   />
 */
import { ref, computed, watch } from 'vue'
import AppButton from './Button.vue'
import AppDrawer from './Drawer.vue'
import AppIcon from './Icon.vue'
import { fieldClasses, fieldLabelClasses } from '../utils/inputClasses'

export interface SelectOption { value: string | number; label: string }
export type FilterFieldType = 'text' | 'select' | 'date' | 'date-range' | 'boolean' | 'number'

export interface FilterField {
  key: string
  label: string
  type: FilterFieldType
  options?: SelectOption[]
  placeholder?: string
}

const props = withDefaults(defineProps<{
  fields: FilterField[]
  modelValue: Record<string, unknown>
  loading?: boolean
  variant?: 'inline' | 'drawer'
}>(), { variant: 'inline' })

const emit = defineEmits<{
  'update:modelValue': [v: Record<string, unknown>]
  apply: []
  reset: []
}>()

// كوبي محلي من الـ filters — يتغير مباشرة لو inline، أو عند الضغط Apply في الـ drawer
const local = ref<Record<string, unknown>>({ ...props.modelValue })
watch(() => props.modelValue, v => { local.value = { ...v } }, { deep: true })

// عدد الفلاتر المفعّلة (للبادج على زرار الـ drawer)
const activeCount = computed(() =>
  Object.values(props.modelValue).filter(v => v !== '' && v !== null && v !== undefined).length,
)

const drawerOpen = ref(false)

function updateField(key: string, value: unknown) {
  local.value = { ...local.value, [key]: value }
  if (props.variant === 'inline') {
    emit('update:modelValue', local.value)
    emit('apply')
  }
}

function applyDrawer() {
  emit('update:modelValue', local.value)
  emit('apply')
  drawerOpen.value = false
}

function resetAll() {
  const empty: Record<string, unknown> = {}
  for (const f of props.fields) {
    empty[f.key] = f.type === 'boolean' ? false : ''
  }
  local.value = empty
  emit('update:modelValue', empty)
  emit('reset')
  if (props.variant === 'drawer') drawerOpen.value = false
}

function getVal(key: string): unknown {
  return local.value[key] ?? ''
}
</script>

<template>
  <!-- ══ INLINE ══ -->
  <div v-if="variant === 'inline'" class="flex flex-wrap items-end gap-3">
    <template v-for="field in fields" :key="field.key">
      <!-- text -->
      <div v-if="field.type === 'text'" class="flex flex-col gap-1">
        <label :class="fieldLabelClasses">{{ field.label }}</label>
        <input
          type="text"
          :placeholder="field.placeholder ?? field.label"
          :value="(getVal(field.key) as string)"
          @input="updateField(field.key, ($event.target as HTMLInputElement).value)"
          :class="[fieldClasses(), 'w-44']"
        />
      </div>

      <!-- select -->
      <div v-else-if="field.type === 'select'" class="flex flex-col gap-1">
        <label :class="fieldLabelClasses">{{ field.label }}</label>
        <select
          :value="(getVal(field.key) as string)"
          @change="updateField(field.key, ($event.target as HTMLSelectElement).value)"
          :class="[fieldClasses(), 'w-44']"
        >
          <option value="">{{ field.placeholder ?? 'الكل' }}</option>
          <option v-for="opt in field.options" :key="opt.value" :value="opt.value">
            {{ opt.label }}
          </option>
        </select>
      </div>

      <!-- date -->
      <div v-else-if="field.type === 'date'" class="flex flex-col gap-1">
        <label :class="fieldLabelClasses">{{ field.label }}</label>
        <input
          type="date"
          :value="(getVal(field.key) as string)"
          @input="updateField(field.key, ($event.target as HTMLInputElement).value)"
          :class="[fieldClasses(), 'w-44']"
        />
      </div>

      <!-- date-range: يُرسل كـ { from, to } في نفس الـ key -->
      <div v-else-if="field.type === 'date-range'" class="flex items-end gap-2">
        <div class="flex flex-col gap-1">
          <label :class="fieldLabelClasses">{{ field.label }} (من)</label>
          <input
            type="date"
            :value="((getVal(field.key) as any)?.from ?? '')"
            @input="updateField(field.key, { ...(local[field.key] as any ?? {}), from: ($event.target as HTMLInputElement).value })"
            :class="[fieldClasses(), 'w-40']"
          />
        </div>
        <div class="flex flex-col gap-1">
          <label :class="fieldLabelClasses">إلى</label>
          <input
            type="date"
            :value="((getVal(field.key) as any)?.to ?? '')"
            @input="updateField(field.key, { ...(local[field.key] as any ?? {}), to: ($event.target as HTMLInputElement).value })"
            :class="[fieldClasses(), 'w-40']"
          />
        </div>
      </div>

      <!-- boolean -->
      <div v-else-if="field.type === 'boolean'" class="flex items-end pb-2">
        <label class="flex items-center gap-2 cursor-pointer select-none text-sm text-gray-700 dark:text-gray-300 font-medium">
          <input
            type="checkbox"
            :checked="(getVal(field.key) as boolean)"
            @change="updateField(field.key, ($event.target as HTMLInputElement).checked)"
            class="w-4 h-4 rounded border-stone-300 dark:border-gray-600 text-primary-700 focus:ring-primary-500"
          />
          {{ field.label }}
        </label>
      </div>

      <!-- number -->
      <div v-else-if="field.type === 'number'" class="flex flex-col gap-1">
        <label :class="fieldLabelClasses">{{ field.label }}</label>
        <input
          type="number"
          :placeholder="field.placeholder"
          :value="(getVal(field.key) as string)"
          @input="updateField(field.key, ($event.target as HTMLInputElement).value)"
          :class="[fieldClasses(), 'w-36']"
        />
      </div>
    </template>

    <!-- Reset (لو في فلاتر مفعّلة) -->
    <button
      v-if="activeCount > 0"
      @click="resetAll"
      class="flex items-center gap-1.5 text-xs font-semibold text-muted hover:text-danger transition-colors pb-2"
    >
      <AppIcon name="close" size="xs" />
      مسح الفلاتر
    </button>
  </div>

  <!-- ══ DRAWER TRIGGER ══ -->
  <template v-else>
    <button
      @click="drawerOpen = true"
      :disabled="loading"
      class="relative inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-stone-200 dark:border-border bg-white dark:bg-surface text-sm font-semibold text-gray-700 dark:text-gray-300 hover:bg-stone-50 dark:hover:bg-gray-700/50 transition-colors focus:outline-none focus-visible:shadow-focus-ring disabled:opacity-50"
    >
      <AppIcon name="filter" size="sm" />
      فلترة
      <!-- Badge عدد الفلاتر المفعّلة -->
      <span
        v-if="activeCount > 0"
        class="absolute -top-1.5 -end-1.5 w-5 h-5 rounded-full bg-primary-700 text-white text-[10px] font-bold flex items-center justify-center"
      >
        {{ activeCount }}
      </span>
    </button>

    <AppDrawer :open="drawerOpen" title="فلترة النتائج" @close="drawerOpen = false">
      <div class="p-4 space-y-4">
        <template v-for="field in fields" :key="field.key">
          <!-- text -->
          <div v-if="field.type === 'text'" class="flex flex-col gap-1.5">
            <label :class="fieldLabelClasses">{{ field.label }}</label>
            <input
              type="text"
              :placeholder="field.placeholder ?? field.label"
              :value="(getVal(field.key) as string)"
              @input="local[field.key] = ($event.target as HTMLInputElement).value"
              :class="fieldClasses()"
            />
          </div>

          <!-- select -->
          <div v-else-if="field.type === 'select'" class="flex flex-col gap-1.5">
            <label :class="fieldLabelClasses">{{ field.label }}</label>
            <select
              :value="(getVal(field.key) as string)"
              @change="local[field.key] = ($event.target as HTMLSelectElement).value"
              :class="fieldClasses()"
            >
              <option value="">{{ field.placeholder ?? 'الكل' }}</option>
              <option v-for="opt in field.options" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>

          <!-- date-range -->
          <div v-else-if="field.type === 'date-range'" class="flex flex-col gap-1.5">
            <label :class="fieldLabelClasses">{{ field.label }}</label>
            <div class="flex gap-2">
              <input
                type="date"
                :value="((getVal(field.key) as any)?.from ?? '')"
                @input="local[field.key] = { ...(local[field.key] as any ?? {}), from: ($event.target as HTMLInputElement).value }"
                :class="[fieldClasses(), 'flex-1']"
              />
              <input
                type="date"
                :value="((getVal(field.key) as any)?.to ?? '')"
                @input="local[field.key] = { ...(local[field.key] as any ?? {}), to: ($event.target as HTMLInputElement).value }"
                :class="[fieldClasses(), 'flex-1']"
              />
            </div>
          </div>

          <!-- boolean -->
          <div v-else-if="field.type === 'boolean'" class="flex items-center gap-2">
            <input
              type="checkbox"
              :id="`drawer-filter-${field.key}`"
              :checked="(getVal(field.key) as boolean)"
              @change="local[field.key] = ($event.target as HTMLInputElement).checked"
              class="w-4 h-4 rounded border-stone-300 dark:border-gray-600 text-primary-700 focus:ring-primary-500"
            />
            <label :for="`drawer-filter-${field.key}`" class="text-sm font-medium text-gray-700 dark:text-gray-300 cursor-pointer">
              {{ field.label }}
            </label>
          </div>
        </template>
      </div>

      <template #footer>
        <div class="flex gap-3 p-4 border-t border-stone-100 dark:border-border">
          <AppButton variant="ghost" class="flex-1" @click="resetAll">مسح الكل</AppButton>
          <AppButton variant="primary" class="flex-1" :loading="loading" @click="applyDrawer">
            تطبيق الفلاتر
          </AppButton>
        </div>
      </template>
    </AppDrawer>
  </template>
</template>
