<script setup lang="ts">
// Mounted once globally in App.vue — see composables/useConfirm.ts.
import AppModal from './Modal.vue'
import AppButton from './Button.vue'
import { useConfirm } from '../composables/useConfirm'

const { isOpen, options, handleConfirm, handleCancel } = useConfirm()
</script>

<template>
  <AppModal :open="isOpen" :title="options.title ?? 'تأكيد'" size="sm" @close="handleCancel">
    <p class="text-gray-700 text-sm leading-relaxed">{{ options.message }}</p>
    <template #footer>
      <div class="flex items-center justify-end gap-2">
        <AppButton variant="ghost" size="sm" @click="handleCancel">
          {{ options.cancelText ?? 'إلغاء' }}
        </AppButton>
        <AppButton :variant="options.danger ? 'danger' : 'primary'" size="sm" @click="handleConfirm">
          {{ options.confirmText ?? 'تأكيد' }}
        </AppButton>
      </div>
    </template>
  </AppModal>
</template>
