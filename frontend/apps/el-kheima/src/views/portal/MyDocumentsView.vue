<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@resort-os/core'
import { AppCard, AppIcon, EmptyState, ErrorState, LoadingState, useToast } from '@resort-os/ui'
import DocumentCard from '../../components/documents/DocumentCard.vue'
import { downloadPrivateDocument } from '../../services/documentVault'
import type { DocumentListResponse, VaultDocument } from '../../types/documents'

const { t } = useI18n()
const toast = useToast()
const documents = ref<VaultDocument[]>([])
const loading = ref(true)
const loadError = ref(false)
const workingId = ref<string | null>(null)

async function load() {
  loading.value = true
  loadError.value = false
  try {
    const { data } = await api.get<DocumentListResponse>('/api/v1/documents/me', {
      params: { size: 100 },
    })
    documents.value = data.items
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
      `/api/v1/documents/me/${document.id}/download`,
      document.original_filename,
    )
  } catch {
    toast.error(t('backoffice.documents.downloadFailed'))
  } finally {
    workingId.value = null
  }
}

onMounted(load)
</script>

<template>
  <div class="space-y-6">
    <header class="flex items-start gap-3">
      <span class="flex h-12 w-12 items-center justify-center rounded-2xl bg-primary-100 text-primary-700 dark:bg-primary-900/40 dark:text-primary-300">
        <AppIcon name="document" size="lg" />
      </span>
      <div>
        <h1 class="text-2xl font-black text-gray-900 dark:text-gray-100">
          {{ t('backoffice.documents.myTitle') }}
        </h1>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
          {{ t('backoffice.documents.mySubtitle') }}
        </p>
      </div>
    </header>

    <AppCard padding="md" class="border-info/30 bg-info/5">
      <div class="flex items-start gap-3 text-sm text-gray-700 dark:text-gray-200">
        <AppIcon name="shield" class="mt-0.5 text-info" />
        <p>{{ t('backoffice.documents.myPrivacyNote') }}</p>
      </div>
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
      icon="📄"
      :title="t('backoffice.documents.emptyMine')"
      :subtitle="t('backoffice.documents.emptyMineHint')"
    />
    <section v-else class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3" :aria-label="t('backoffice.documents.myTitle')">
      <DocumentCard
        v-for="document in documents"
        :key="document.id"
        :document="document"
        :busy="workingId === document.id"
        @download="download"
      />
    </section>
  </div>
</template>
