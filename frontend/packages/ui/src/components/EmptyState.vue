<script setup lang="ts">
// `icon` stays a free-form string (emoji, exactly as ~20 already-shipped
// screens call it today — grep confirms usages like icon="🧾"/"💵"/"⭐")
// so this refactor changes no existing screen's rendering. The new `action`
// slot is purely additive (renders nothing when unused) — it's what makes
// this usable as the real "every empty state should help the user" pattern
// wagdy.md's Phase 11 asks for (e.g. an EmptyState with a "+ إنشاء" button),
// without forcing that on the ~20 call sites that don't pass it.
defineProps<{ icon?: string; title: string; subtitle?: string }>()
</script>
<template>
  <div class="px-4 py-12 text-center text-gray-400 dark:text-gray-400">
    <div class="text-4xl mb-3">{{ icon ?? '📭' }}</div>
    <p class="text-base font-medium text-gray-500 dark:text-gray-400">{{ title }}</p>
    <p v-if="subtitle" class="mt-1 text-sm text-gray-400 dark:text-gray-400">{{ subtitle }}</p>
    <div v-if="$slots.action" class="mt-4">
      <slot name="action" />
    </div>
  </div>
</template>
