<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore } from '@resort-os/core'
import {
  AppBadge,
  AppButton,
  AppCard,
  AppIcon,
  AppSelect,
  EmptyState,
  ErrorState,
  LoadingState,
  SearchInput,
  useConfirm,
  useToast,
} from '@resort-os/ui'
import DocumentCard from '../../components/documents/DocumentCard.vue'
import UploadDocumentModal from '../../components/documents/UploadDocumentModal.vue'
import { downloadPrivateDocument } from '../../services/documentVault'
import {
  BRANCH_DOCUMENT_TYPES,
  type DocumentListResponse,
  type ExpiringDocument,
  type VaultDocument,
} from '../../types/documents'

const { t } = useI18n()
const auth = useAuthStore()
const toast = useToast()
const { confirm } = useConfirm()

const documents = ref<VaultDocument[]>([])
const expiring = ref<ExpiringDocument[]>([])
const loading = ref(true)
const loadError = ref(false)
const workingId = ref<string | null>(null)
const showUpload = ref(false)
const showDeleted = ref(false)
const search = ref('')
const docType = ref('')

const canManage = computed(() => auth.hasPermission('documents.branch:manage'))
const typeOptions = computed(() => [
  { value: 'all', label: t('backoffice.documents.allTypes') },
  ...BRANCH_DOCUMENT_TYPES.map(value => ({
    value,
    label: t(`backoffice.documents.types.${value}`),
  })),
])
const urgentCount = computed(() => expiring.value.filter(item => item.days_remaining <= 7).length)
const warningCount = computed(() => expiring.value.filter(item => item.days_remaining > 7).length)

async function load() {
  loading.value = true
  loadError.value = false
  try {
    const params = {
      search: search.value.trim() || undefined,
      doc_type: docType.value && docType.value !== 'all' ? docType.value : undefined,
      size: 100,
    }
    const listEndpoint = showDeleted.value
      ? '/api/v1/documents/branch/deleted'
      : '/api/v1/documents/branch'
    const [listResponse, expiryResponse] = await Promise.all([
      api.get<DocumentListResponse>(listEndpoint, { params: showDeleted.value ? { size: 100 } : params }),
      api.get<ExpiringDocument[]>('/api/v1/documents/branch/expiring', { params: { days: 60 } }),
    ])
    documents.value = listResponse.data.items
    expiring.value = expiryResponse.data
  } catch {
    loadError.value = true
    toast.error(t('backoffice.documents.loadFailed'))
  } finally {
    loading.value = false
  }
}

async function download(document: VaultDocument) {
  workingId.value = document.id
  try {
    await downloadPrivateDocument(
      `/api/v1/documents/branch/${document.id}/download`,
      document.original_filename,
    )
  } catch {
    toast.error(t('backoffice.documents.downloadFailed'))
  } finally {
    workingId.value = null
  }
}

async function remove(document: VaultDocument) {
  const accepted = await confirm({
    title: t('backoffice.documents.deleteTitle'),
    message: t('backoffice.documents.deleteMessage', { title: document.title }),
    confirmText: t('backoffice.documents.delete'),
    danger: true,
  })
  if (!accepted) return
  workingId.value = document.id
  try {
    await api.delete(`/api/v1/documents/branch/${document.id}`)
    toast.success(t('backoffice.documents.deleted'))
    await load()
  } catch {
    toast.error(t('backoffice.documents.deleteFailed'))
  } finally {
    workingId.value = null
  }
}

async function restore(document: VaultDocument) {
  workingId.value = document.id
  try {
    await api.post(`/api/v1/documents/branch/${document.id}/restore`)
    toast.success(t('backoffice.documents.restored'))
    await load()
  } catch {
    toast.error(t('backoffice.documents.restoreFailed'))
  } finally {
    workingId.value = null
  }
}

async function toggleDeleted() {
  showDeleted.value = !showDeleted.value
  await load()
}

async function handleUploaded() {
  showDeleted.value = false
  await load()
}

onMounted(load)
</script>

