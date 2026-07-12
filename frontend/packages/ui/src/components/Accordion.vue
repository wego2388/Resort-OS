<script setup lang="ts">
// A single collapsible section — compose multiple <AppAccordion> instances
// for a full accordion group (each manages its own open state independently
// unless the caller lifts it via v-model, matching how e.g. FAQ-style or
// per-record detail panels are actually used across this codebase; a
// forced single-open-at-a-time group would be a real behavior decision
// better made by the specific screen, not imposed by the primitive).
import { ref, computed } from 'vue'
import AppIcon from './Icon.vue'

const props = defineProps<{ title: string; modelValue?: boolean; defaultOpen?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [v: boolean] }>()

const internalOpen = ref(props.defaultOpen ?? false)
// Supports both uncontrolled (defaultOpen + internal state) and controlled
// (v-model) usage — same dual-mode pattern Vue itself recommends for
// components that are sometimes standalone, sometimes orchestrated by a parent.
const isOpen = computed({
  get: () => props.modelValue ?? internalOpen.value,
  set: (v) => { internalOpen.value = v; emit('update:modelValue', v) },
})
</script>

<template>
  <div class="border border-stone-200 rounded-xl overflow-hidden">
    <button
      type="button"
      class="w-full flex items-center justify-between gap-3 px-4 py-3 text-start font-medium text-gray-800 hover:bg-background transition-colors duration-base focus:outline-none focus-visible:shadow-focus-ring"
      :aria-expanded="isOpen"
      @click="isOpen = !isOpen"
    >
      <span>{{ title }}</span>
      <AppIcon name="chevron-down" size="sm" :class="['transition-transform duration-base text-muted', isOpen && 'rotate-180']" />
    </button>
    <Transition
      enter-active-class="transition-all duration-base ease-ds-decelerate"
      leave-active-class="transition-all duration-fast ease-ds-accelerate"
      enter-from-class="grid-rows-[0fr] opacity-0"
      enter-to-class="grid-rows-[1fr] opacity-100"
      leave-from-class="grid-rows-[1fr] opacity-100"
      leave-to-class="grid-rows-[0fr] opacity-0"
    >
      <div v-if="isOpen" class="grid grid-rows-[1fr] px-4 pb-4 pt-1 text-sm text-gray-700">
        <div class="overflow-hidden">
          <slot />
        </div>
      </div>
    </Transition>
  </div>
</template>
