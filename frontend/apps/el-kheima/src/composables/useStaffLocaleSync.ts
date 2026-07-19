/**
 * useStaffLocaleSync — keeps the staff UI language reconciled to the signed-in
 * user's server-stored `preferred_language` (Gate 3A / Decision 0002 §4,§5).
 *
 * The backend `preferred_language` is the source of truth once authenticated.
 * This watcher applies it whenever the authenticated user changes:
 *   - login          → apply the user's saved language
 *   - token refresh  → same, on every reload
 *   - PIN switch      → the *new* operator's language, never the previous
 *                       employee's (shared-terminal safety)
 *
 * On logout the user becomes null; the app reloads via window.location.replace
 * ('/login'), so the pre-login namespaced preference re-applies deterministically
 * on the next boot — no stale authenticated language leaks to the login screen.
 *
 * Mount once, high in the tree (App.vue). It does not persist to the server;
 * saving a *new* choice is the LanguageSwitcher's job.
 */
import { watch } from 'vue'
import { storeToRefs } from 'pinia'
import { useAuthStore } from '@resort-os/core'
import { staffLocale } from '@resort-os/core/i18n/staff'

export function useStaffLocaleSync(): void {
  const auth = useAuthStore()
  const { user } = storeToRefs(auth)

  watch(
    [() => user.value?.id, () => user.value?.preferred_language],
    ([, language]) => {
      if (language) {
        // setLocale normalizes unsupported values to the safe fallback.
        // Keep the terminal's pre-login language separate from the signed-in
        // employee preference. Logout reloads that unchanged local policy.
        void staffLocale.setLocale(language, { persist: false })
      }
    },
    { immediate: true },
  )
}
