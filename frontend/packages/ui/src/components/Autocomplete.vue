<script setup lang="ts">
/**
 * Autocomplete — text input مع suggestions من API.
 * الفرق عن Combobox: القيمة string حر (مش مقيّد بالـ options)، يسمح بـ free text.
 * الاستخدام الرئيسي: CRM customer search، PMS booking search.
 */
import { ref, computed, nextTick, onMounted, onBeforeUnmount } from 'vue'
import AppIcon from './Icon.vue'
import Skeleton from './Skeleton.vue'
import { fieldClasses, fieldLabelClasses, fieldErrorClasses, fieldHintClasses } from '../utils/inputClasses'

export interface AutocompleteSuggestion {
  label: string
  value: string
  meta?: string
}

const props = withDefaults(defineProps<{
  modelValue: string
  suggestions: AutocompleteSuggestion[]
  placeholder?: string
  label?: string
  hint?: string
  error?: string
  loading?: boolean
  disabled?: boolean
  minChars?: number
  debounce?: number
}>(), {
  placeholder: 'اكتب للبحث...',
  minChars: 2,
  debounce: 300,
})

const emit = defineEmits<{
  'update:modelValue': [v: string]
  select: [suggestion: AutocompleteSuggestion]
  search: [query: string]
}>()

const containerRef = ref<HTMLDivElement>()
const inputRef     = ref<HTMLInputElement>()
const open         = ref(false)
const activeIndex  = ref(-1)

let debounceTimer: ReturnType<typeof setTimeout> | null = null

function handleInput(e: Event) {
  const val = (e.target as HTMLInputElement).value
  emit('update:modelValue', val)
  activeIndex.value = -1

  if (val.length >= props.minChars) {
    open.value = true
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => emit('search', val), props.debounce)
  } else {
    open.value = false
  }
}

function selectSuggestion(s: AutocompleteSuggestion) {
  emit('update:modelValue', s.label)
  emit('select', s)
  open.value = false
}

function handleKeydown(e: KeyboardEvent) {
  if (!open.value || !props.suggestions.length) return
  switch (e.key) {
    case 'ArrowDown':
      e.preventDefault()
      activeIndex.value = Math.min(activeIndex.value + 1, props.suggestions.length - 1)
      break
    case 'ArrowUp':
      e.preventDefault()
      activeIndex.value = Math.max(activeIndex.value - 1, 0)
      break
    case 'Enter':
      e.preventDefault()
      if (activeIndex.value >= 0 && props.suggestions[activeIndex.value]) {
        selectSuggestion(props.suggestions[activeIndex.value])
      }
      break
    case 'Escape':
      open.value = false
      break
  }
}

const dropdownStyle = computed(() => {
  if (!containerRef.value) return {}
  const rect = containerRef.value.getBoundingClientRect()
  return { top: `${rect.bottom + 4}px`, left: `${rect.left}px`, width: `${rect.width}px` }
})

function handleClickOutside(e: MouseEvent) {
  if (!containerRef.value?.contains(e.target as Node)) open.value = false
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

    <div class="relative">
      <div class="absolute end-2 inset-y-0 flex items-center pointer-events-none">
        <svg v-if="loading" class="animate-spin h-4 w-4 text-muted" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
        </svg>
        <AppIcon v-else name="search" size="sm" class="text-muted" />
      </div>
      <input
        ref="inputRef"
        type="text"
        :value="modelValue"
        :placeholder="placeholder"
        :disabled="disabled"
        :class="[fieldClasses({ error: !!error, disabled }), 'pe-9']"
        autocomplete="off"
        @input="handleInput"
        @keydown="handleKeydown"
      />
    </div>

    <p v-if="error" :class="[fieldErrorClasses, 'mt-1']">{{ error }}</p>
    <p v-else-if="hint" :class="[fieldHintClasses, 'mt-1']">{{ hint }}</p>

    <Teleport to="body">
      <div v-if="open" class="fixed z-[100] bg-white dark:bg-surface rounded-xl border border-stone-200 dark:border-border shadow-elevation-3 overflow-hidden" :style="dropdownStyle">
        <div v-if="loading && !suggestions.length" class="p-3 space-y-2">
          <Skeleton v-for="i in 3" :key="i" class="h-8" />
        </div>
        <div v-else-if="!suggestions.length" class="px-4 py-5 text-center text-sm text-muted">لا توجد نتائج</div>
        <ul v-else role="listbox" class="max-h-60 overflow-y-auto py-1">
          <li v-for="(s, i) in suggestions" :key="s.value"
            role="option"
            :class="[
              'flex items-center justify-between gap-3 px-3 py-2.5 text-sm cursor-pointer select-none transition-colors',
              activeIndex === i ? 'bg-primary-50 text-primary-700' : 'text-gray-800 dark:text-gray-200 hover:bg-stone-50 dark:hover:bg-gray-700/50',
            ]"
            @mousedown.prevent="selectSuggestion(s)"
            @mousemove="activeIndex = i"
          >
            <span class="font-medium truncate">{{ s.label }}</span>
            <span v-if="s.meta" class="text-xs text-muted shrink-0">{{ s.meta }}</span>
          </li>
        </ul>
      </div>
    </Teleport>
  </div>
</template>
