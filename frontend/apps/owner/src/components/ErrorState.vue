<script setup lang="ts">
defineProps<{ message?: string }>()
const emit = defineEmits<{ retry: [] }>()
</script>

<template>
  <div class="flex flex-col items-center justify-center py-16 px-6 text-center">
    <div class="text-4xl mb-4" aria-hidden="true">⚠️</div>
    <p class="text-owner-muted text-sm mb-6">
      {{ message || 'تعذّر تحميل البيانات. تحقق من الاتصال.' }}
    </p>
    <button
      class="touch-target bg-owner-card border border-owner-border rounded-xl px-6 text-sm font-semibold text-owner-text active:opacity-70 transition-opacity"
      @click="emit('retry')"
    >
      إعادة المحاولة
    </button>
  </div>
</template>
