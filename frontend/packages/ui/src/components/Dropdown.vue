<script setup lang="ts">
// A generic trigger + popover menu — the foundation Select/Combobox-style
// components could build on, and directly usable today for row action menus
// ("⋮" → edit/delete/void) and small filter popovers.
//
// Deliberately positioned relative to its own trigger (absolute, inside a
// `position: relative` wrapper) rather than Teleported + computed via
// getBoundingClientRect: covers the overwhelming majority of real usage
// (a menu attached to a button inside a normal-flow container) correctly
// and simply. The one real limitation — it can clip if the trigger sits
// inside a container with `overflow: hidden` right at the viewport edge —
// is a known, documented trade-off, not a silent bug; reach for a
// Teleport-based positioning solution only if a screen actually hits that
// case (none does yet, since no screen uses this component).
import { ref, watch, nextTick } from 'vue'
import { onClickOutside } from '../composables/onClickOutside'

const props = withDefaults(defineProps<{
  align?: 'start' | 'end'
  disabled?: boolean
}>(), { align: 'end' })

const open = ref(false)
const rootEl = ref<HTMLElement | null>(null)

function toggle() { if (!props.disabled) open.value = !open.value }
function close() { open.value = false }

onClickOutside(rootEl, close)

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && open.value) { close(); (rootEl.value?.querySelector('[data-dropdown-trigger]') as HTMLElement | null)?.focus() }
}

watch(open, async (v) => {
  if (v) { await nextTick(); rootEl.value?.querySelector<HTMLElement>('[role="menuitem"]')?.focus() }
})
</script>

<template>
  <div ref="rootEl" class="relative inline-block" @keydown="onKeydown">
    <span data-dropdown-trigger @click="toggle">
      <slot name="trigger" :open="open" :toggle="toggle" />
    </span>
    <Transition
      enter-active-class="transition duration-fast ease-ds-decelerate"
      leave-active-class="transition duration-fast ease-ds-accelerate"
      enter-from-class="opacity-0 scale-95"
      leave-to-class="opacity-0 scale-95"
    >
      <div
        v-if="open"
        role="menu"
        :class="[
          'absolute top-full mt-1 min-w-[12rem] rounded-xl border border-stone-200 bg-white shadow-elevation-3 py-1 z-30',
          align === 'end' ? 'end-0' : 'start-0',
        ]"
        @click="close"
      >
        <slot :close="close" />
      </div>
    </Transition>
  </div>
</template>
