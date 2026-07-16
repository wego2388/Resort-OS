<script setup lang="ts">
/**
 * Combobox — searchable select مع keyboard navigation كامل.
 * الفرق عن AppSelect: يسمح بالكتابة والفلترة، async search، sublabel، groups.
 */
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import AppIcon from './Icon.vue'
import Skeleton from './Skeleton.vue'
import { fieldClasses, fieldLabelClasses, fieldErrorClasses, fieldHintClasses } from '../utils/inputClasses'

export interface ComboboxOption {
  value: string | number
  label: string
  sublabel?: string
  disabled?: boolean
  group?: string
}

const props = withDefaults(defineProps<{
  modelValue: string | number | null
  options: ComboboxOption[]
  placeholder?: string
  label?: string
  hint?: string
  error?: string
  loading?: boolean
  clearable?: boolean
  disabled?: boolean
  onSearch?: (query: string) => void
}>(), { placeholder: 'ابحث أو اختر...', clearable: true })

const emit = defineEmits<{
  'update:modelValue': [v: string | number | null]
  search: [query: string]
}>()

const containerRef = ref<HTMLDivElement>()
const inputRef    = ref<HTMLInputElement>()
const listRef     = ref<HTMLUListElement>()
const open        = ref(false)
const query       = ref('')
const activeIndex = ref(-1)

const selectedLabel = computed(() => {
  if (props.modelValue === null || props.modelValue === undefined || props.modelValue === '') return ''
  return props.options.find(o => o.value === props.modelValue)?.label ?? String(props.modelValue)
})
const displayValue = computed(() => open.value ? query.value : selectedLabel.value)

const filteredOptions = computed(() => {
  if (!query.value || props.onSearch) return props.options
  const q = query.value.toLowerCase()
  return props.options.filter(o =>
    o.label.toLowerCase().includes(q) || (o.sublabel?.toLowerCase().includes(q) ?? false),
  )
})

const grouped = computed(() => {
  const map = new Map<string, ComboboxOption[]>()
  for (const opt of filteredOptions.value) {
    const g = opt.group ?? ''
    if (!map.has(g)) map.set(g, [])
    map.get(g)!.push(opt)
  }
  return map
})

const flatOptions = computed(() => filteredOptions.value.filter(o => !o.disabled))

const dropdownStyle = computed(() => {
  if (!containerRef.value) return {}
  const rect = containerRef.value.getBoundingClientRect()
  return { top: `${rect.bottom + 4}px`, left: `${rect.left}px`, width: `${rect.width}px` }
})

let debounceTimer: ReturnType<typeof setTimeout> | null = null

function handleInput(e: Event) {
  query.value = (e.target as HTMLInputElement).value
  open.value = true
  activeIndex.value = -1
  if (props.onSearch) {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      emit('search', query.value)
      props.onSearch!(query.value)
    }, 300)
  }
}

function openDropdown() {
  if (props.disabled) return
  open.value = true
  query.value = ''
  activeIndex.value = -1
  nextTick(() => inputRef.value?.focus())
}

function selectOption(opt: ComboboxOption) {
  if (opt.disabled) return
  emit('update:modelValue', opt.value)
  open.value = false
  query.value = ''
}

function clearValue() {
  emit('update:modelValue', null)
  query.value = ''
  open.value = false
}

function handleKeydown(e: KeyboardEvent) {
  if (!open.value) {
    if (e.key === 'Enter' || e.key === 'ArrowDown') openDropdown()
    return
  }
  switch (e.key) {
    case 'ArrowDown':
      e.preventDefault()
      activeIndex.value = Math.min(activeIndex.value + 1, flatOptions.value.length - 1)
      nextTick(() => listRef.value?.querySelector<HTMLElement>(`[data-index="${activeIndex.value}"]`)?.scrollIntoView({ block: 'nearest' }))
      break
    case 'ArrowUp':
      e.preventDefault()
      activeIndex.value = Math.max(activeIndex.value - 1, 0)
      nextTick(() => listRef.value?.querySelector<HTMLElement>(`[data-index="${activeIndex.value}"]`)?.scrollIntoView({ block: 'nearest' }))
      break
    case 'Enter':
      e.preventDefault()
      if (activeIndex.value >= 0 && flatOptions.value[activeIndex.value]) selectOption(flatOptions.value[activeIndex.value])
      break
    case 'Escape':
    case 'Tab':
      open.value = false
      query.value = ''
      break
  }
}

