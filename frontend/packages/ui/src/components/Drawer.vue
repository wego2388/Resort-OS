<script setup lang="ts">
// Slide-in side panel — same Teleport/backdrop/z-index pattern as Modal.vue
// (including the same z-index escape hatch, for the identical reason: a
// useConfirm() opened from inside an open Drawer needs to render above it).
// Use for detail/edit panels that benefit from keeping the underlying list
// visible at the edge (order details, guest profile) — Modal.vue remains
// the default for anything that should fully focus the user's attention.
//
// `side` is logical (start/end, not left/right) because both apps run
// RTL-by-default with a live per-session dir switch (packages/core's i18n
// switchLocale() flips <html dir> at runtime — see apps/*/src/assets/
// main.css's comment on why direction is never hardcoded). The slide
// transform direction below is resolved from the *live* `dir` attribute via
// :global([dir="rtl"]) overrides, not assumed — so this animates correctly
// in both Arabic (RTL) and en/it (LTR) sessions.
import AppIcon from './Icon.vue'

withDefaults(defineProps<{
  open: boolean
  title?: string
  side?: 'start' | 'end'
  width?: 'sm' | 'md' | 'lg'
  zIndex?: string
}>(), { side: 'end', width: 'md', zIndex: 'z-50' })

const emit = defineEmits<{ close: [] }>()
</script>

<template>
  <Teleport to="body">
    <Transition name="drawer-backdrop">
      <div v-if="open" :class="['fixed inset-0', zIndex]">
        <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" @click="emit('close')" />
        <Transition :name="side === 'end' ? 'drawer-end' : 'drawer-start'">
          <div
            v-if="open"
            :class="[
              'absolute top-0 bottom-0 bg-white shadow-elevation-5 flex flex-col w-full',
              side === 'end' ? 'end-0' : 'start-0',
              width === 'sm' ? 'max-w-sm' : width === 'lg' ? 'max-w-2xl' : 'max-w-md',
            ]"
            role="dialog"
            aria-modal="true"
          >
            <div v-if="title || $slots.header" class="flex items-center justify-between px-6 py-4 border-b border-stone-100 flex-shrink-0">
              <slot name="header"><h2 class="text-lg font-bold text-gray-900">{{ title }}</h2></slot>
              <button @click="emit('close')" class="p-1 rounded-lg hover:bg-gray-100 transition-colors duration-base" aria-label="إغلاق">
                <AppIcon name="close" class="text-gray-500" />
              </button>
            </div>
            <div class="overflow-y-auto flex-1 p-6">
              <slot />
            </div>
            <div v-if="$slots.footer" class="px-6 py-4 border-t border-stone-100 flex-shrink-0">
              <slot name="footer" />
            </div>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.drawer-backdrop-enter-active, .drawer-backdrop-leave-active { transition: opacity 0.2s ease; }
.drawer-backdrop-enter-from, .drawer-backdrop-leave-to { opacity: 0; }
.drawer-end-enter-active, .drawer-end-leave-active,
.drawer-start-enter-active, .drawer-start-leave-active { transition: transform 0.25s cubic-bezier(0.4,0,0.2,1); }

/* LTR default: "end" = right edge, "start" = left edge. */
.drawer-end-enter-from, .drawer-end-leave-to { transform: translateX(100%); }
.drawer-start-enter-from, .drawer-start-leave-to { transform: translateX(-100%); }

/* RTL (this project's default locale): "end" = left edge, "start" = right
   edge — mirror the slide direction so the panel always enters from off the
   edge it's actually anchored to, not off the opposite one. */
:global([dir="rtl"]) .drawer-end-enter-from,
:global([dir="rtl"]) .drawer-end-leave-to { transform: translateX(-100%); }
:global([dir="rtl"]) .drawer-start-enter-from,
:global([dir="rtl"]) .drawer-start-leave-to { transform: translateX(100%); }
</style>
