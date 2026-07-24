<script setup lang="ts">
// Mounted once globally in App.vue — see composables/useConfirm.ts.
// i18n fallback strings are passed as props from App.vue (which has vue-i18n)
// so this package stays free of a direct vue-i18n dependency.
import AppModal from './Modal.vue'
import AppButton from './Button.vue'
import { useConfirm } from '../composables/useConfirm'

const props = withDefaults(defineProps<{
  /** Translated fallback shown when no title is passed to confirm() */
  defaultTitle?: string
  /** Translated fallback for the confirm button */
  defaultConfirmText?: string
  /** Translated fallback for the cancel button */
  defaultCancelText?: string
}>(), {
  defaultTitle: 'تأكيد',
  defaultConfirmText: 'تأكيد',
  defaultCancelText: 'إلغاء',
})

const { isOpen, options, handleConfirm, handleCancel } = useConfirm()

// Stable ID for aria-describedby — single global instance, no collision risk.
const descId = 'confirm-dialog-desc'
</script>

<template>
  <AppModal
    :open="isOpen"
    :title="options.title ?? props.defaultTitle"
    :aria-describedby="descId"
    size="sm"
    z-index="z-[60]"
    @close="handleCancel"
  >
    <p :id="descId" class="text-gray-700 dark:text-gray-300 text-sm leading-relaxed">{{ options.message }}</p>
    <template #footer>
      <div class="flex items-center justify-end gap-2">
        <AppButton variant="ghost" size="sm" @click="handleCancel">
          {{ options.cancelText ?? props.defaultCancelText }}
        </AppButton>
        <AppButton :variant="options.danger ? 'danger' : 'primary'" size="sm" @click="handleConfirm">
          {{ options.confirmText ?? props.defaultConfirmText }}
        </AppButton>
      </div>
    </template>
  </AppModal>
</template>
