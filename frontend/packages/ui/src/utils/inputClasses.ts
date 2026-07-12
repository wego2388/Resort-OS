/**
 * Shared visual treatment for every text-entry Design System control (Input,
 * Textarea, Select, MoneyInput, PhoneInput, DatePicker, TimePicker, ...) —
 * extracted so those 7+ components render byte-identical borders/padding/
 * focus states instead of seven hand-copied Tailwind strings drifting apart
 * over time (exactly the "duplicate CSS" wagdy.md's Design System asks to
 * eliminate). Input.vue itself is refactored to call this too, so there is
 * exactly one place that defines what a form field looks like.
 */
export function fieldClasses(opts: { error?: boolean; disabled?: boolean; withStartSlot?: boolean; withEndSlot?: boolean } = {}) {
  return [
    // Same literal values Input.vue has always used (border-stone-200,
    // red-400/50, gray-50) — kept byte-identical rather than swapped for the
    // newer `border`/`danger`/`background` DS tokens, since Input.vue is
    // already wired into ~20 shipped screens and this file is what defines
    // its render output; `focus:ring-primary-500` is the one intentional
    // rename (primary.500 === Tailwind's blue-500 hex exactly, in both
    // apps' tailwind.config.js — so this is a zero-visual-diff correction
    // from an accidental generic-blue reference to the real brand token).
    'w-full rounded-lg border bg-white dark:bg-surface text-gray-900 dark:text-gray-100 placeholder-gray-400 transition-colors',
    'focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500',
    opts.withStartSlot ? 'ps-9 pe-3 py-2' : opts.withEndSlot ? 'ps-3 pe-9 py-2' : 'px-3 py-2',
    opts.error ? 'border-red-400 bg-red-50' : 'border-stone-200',
    opts.disabled ? 'opacity-50 cursor-not-allowed bg-gray-50' : '',
  ]
}

export const fieldLabelClasses = 'text-sm font-medium text-gray-700 dark:text-gray-300'
export const fieldErrorClasses = 'text-xs text-danger'
export const fieldHintClasses = 'text-xs text-muted'
