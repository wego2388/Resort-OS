import { onMounted, onBeforeUnmount, type Ref } from 'vue'

/**
 * Fires `handler` on any pointerdown outside `target`'s element — the
 * standard "close this dropdown/menu/popover when the user clicks
 * elsewhere" behavior, extracted so Dropdown.vue (and anything similar
 * later — Combobox, CommandPalette) doesn't each reimplement the same
 * document-listener dance with subtly different edge cases.
 */
export function onClickOutside(target: Ref<HTMLElement | null>, handler: () => void) {
  function onPointerDown(e: PointerEvent) {
    const el = target.value
    if (!el || el.contains(e.target as Node)) return
    handler()
  }

  onMounted(() => document.addEventListener('pointerdown', onPointerDown, true))
  onBeforeUnmount(() => document.removeEventListener('pointerdown', onPointerDown, true))
}
