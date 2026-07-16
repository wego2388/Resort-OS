<script setup lang="ts">
// A controlled tab strip — the parent owns which tab is active (v-model),
// this component only renders the strip and emits selection. Content panels
// are the caller's own template with `v-show`/`v-if="active === 'x'"`, kept
// deliberately outside this component rather than a <template #tab-x> slot
// API, since every current multi-tab screen (FinanceView, HRView, ...)
// already structures its panels that way and a slot-based rewrite would be
// a real behavior change, not just a presentation one.
import { computed } from 'vue'

export interface TabItem {
  value: string
  label: string
  count?: number
  disabled?: boolean
}

const props = defineProps<{ tabs: TabItem[]; modelValue: string }>()
const emit = defineEmits<{ 'update:modelValue': [v: string] }>()

const activeIndex = computed(() => props.tabs.findIndex(t => t.value === props.modelValue))

function onKeydown(e: KeyboardEvent) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return
  e.preventDefault()
  const enabled = props.tabs.map((t, i) => ({ t, i })).filter(x => !x.t.disabled)
  if (enabled.length === 0) return
  const currentPos = enabled.findIndex(x => x.i === activeIndex.value)
  let nextPos = currentPos
  if (e.key === 'Home') nextPos = 0
  else if (e.key === 'End') nextPos = enabled.length - 1
  // RTL-agnostic: ArrowRight always moves toward the end of the tab list in
  // document order, matching how [dir] already flips the *visual* order of
  // the flex row — no separate RTL branch needed here.
  else if (e.key === 'ArrowRight') nextPos = (currentPos + 1) % enabled.length
  else if (e.key === 'ArrowLeft') nextPos = (currentPos - 1 + enabled.length) % enabled.length
  emit('update:modelValue', enabled[nextPos]!.t.value)
}
</script>

<template>
  <div role="tablist" class="flex items-center gap-1 border-b border-stone-200 dark:border-border overflow-x-auto" @keydown="onKeydown">
    <button
      v-for="tab in tabs"
      :key="tab.value"
      role="tab"
      type="button"
      :aria-selected="tab.value === modelValue"
      :disabled="tab.disabled"
      :tabindex="tab.value === modelValue ? 0 : -1"
      @click="!tab.disabled && emit('update:modelValue', tab.value)"
      :class="[
        'relative px-4 py-2.5 text-sm font-medium whitespace-nowrap transition-colors duration-base focus:outline-none focus-visible:shadow-focus-ring rounded-t-lg',
        tab.value === modelValue ? 'text-primary-700' : 'text-muted hover:text-gray-700 dark:hover:text-gray-300',
        tab.disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer',
      ]"
    >
      {{ tab.label }}
      <span v-if="tab.count !== undefined" class="ms-1.5 text-xs text-muted">({{ tab.count }})</span>
      <span
        v-if="tab.value === modelValue"
        class="absolute inset-x-2 -bottom-px h-0.5 bg-primary-700 rounded-full"
      />
    </button>
  </div>
</template>
