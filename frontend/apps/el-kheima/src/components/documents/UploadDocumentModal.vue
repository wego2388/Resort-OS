<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@resort-os/core'
import {
  AppButton,
  AppIcon,
  AppInput,
  AppModal,
  AppSelect,
  AppTextarea,
  useToast,
} from '@resort-os/ui'
import {
  BRANCH_DOCUMENT_TYPES,
  EMPLOYEE_DOCUMENT_TYPES,
  type DocumentScope,
  type VaultDocument,
} from '../../types/documents'

const props = defineProps<{
  open: boolean
  scope: DocumentScope
  employeeId?: number | null
}>()

const emit = defineEmits<{
  close: []
  uploaded: [document: VaultDocument]
}>()

const { t } = useI18n()
const toast = useToast()
const fileInput = ref<HTMLInputElement | null>(null)
const selectedFile = ref<File | null>(null)
const saving = ref(false)
const progress = ref(0)
const form = ref({
  docType: '',
  title: '',
  description: '',
  visibility: '',
  issueDate: '',
  expiryDate: '',
})

const typeOptions = computed(() => (
  props.scope === 'branch' ? BRANCH_DOCUMENT_TYPES : EMPLOYEE_DOCUMENT_TYPES
).map(value => ({
  value,
  label: t(`backoffice.documents.types.${value}`),
})))

const visibilityOptions = computed(() => (
  props.scope === 'branch'
    ? [
        { value: 'management', label: t('backoffice.documents.visibility.management') },
        { value: 'owner_visible', label: t('backoffice.documents.visibility.ownerVisible') },
      ]
    : [
        { value: 'hr_confidential', label: t('backoffice.documents.visibility.hrConfidential') },
        { value: 'employee_visible', label: t('backoffice.documents.visibility.employeeVisible') },
      ]
))

function reset() {
  form.value = {
    docType: '',
    title: '',
    description: '',
    visibility: props.scope === 'branch' ? 'management' : 'hr_confidential',
    issueDate: '',
    expiryDate: '',
  }
  selectedFile.value = null
  progress.value = 0
  if (fileInput.value) fileInput.value.value = ''
}

watch(() => props.open, isOpen => {
  if (isOpen) reset()
})

function selectFile(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0] ?? null
  if (!file) {
    selectedFile.value = null
    return
  }
  const allowed = new Set(['application/pdf', 'image/jpeg', 'image/png', 'image/webp'])
  if (!allowed.has(file.type) || file.size > 20 * 1024 * 1024) {
    toast.error(t('backoffice.documents.invalidFile'))
    input.value = ''
    selectedFile.value = null
    return
  }
  selectedFile.value = file
}

async function submit() {
  if (
    !form.value.docType
    || !form.value.title.trim()
    || !form.value.visibility
    || !selectedFile.value
    || (form.value.expiryDate && form.value.issueDate && form.value.expiryDate < form.value.issueDate)
  ) {
    toast.error(t('backoffice.documents.completeRequired'))
    return
  }
  if (props.scope === 'employee' && !props.employeeId) {
    toast.error(t('backoffice.documents.selectEmployee'))
    return
  }

  const payload = new FormData()
  payload.append('file', selectedFile.value)
  payload.append('doc_type', form.value.docType)
  payload.append('title', form.value.title.trim())
  payload.append('visibility', form.value.visibility)
  if (form.value.description.trim()) payload.append('description', form.value.description.trim())
  if (form.value.issueDate) payload.append('issue_date', form.value.issueDate)
  if (form.value.expiryDate) payload.append('expiry_date', form.value.expiryDate)

  const endpoint = props.scope === 'branch'
    ? '/api/v1/documents/branch/upload'
    : `/api/v1/documents/employee/${props.employeeId}/upload`
  saving.value = true
  progress.value = 0
  try {
    const { data } = await api.post<VaultDocument>(endpoint, payload, {
      onUploadProgress(event) {
        if (event.total) progress.value = Math.round((event.loaded / event.total) * 100)
      },
    })
    toast.success(t('backoffice.documents.uploaded'))
    emit('uploaded', data)
    emit('close')
  } catch {
    toast.error(t('backoffice.documents.uploadFailed'))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <AppModal
    :open="open"
    :title="t('backoffice.documents.uploadTitle')"
    size="lg"
    :close-label="t('backoffice.documents.close')"
    @close="emit('close')"
  >
    <form class="space-y-5" @submit.prevent="submit">
      <div class="grid gap-4 sm:grid-cols-2">
        <AppSelect
          v-model="form.docType"
          :label="t('backoffice.documents.documentType')"
          :options="typeOptions"
          :placeholder="t('backoffice.documents.chooseType')"
          required
        />
        <AppSelect
          v-model="form.visibility"
          :label="t('backoffice.documents.visibilityLabel')"
          :options="visibilityOptions"
          required
        />
      </div>

      <AppInput
        v-model="form.title"
        :label="t('backoffice.documents.titleLabel')"
        :placeholder="t('backoffice.documents.titlePlaceholder')"
        required
      />
      <AppTextarea
        v-model="form.description"
        :label="t('backoffice.documents.description')"
        :placeholder="t('backoffice.documents.descriptionPlaceholder')"
      />
      <div class="grid gap-4 sm:grid-cols-2">
        <AppInput v-model="form.issueDate" type="date" :label="t('backoffice.documents.issueDate')" />
        <AppInput v-model="form.expiryDate" type="date" :label="t('backoffice.documents.expiryDate')" />
      </div>

      <label class="block cursor-pointer rounded-xl border-2 border-dashed border-stone-300 p-5 text-center transition hover:border-primary-500 dark:border-border dark:hover:border-primary-400">
        <input
          ref="fileInput"
          class="sr-only"
          type="file"
          accept=".pdf,.jpg,.jpeg,.png,.webp,application/pdf,image/jpeg,image/png,image/webp"
          required
          @change="selectFile"
        />
        <span class="flex min-h-11 items-center justify-center gap-2 font-semibold text-primary-700 dark:text-primary-300">
          <AppIcon name="upload" />
          {{ selectedFile?.name || t('backoffice.documents.chooseFile') }}
        </span>
        <span class="mt-1 block text-xs text-gray-500 dark:text-gray-400">
          {{ t('backoffice.documents.fileHint') }}
        </span>
      </label>

      <div v-if="saving" class="space-y-2" role="status" aria-live="polite">
        <progress
          class="h-2 w-full overflow-hidden rounded-full accent-primary-600"
          :value="progress"
          max="100"
        />
        <p class="text-center text-sm text-gray-600 dark:text-gray-300">
          {{ t('backoffice.documents.uploadProgress', { progress }) }}
        </p>
      </div>

      <div class="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <AppButton type="button" variant="ghost" class="min-h-11" :disabled="saving" @click="emit('close')">
          {{ t('backoffice.documents.cancel') }}
        </AppButton>
        <AppButton type="submit" class="min-h-11" :loading="saving">
          <AppIcon name="shield" />
          {{ t('backoffice.documents.uploadSecurely') }}
        </AppButton>
      </div>
    </form>
  </AppModal>
</template>
