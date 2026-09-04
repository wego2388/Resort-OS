import { ref, watch } from 'vue'

/**
 * Owner-app-only readable-text preference (Normal / Large / Extra Large).
 *
 * Mohamed tried the app himself, reads with reading glasses, and said the
 * numbers/text are too small (2026-08-17). Rather than hand-tuning ~200
 * individual Tailwind text-size utility classes across every screen (risky,
 * mechanical, easy to miss one), this scales the document's root font-size —
 * every rem-based Tailwind text utility and the .metric-value clamp() in
 * main.css are relative to it, so one setting fixes readability everywhere
 * at once, proportionally, with zero per-class changes.
 *
 * Deliberately owner-app-local (not promoted to @resort-os/core): this is a
 * response to this specific app's specific accessibility request, not an
 * established cross-app concept yet. Mirrors the shape of
 * @resort-os/core's useTheme.ts (module-level singleton ref, localStorage
 * persistence, an init*() to call once before mount) without depending on it.
 */

export type TextScale = 'normal' | 'large' | 'xlarge'

const STORAGE_KEY = 'owner-text-scale'
const SCALE_ORDER: readonly TextScale[] = ['normal', 'large', 'xlarge']
const ROOT_PX: Record<TextScale, number> = { normal: 17, large: 19, xlarge: 21 }
const SCALE_LABEL_AR: Record<TextScale, string> = { normal: 'عادي', large: 'كبير', xlarge: 'أكبر' }

function readStoredScale(): TextScale {
  if (typeof localStorage === 'undefined') return 'normal'
  const stored = localStorage.getItem(STORAGE_KEY)
  return stored === 'large' || stored === 'xlarge' ? stored : 'normal'
}

// Module-level singleton — same reasoning as useTheme.ts: text scale is a
// single global concept for this app, not per-component state.
const scale = ref<TextScale>(readStoredScale())
let initialized = false

function applyToDocument(next: TextScale) {
  if (typeof document === 'undefined') return
  document.documentElement.style.fontSize = `${ROOT_PX[next]}px`
}

/** Call once, as early as possible from main.ts — before app.mount() — so
 * there's no flash of the un-scaled size on first paint. Idempotent. */
export function initTextScale(): void {
  if (initialized) return
  initialized = true
  applyToDocument(scale.value)
  watch(scale, applyToDocument)
}

export function useTextScale() {
  function setScale(next: TextScale) {
    scale.value = next
    if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY, next)
  }

  function cycleScale() {
    const i = SCALE_ORDER.indexOf(scale.value)
    setScale(SCALE_ORDER[(i + 1) % SCALE_ORDER.length])
  }

  return { scale, setScale, cycleScale, label: () => SCALE_LABEL_AR[scale.value] }
}
