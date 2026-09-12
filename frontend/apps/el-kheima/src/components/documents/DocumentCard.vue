<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppBadge, AppButton, AppCard, AppIcon } from '@resort-os/ui'
import type { VaultDocument } from '../../types/documents'
import { formatDocumentSize } from '../../services/documentVault'

const props = withDefaults(defineProps<{
  document: VaultDocument
  canManage?: boolean
  busy?: boolean
}>(), { canManage: false, busy: false })

defineEmits<{
  download: [document: VaultDocument]
  remove: [document: VaultDocument]
  restore: [document: VaultDocument]
}>()

const { t } = useI18n()
const { formatDate } = useStaffFormat()

const expiryVariant = computed<'success' | 'warning' | 'danger' | 'neutral'>(() => {
  const days = props.document.days_until_expiry
  if (days == null) return 'neutral'
  if (days < 0 || days <= 7) return 'danger'
  if (days <= 30) return 'warning'
  return 'success'
})

const expiryLabel = computed(() => {
  const days = props.document.days_until_expiry
  if (days == null) return t('backoffice.documents.noExpiry')
  if (days < 0) return t('backoffice.documents.expiredDays', { count: Math.abs(days) })
  if (days === 0) return t('backoffice.documents.expiresToday')
  return t('backoffice.documents.expiresInDays', { count: days })
})
</script>

<template>
  <AppCard padding="md" class="h-full">
    <article class="flex h-full flex-col gap-4">
      <div class="flex items-start justify-between gap-3">
        <div class="flex min-w-0 items-start gap-3">
          <span class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary-50 text-primary-700 dark:bg-primary-900/30 dark:text-primary-300">
            <AppIcon name="document" size="lg" />
          </span>
          <div class="min-w-0">
            <h3 class="break-words font-bold text-gray-900 dark:text-gray-100">
              {{ document.title }}
            </h3>
            <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {{ t(`backoffice.documents.types.${document.doc_type}`) }}
            </p>
          </div>
        </div>
        <AppBadge :variant="expiryVariant">{{ expiryLabel }}</AppBadge>
      </div>

      <p v-if="document.description" class="line-clamp-2 text-sm text-gray-600 dark:text-gray-300">
        {{ document.description }}
      </p>

      <dl class="grid grid-cols-2 gap-3 text-sm">
        <div>
          <dt class="text-gray-500 dark:text-gray-400">{{ t('backoffice.documents.issueDate') }}</dt>
          <dd class="mt-1 font-semibold text-gray-800 dark:text-gray-200">
            {{ document.issue_date ? formatDate(document.issue_date) : '—' }}
          </dd>
        </div>
        <div>
          <dt class="text-gray-500 dark:text-gray-400">{{ t('backoffice.documents.fileSize') }}</dt>
          <dd class="mt-1 font-semibold text-gray-800 dark:text-gray-200">
            {{ formatDocumentSize(document.size_bytes) }}
          </dd>
        </div>
      </dl>

      <div class="mt-auto flex flex-wrap gap-2 border-t border-stone-100 pt-4 dark:border-border">
        <AppButton
          v-if="document.is_deleted && canManage"
          type="button"
          size="sm"
          class="min-h-11 flex-1"
          :disabled="busy"
          @click="$emit('restore', document)"
        >
          <AppIcon name="refresh" />
          {{ t('backoffice.documents.restore') }}
        </AppButton>
        <AppButton
          v-else
          type="button"
          size="sm"
          class="min-h-11 flex-1"
          :disabled="busy"
          @click="$emit('download', document)"
        >
          <AppIcon name="download" />
          {{ t('backoffice.documents.download') }}
        </AppButton>
        <AppButton
          v-if="canManage && !document.is_deleted"
          type="button"
          variant="danger"
          size="sm"
          class="min-h-11"
          :aria-label="t('backoffice.documents.delete')"
          :disabled="busy"
          @click="$emit('remove', document)"
        >
          <AppIcon name="delete" />
          {{ t('backoffice.documents.delete') }}
        </AppButton>
      </div>
    </article>
  </AppCard>
</template>
