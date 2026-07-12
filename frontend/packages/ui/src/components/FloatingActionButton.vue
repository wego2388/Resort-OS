<script setup lang="ts">
// A fixed-position primary action button — the "new order"/"new booking"
// affordance for touch-first POS/waiter screens where reaching a toolbar
// button at the top of a long list costs an extra scroll. 56px hit target
// (comfortably over the 48px minimum wagdy.md's Touch UX phase requires).
import AppIcon from './Icon.vue'
import type { IconName } from '../icons/registry'

withDefaults(defineProps<{
  icon: IconName
  label: string
  position?: 'bottom-end' | 'bottom-center'
}>(), { position: 'bottom-end' })

defineEmits<{ click: [] }>()
</script>

<template>
  <button
    type="button"
    :aria-label="label"
    :title="label"
    @click="$emit('click')"
    :class="[
      'fixed z-40 w-14 h-14 rounded-full bg-primary-700 text-white shadow-elevation-4 flex items-center justify-center hover:bg-primary-800 active:scale-95 transition-all duration-base focus:outline-none focus-visible:shadow-focus-ring',
      position === 'bottom-end' ? 'bottom-6 end-6' : 'bottom-6 start-1/2 -translate-x-1/2 rtl:translate-x-1/2',
    ]"
  >
    <AppIcon :name="icon" size="lg" />
  </button>
</template>
