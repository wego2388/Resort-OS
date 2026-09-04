<script setup lang="ts">
/**
 * DetailSheet — نافذة تفاصيل موحّدة (bottom sheet) تُستخدم في كل شاشات
 * الأونر. تدوس على أي سطر إجمالي (صنف/فئة مصروف/مورد...) → تفتح النافذة
 * دي بالسجلات الخام اللي كوّنت الرقم، بدل شاشة منفصلة لكل حالة.
 *
 * الاستخدام: <DetailSheet :open :title :subtitle :loading :error @close
 * @retry> ... default slot لصفوف المحتوى، اللي بيختلف شكله حسب النوع ... </DetailSheet>
 */
import { watch } from 'vue'

const props = defineProps<{
  open: boolean
  title: string
  subtitle?: string
  loading?: boolean
  error?: string | null
}>()

const emit = defineEmits<{ close: []; retry: [] }>()

// يمنع scroll الصفحة اللي تحت وقت فتح النافذة
watch(() => props.open, (isOpen) => {
  document.body.style.overflow = isOpen ? 'hidden' : ''
})
</script>

<template>
  <Teleport to="body">
    <Transition name="sheet-fade">
      <div
        v-if="open"
        class="fixed inset-0 z-50 bg-black/60"
        @click.self="emit('close')"
      >
        <Transition name="sheet-slide" appear>
          <div
            class="absolute inset-x-0 bottom-0 max-h-[85vh] flex flex-col bg-owner-bg rounded-t-2xl border-t border-owner-border shadow-2xl lg:mx-auto lg:max-w-2xl lg:bottom-8 lg:rounded-2xl lg:border"
            style="padding-bottom: env(safe-area-inset-bottom);"
            role="dialog"
            aria-modal="true"
            :aria-label="title"
          >
            <!-- مقبض السحب -->
            <div class="flex justify-center pt-2 pb-1 shrink-0">
              <div class="w-10 h-1 rounded-full bg-owner-border" />
            </div>

            <!-- Header -->
            <div class="flex items-start justify-between gap-3 px-4 pb-3 border-b border-owner-border shrink-0">
              <div class="min-w-0">
                <h2 class="text-sm font-bold text-owner-text truncate">{{ title }}</h2>
                <p v-if="subtitle" class="text-xs text-owner-muted mt-0.5">{{ subtitle }}</p>
              </div>
              <button
                class="touch-target shrink-0 text-owner-muted active:text-owner-text transition-colors"
                aria-label="إغلاق"
                @click="emit('close')"
              >
                <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                  <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            <!-- Body -->
            <div class="flex-1 overflow-y-auto overscroll-contain px-4 py-3">
              <div v-if="loading" class="space-y-2 py-4">
                <div v-for="i in 5" :key="i" class="skeleton h-14 rounded-xl" />
              </div>

              <div v-else-if="error" class="flex flex-col items-center justify-center py-12 text-center">
                <div class="text-3xl mb-3" aria-hidden="true">⚠️</div>
                <p class="text-owner-muted text-xs mb-4">{{ error }}</p>
                <button
                  class="touch-target bg-owner-card border border-owner-border rounded-xl px-5 text-xs font-semibold text-owner-text active:opacity-70"
                  @click="emit('retry')"
                >
                  إعادة المحاولة
                </button>
              </div>

              <slot v-else />
            </div>
          </div>
        </Transition>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.sheet-fade-enter-active, .sheet-fade-leave-active { transition: opacity 0.2s ease; }
.sheet-fade-enter-from, .sheet-fade-leave-to { opacity: 0; }

.sheet-slide-enter-active { transition: transform 0.25s cubic-bezier(0.16, 1, 0.3, 1); }
.sheet-slide-leave-active { transition: transform 0.2s ease-in; }
.sheet-slide-enter-from, .sheet-slide-leave-to { transform: translateY(100%); }

@media (prefers-reduced-motion: reduce) {
  .sheet-fade-enter-active, .sheet-fade-leave-active,
  .sheet-slide-enter-active, .sheet-slide-leave-active { transition: none; }
}
</style>
