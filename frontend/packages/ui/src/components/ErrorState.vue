<script setup lang="ts">
// The failed-to-load counterpart to EmptyState.vue (which is for "loaded
// fine, there's just nothing here"). Every screen that fetches data and
// swallows the failure into a silent blank area — the exact class of bug
// CLAUDE.md's UI/UX quality pass (2026-07-04) already fixed once across 25
// screens with ad-hoc toast.error() calls — gets a real retry affordance
// instead when it's migrated onto this component.
import AppIcon from './Icon.vue'
import AppButton from './Button.vue'

withDefaults(defineProps<{
  title?: string
  message?: string
  retryLabel?: string
  /** Set to false for errors nothing can retry (e.g. a permission denial) — defaults to true since most load failures are transient. */
  retryable?: boolean
}>(), {
  title: 'حدث خطأ',
  message: 'تعذّر تحميل البيانات. تحقق من الاتصال وحاول مرة أخرى.',
  retryLabel: 'إعادة المحاولة',
  retryable: true,
})

defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="text-center py-12 px-4">
    <div class="w-12 h-12 mx-auto rounded-full bg-danger/10 text-danger flex items-center justify-center mb-3">
      <AppIcon name="warning" size="lg" />
    </div>
    <p class="text-base font-semibold text-gray-800">{{ title }}</p>
    <p class="text-sm text-muted mt-1 max-w-sm mx-auto">{{ message }}</p>
    <AppButton v-if="retryable" variant="outline" size="sm" class="mt-4" @click="$emit('retry')">
      <AppIcon name="refresh" size="sm" />
      {{ retryLabel }}
    </AppButton>
  </div>
</template>
