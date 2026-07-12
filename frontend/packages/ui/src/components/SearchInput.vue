<script setup lang="ts">
// The one search box every list/table/DataTable in the app should use —
// leading search icon, trailing clear button once there's text, and an
// optional built-in debounce so screens stop hand-rolling setTimeout logic
// (a genuine business-logic-in-component smell wagdy.md explicitly forbids).
import { ref, watch, onBeforeUnmount } from 'vue'
import AppIcon from './Icon.vue'
import { fieldClasses } from '../utils/inputClasses'

const props = withDefaults(defineProps<{
  modelValue?: string
  placeholder?: string
  disabled?: boolean
  /** ms to wait after the user stops typing before emitting `search` (0 = emit immediately, same as `update:modelValue`). */
  debounceMs?: number
}>(), { placeholder: 'بحث...', debounceMs: 300 })

const emit = defineEmits<{ 'update:modelValue': [v: string]; search: [v: string] }>()

let timer: ReturnType<typeof setTimeout> | undefined

function onInput(e: Event) {
  const value = (e.target as HTMLInputElement).value
  emit('update:modelValue', value)
  if (timer) clearTimeout(timer)
  if (props.debounceMs <= 0) {
    emit('search', value)
  } else {
    timer = setTimeout(() => emit('search', value), props.debounceMs)
  }
}

function clear() {
  emit('update:modelValue', '')
  emit('search', '')
}

onBeforeUnmount(() => { if (timer) clearTimeout(timer) })

const classes = fieldClasses({ withStartSlot: true, withEndSlot: true })
</script>

<template>
  <div class="relative">
    <AppIcon name="search" size="sm" class="absolute start-3 top-1/2 -translate-y-1/2 text-muted pointer-events-none" />
    <input
      type="search"
      :placeholder="placeholder"
      :disabled="disabled"
      :value="modelValue"
      @input="onInput"
      :class="classes"
    />
    <button
      v-if="modelValue"
      type="button"
      class="absolute end-2 top-1/2 -translate-y-1/2 p-1 rounded-full hover:bg-background text-muted"
      aria-label="مسح البحث"
      @click="clear"
    >
      <AppIcon name="close" size="xs" />
    </button>
  </div>
</template>