<template>
  <div class="space-y-6">
    <header class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <div class="flex items-center gap-3">
          <span class="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300">
            <AppIcon name="archive" size="lg" />
          </span>
          <div>
            <h1 class="text-2xl font-black text-gray-900 dark:text-gray-100">
              {{ t('backoffice.documents.branchTitle') }}
            </h1>
            <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {{ t('backoffice.documents.branchSubtitle') }}
            </p>
          </div>
        </div>
      </div>
      <div v-if="canManage" class="flex flex-wrap gap-2">
        <AppButton type="button" variant="outline" class="min-h-11" @click="toggleDeleted">
          <AppIcon :name="showDeleted ? 'arrow-right' : 'delete'" />
          {{ showDeleted ? t('backoffice.documents.backToActive') : t('backoffice.documents.deletedDocuments') }}
        </AppButton>
        <AppButton v-if="!showDeleted" type="button" class="min-h-11" @click="showUpload = true">
          <AppIcon name="upload" />
          {{ t('backoffice.documents.upload') }}
        </AppButton>
      </div>
    </header>

    <AppCard v-if="expiring.length && !showDeleted" padding="md" class="border-warning/40 bg-warning/5">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div class="flex items-start gap-3">
          <AppIcon name="warning" size="lg" class="mt-0.5 text-warning" />
          <div>
            <h2 class="font-bold text-gray-900 dark:text-gray-100">
              {{ t('backoffice.documents.expiryAttention') }}
            </h2>
            <p class="mt-1 text-sm text-gray-600 dark:text-gray-300">
              {{ t('backoffice.documents.expirySummary', { urgent: urgentCount, warning: warningCount }) }}
            </p>
          </div>
        </div>
        <div class="flex gap-2">
          <AppBadge v-if="urgentCount" variant="danger">
            {{ t('backoffice.documents.urgentCount', { count: urgentCount }) }}
          </AppBadge>
          <AppBadge v-if="warningCount" variant="warning">
            {{ t('backoffice.documents.warningCount', { count: warningCount }) }}
          </AppBadge>
        </div>
      </div>
    </AppCard>

    <AppCard v-if="!showDeleted" padding="md">
      <form class="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(13rem,18rem)_auto]" @submit.prevent="load">
        <SearchInput
          v-model="search"
          :placeholder="t('backoffice.documents.searchPlaceholder')"
        />
        <AppSelect
          v-model="docType"
          :options="typeOptions"
          :placeholder="t('backoffice.documents.allTypes')"
        />
        <AppButton type="submit" variant="outline" class="min-h-11" :disabled="loading">
          <AppIcon name="search" />
          {{ t('backoffice.documents.search') }}
        </AppButton>
      </form>
    </AppCard>

    <LoadingState v-if="loading" :label="t('backoffice.documents.loading')" />
    <ErrorState
      v-else-if="loadError"
      :title="t('backoffice.documents.loadFailed')"
      :message="t('backoffice.documents.loadFailedHint')"
      :retry-label="t('backoffice.documents.retry')"
      @retry="load"
    />
    <EmptyState
      v-else-if="documents.length === 0"
      icon="📁"
      :title="showDeleted ? t('backoffice.documents.emptyTrash') : t('backoffice.documents.emptyBranch')"
      :subtitle="showDeleted ? t('backoffice.documents.emptyTrashHint') : t('backoffice.documents.emptyBranchHint')"
    >
      <template v-if="canManage" #action>
        <AppButton type="button" class="min-h-11" @click="showUpload = true">
          <AppIcon name="upload" />
          {{ t('backoffice.documents.uploadFirst') }}
        </AppButton>
      </template>
    </EmptyState>
    <section v-else class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" :aria-label="t('backoffice.documents.branchTitle')">
      <DocumentCard
        v-for="document in documents"
        :key="document.id"
        :document="document"
        :can-manage="canManage"
        :busy="workingId === document.id"
        @download="download"
        @remove="remove"
        @restore="restore"
      />
    </section>

    <UploadDocumentModal
      :open="showUpload"
      scope="branch"
      @close="showUpload = false"
      @uploaded="handleUploaded"
    />
  </div>
</template>
