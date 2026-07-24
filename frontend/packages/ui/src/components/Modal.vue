<script setup lang="ts">
// Gate 3B — accessible dialog baseline. Additive only: no prop removed, no
// visual change. Adds dialog semantics (role/aria-modal/accessible name),
// Escape-to-close, focus-on-open, focus-return-on-close, and a Tab focus trap
// so keyboard users cannot tab out of an open modal. All existing call sites
// keep working unchanged (they already handle the `close` emit).
import { ref, watch, nextTick, computed, onMounted, onBeforeUnmount } from 'vue'

const props = withDefaults(defineProps<{
  open: boolean
  title?: string
  size?: 'sm' | 'md' | 'lg' | 'xl'
  /** Accessible name when there is no visible title (falls back to this). */
  ariaLabel?: string
  /** Accessible name for the icon-only close button. */
  closeLabel?: string
  /**
   * Associates the dialog with a description element via aria-describedby.
   * Pass the `id` of the element that describes the dialog's purpose
   * (e.g. a message paragraph). Screen readers will announce it automatically.
   */
  ariaDescribedby?: string
  // ⚠️ باج حقيقي اتكشف حي (2026-07-06، اختبار زر "📨 استبيان الرضا" في
  // TimeshareView كمدير): useConfirm() بيفتح AppModal تاني فوق أي AppModal
  // شاشة مفتوحة أصلاً (نفس المكوّن، الاتنين Teleport لـ body بنفس z-50).
  // ترتيب عناصر body بيتحدد بترتيب أول mount لكل Teleport instance، مش
  // بترتيب ظهور المحتوى — وConfirmDialogContainer بيتحمّل مرة واحدة بدري
  // جدًا في App.vue، يعني أي مودال شاشة بيتفتح بعده (زي بروفايل عميل
  // التايم شير) بيطلع فوقه فعليًا في الـ DOM رغم تساوي z-index. النتيجة:
  // زر تأكيد حقيقي ("نعم، أرسل") كان مقفول خلف مودال الشاشة، غير قابل
  // للضغط عليه خالص — أي useConfirm() جوه أي مودال مفتوح في المشروع كله
  // كان معطّل عمليًا. الحل: z-index قابل للتحديد، ConfirmDialogContainer
  // بيطلب طبقة أعلى صراحة عشان يفضل دايمًا فوق أي مودال محتوى.
  zIndex?: string
}>(), {
  zIndex: 'z-50',
  ariaLabel: 'Dialog / نافذة',
  closeLabel: 'Close / إغلاق',
})
const emit = defineEmits<{ close: [] }>()

const panelEl = ref<HTMLElement | null>(null)
let previouslyFocused: HTMLElement | null = null

const titleId = `modal-title-${Math.random().toString(36).slice(2, 9)}`
const labelledBy = computed(() => (props.title ? titleId : undefined))

function focusables(): HTMLElement[] {
  if (!panelEl.value) return []
  return Array.from(
    panelEl.value.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ),
  ).filter((el) => {
    if (el.closest('[hidden], [aria-hidden="true"]')) return false
    const style = window.getComputedStyle(el)
    return style.display !== 'none' && style.visibility !== 'hidden'
  })
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.stopPropagation()
    emit('close')
    return
  }
  if (e.key !== 'Tab') return
  const items = focusables()
  if (items.length === 0) {
    e.preventDefault()
    panelEl.value?.focus()
    return
  }
  const first = items[0]
  const last = items[items.length - 1]
  const active = document.activeElement as HTMLElement | null
  if (e.shiftKey && (active === first || !panelEl.value?.contains(active))) {
    e.preventDefault()
    last.focus()
  } else if (!e.shiftKey && active === last) {
    e.preventDefault()
    first.focus()
  }
}

function restorePreviousFocus() {
  if (previouslyFocused && typeof previouslyFocused.focus === 'function') {
    previouslyFocused.focus()
  }
  previouslyFocused = null
}

function activateDialogFocus() {
  previouslyFocused = document.activeElement as HTMLElement | null
  nextTick(() => {
    const items = focusables()
    ;(items[0] ?? panelEl.value)?.focus()
  })
}

watch(
  () => props.open,
  (isOpen) => {
    if (isOpen) {
      activateDialogFocus()
    } else {
      // Return focus to whatever opened the modal.
      restorePreviousFocus()
    }
  },
)

// Several real call sites mount AppModal conditionally with `open=true`
// (StepUp, PinGuard, operator switch). A normal prop watcher sees no change on
// that path, so initialize focus explicitly after the Teleport has mounted.
onMounted(() => {
  if (props.open) activateDialogFocus()
})

// A conditional parent may remove the whole component in response to `close`
// without first changing its `open` prop. Restore focus on that path too.
onBeforeUnmount(restorePreviousFocus)
</script>
<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="open"
        :class="['fixed inset-0 flex items-center justify-center p-4', zIndex]"
        @click.self="emit('close')"
        @keydown="onKeydown"
      >
        <div class="absolute inset-0 bg-black/50 backdrop-blur-sm" @click="emit('close')" />
        <div
          ref="panelEl"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="labelledBy"
          :aria-label="!title ? ariaLabel : undefined"
          :aria-describedby="ariaDescribedby || undefined"
          tabindex="-1"
          :class="[
          'relative bg-white dark:bg-surface rounded-2xl shadow-2xl w-full max-h-[90vh] flex flex-col focus:outline-none',
          size === 'sm' ? 'max-w-sm'  : '',
          size === 'lg' ? 'max-w-2xl' : '',
          size === 'xl' ? 'max-w-4xl' : '',
          (!size || size === 'md') ? 'max-w-lg' : '',
        ]">
          <div v-if="title" class="flex items-center justify-between px-6 py-4 border-b border-stone-100 dark:border-border flex-shrink-0">
            <h2 :id="titleId" class="text-lg font-bold text-gray-900 dark:text-gray-100">{{ title }}</h2>
            <button @click="emit('close')" :aria-label="closeLabel" class="p-1 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors">
              <svg class="w-5 h-5 text-gray-500 dark:text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
              </svg>
            </button>
          </div>
          <div class="overflow-y-auto flex-1 p-6">
            <slot />
          </div>
          <div v-if="$slots.footer" class="px-6 py-4 border-t border-stone-100 dark:border-border flex-shrink-0">
            <slot name="footer" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
<style scoped>
.modal-enter-active, .modal-leave-active { transition: opacity 0.2s ease; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
</style>