function handleClickOutside(e: MouseEvent) {
  if (!containerRef.value?.contains(e.target as Node)) { open.value = false; query.value = '' }
}

onMounted(() => document.addEventListener('mousedown', handleClickOutside))
onBeforeUnmount(() => {
  document.removeEventListener('mousedown', handleClickOutside)
  if (debounceTimer) clearTimeout(debounceTimer)
})
</script>

<template>
  <div ref="containerRef" class="relative w-full" dir="rtl">
    <label v-if="label" :class="[fieldLabelClasses, 'block mb-1']">{{ label }}</label>

    <div class="relative" @click="openDropdown">
      <input
        ref="inputRef"
        type="text"
        :value="displayValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :readonly="!open"
        :class="[fieldClasses({ error: !!error, disabled }), 'pe-10', open ? 'cursor-text' : 'cursor-pointer']"
        autocomplete="off"
        @input="handleInput"
        @keydown="handleKeydown"
        @focus="openDropdown"
      />
      <div class="absolute start-2 inset-y-0 flex items-center">
        <svg v-if="loading" class="animate-spin h-4 w-4 text-muted" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
        </svg>
        <button v-else-if="clearable && modelValue !== null && modelValue !== undefined && modelValue !== ''"
          type="button" class="p-0.5 text-muted hover:text-danger rounded" tabindex="-1" @click.stop="clearValue">
          <AppIcon name="close" size="xs" />
        </button>
        <AppIcon v-else :name="open ? 'chevron-up' : 'chevron-down'" size="sm" class="text-muted" />
      </div>
    </div>

    <p v-if="error" :class="[fieldErrorClasses, 'mt-1']">{{ error }}</p>
    <p v-else-if="hint" :class="[fieldHintClasses, 'mt-1']">{{ hint }}</p>

    <Teleport to="body">
      <div v-if="open" class="fixed z-[100] bg-white dark:bg-surface rounded-xl border border-stone-200 dark:border-border shadow-elevation-3 overflow-hidden" :style="dropdownStyle">
        <div v-if="loading && !filteredOptions.length" class="p-3 space-y-2">
          <Skeleton v-for="i in 3" :key="i" class="h-8" />
        </div>
        <div v-else-if="!filteredOptions.length" class="px-4 py-6 text-center text-sm text-muted">
          لا توجد نتائج{{ query ? ` لـ "${query}"` : '' }}
        </div>
        <ul v-else ref="listRef" role="listbox" class="max-h-64 overflow-y-auto py-1">
          <template v-for="[group, opts] in grouped" :key="group">
            <li v-if="group" class="px-3 py-1.5 text-[10px] font-bold text-muted uppercase tracking-wider bg-stone-50">{{ group }}</li>
            <li v-for="opt in opts" :key="opt.value"
              :data-index="flatOptions.indexOf(opt)"
              role="option"
              :aria-selected="modelValue === opt.value"
              :class="[
                'flex items-start justify-between gap-3 px-3 py-2 text-sm select-none transition-colors',
                opt.disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer hover:bg-primary-50',
                activeIndex === flatOptions.indexOf(opt) ? 'bg-primary-50' : '',
                modelValue === opt.value ? 'bg-primary-50/60 text-primary-700 font-semibold' : 'text-gray-800 dark:text-gray-200',
              ]"
              @mousedown.prevent="selectOption(opt)"
              @mousemove="activeIndex = flatOptions.indexOf(opt)"
            >
              <div class="min-w-0">
                <div class="truncate">{{ opt.label }}</div>
                <div v-if="opt.sublabel" class="text-xs text-muted truncate">{{ opt.sublabel }}</div>
              </div>
              <AppIcon v-if="modelValue === opt.value" name="check" size="xs" class="text-primary-700 mt-0.5 shrink-0" />
            </li>
          </template>
        </ul>
      </div>
    </Teleport>
  </div>
</template>
