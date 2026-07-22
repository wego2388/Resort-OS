import { ref, watch } from 'vue'

type ThemePreference = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'resort-os-theme'

// Module-level singleton (same pattern as useToast/useConfirm in
// @resort-os/ui) — theme is a single global concept, not per-component
// state, so every `useTheme()` caller across both apps shares one source of
// truth instead of racing separate refs.
const preference = ref<ThemePreference>(readStoredPreference())
const isDark = ref(false)

let media: MediaQueryList | null = null
let initialized = false

function readStoredPreference(): ThemePreference {
  if (typeof localStorage === 'undefined') return 'system'
  const stored = localStorage.getItem(STORAGE_KEY)
  return stored === 'light' || stored === 'dark' ? stored : 'system'
}

function systemPrefersDark(): boolean {
  return typeof matchMedia !== 'undefined' && matchMedia('(prefers-color-scheme: dark)').matches
}

function applyToDocument(dark: boolean) {
  isDark.value = dark
  if (typeof document === 'undefined') return
  document.documentElement.classList.toggle('dark', dark)
}

function resolve(pref: ThemePreference): boolean {
  return pref === 'system' ? systemPrefersDark() : pref === 'dark'
}

/**
 * Bootstraps the Design System's dark mode: applies the `.dark` class Tailwind
 * (darkMode: 'class', see tailwind-preset.js) expects, from either the
 * user's saved preference (localStorage) or the OS-level `prefers-color-scheme`
 * when no preference has been saved yet. Call this once, as early as possible,
 * from each app's main.ts — before `app.mount()` — so there's no flash of the
 * wrong theme on first paint.
 *
 * Idempotent: safe to import/call from multiple entry points without
 * double-registering the matchMedia listener.
 */
export function initTheme(): void {
  if (initialized) return
  initialized = true

  applyToDocument(resolve(preference.value))

  if (typeof matchMedia !== 'undefined') {
    media = matchMedia('(prefers-color-scheme: dark)')
    media.addEventListener('change', (e) => {
      if (preference.value === 'system') applyToDocument(e.matches)
    })
  }

  watch(preference, (pref) => applyToDocument(resolve(pref)))
}

/**
 * Reactive access to the current theme + a setter that persists the choice.
 * Any component (including the shared `<ThemeToggle />`) can call this without
 * caring whether `initTheme()` already ran elsewhere — reading `isDark`/
 * `preference` before the app boots simply reflects the not-yet-applied
 * resolved value (documentElement update happens once initTheme() runs).
 */
export function useTheme() {
  function setTheme(next: ThemePreference) {
    preference.value = next
    if (typeof localStorage !== 'undefined') {
      if (next === 'system') localStorage.removeItem(STORAGE_KEY)
      else localStorage.setItem(STORAGE_KEY, next)
    }
    applyToDocument(resolve(next))
  }

  function toggleTheme() {
    setTheme(isDark.value ? 'light' : 'dark')
  }

  return { preference, isDark, setTheme, toggleTheme }
}
