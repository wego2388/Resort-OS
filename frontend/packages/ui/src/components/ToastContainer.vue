<script setup lang="ts">
import { useToast } from '../composables/useToast'
const { toasts, remove } = useToast()
</script>
<template>
  <Teleport to="body">
    <div class="fixed top-4 left-1/2 -translate-x-1/2 z-[100] flex flex-col gap-2 w-full max-w-sm px-4">
      <TransitionGroup name="toast">
        <div
          v-for="t in toasts"
          :key="t.id"
          :class="[
            'flex items-start gap-3 px-4 py-3 rounded-xl shadow-lg text-sm font-medium cursor-pointer',
            t.type === 'success' ? 'bg-green-600 text-white' : '',
            t.type === 'error'   ? 'bg-red-600 text-white'   : '',
            t.type === 'warning' ? 'bg-amber-500 text-white' : '',
            t.type === 'info'    ? 'bg-blue-600 text-white'  : '',
          ]"
          @click="remove(t.id)"
        >{{ t.message }}</div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>
<style scoped>
.toast-enter-active, .toast-leave-active { transition: all 0.3s ease; }
.toast-enter-from { opacity: 0; transform: translateY(-20px); }
.toast-leave-to   { opacity: 0; transform: translateY(-20px); }
</style>
