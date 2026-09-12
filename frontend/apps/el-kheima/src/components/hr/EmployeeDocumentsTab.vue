<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore } from '@resort-os/core'
import {
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
import DocumentCard from '../documents/DocumentCard.vue'
import UploadDocumentModal from '../documents/UploadDocumentModal.vue'
import { downloadPrivateDocument } from '../../services/documentVault'
import type { DocumentListResponse, VaultDocument } from '../../types/documents'

interface EmployeeSummary {
  id: number
  employee_code: string
  full_name: string
  status: string
}

const { t } = useI18n()
const auth = useAuthStore()
const toast = useToast()
const { confirm } = useConfirm()

const employees = ref<EmployeeSummary[]>([])
const selectedEmployeeId = ref('')
const documents = ref<VaultDocument[]>([])
const employeeSearch = ref('')
const loadingEmployees = ref(true)
const loadingDocuments = ref(false)
const loadError = ref(false)
const workingId = ref<string | null>(null)
const showUpload = ref(false)
const showDeleted = ref(false)

const canManage = computed(() => auth.hasPermission('documents.employee:manage'))
const selectedEmployee = computed(() =>
  employees.value.find(employee => String(employee.id) === selectedEmployeeId.value) ?? null,
)
const employeeOptions = computed(() => employees.value.map(employee => ({
  value: employee.id,
  label: `${employee.full_name} (${employee.employee_code})`,
})))

async function loadEmployees() {
  loadingEmployees.value = true
  loadError.value = false
  try {
    const { data } = await api.get('/api/v1/hr/employees', {
      params: {
        branch_id: auth.branchId,
        search: employeeSearch.value.trim() || undefined,
        size: 100,
      },
    })
    employees.value = data.employees ?? data.items ?? data
    if (
      selectedEmployeeId.value
      && !employees.value.some(employee => String(employee.id) === selectedEmployeeId.value)
    ) {
      selectedEmployeeId.value = ''
      documents.value = []
    }
  } catch {
    loadError.value = true
    toast.error(t('backoffice.documents.loadEmployeesFailed'))
  } finally {
    loadingEmployees.value = false
  }
}

async function loadDocuments() {
  if (!selectedEmployeeId.value) {
    documents.value = []
    return
  }
  loadingDocuments.value = true
  loadError.value = false
  try {
    const suffix = showDeleted.value ? '/deleted' : ''
    const { data } = await api.get<DocumentListResponse>(
      `/api/v1/documents/employee/${selectedEmployeeId.value}${suffix}`,
      { params: { size: 100 } },
    )
    documents.value = data.items
  } catch {
    loadError.value = true
    toast.error(t('backoffice.documents.loadFailed'))
  } finally {
    loadingDocuments.value = false
  }
}

async function download(document: VaultDocument) {
  if (!selectedEmployeeId.value) return
  workingId.value = document.id
  try {
    await downloadPrivateDocument(
      `/api/v1/documents/employee/${selectedEmployeeId.value}/${document.id}/download`,
      document.original_filename,
    )
  } catch {
    toast.error(t('backoffice.documents.downloadFailed'))
  } finally {
    workingId.value = null
  }
}

async function remove(document: VaultDocument) {
  if (!selectedEmployeeId.value) return
  const accepted = await confirm({
    title: t('backoffice.documents.deleteTitle'),
    message: t('backoffice.documents.deleteMessage', { title: document.title }),
    confirmText: t('backoffice.documents.delete'),
    danger: true,
  })
  if (!accepted) return
  workingId.value = document.id
  try {
    await api.delete(`/api/v1/documents/employee/${selectedEmployeeId.value}/${document.id}`)
    toast.success(t('backoffice.documents.deleted'))
    await loadDocuments()
  } catch {
    toast.error(t('backoffice.documents.deleteFailed'))
  } finally {
    workingId.value = null
  }
}

async function restore(document: VaultDocument) {
  if (!selectedEmployeeId.value) return
  workingId.value = document.id
  try {
    await api.post(
      `/api/v1/documents/employee/${selectedEmployeeId.value}/${document.id}/restore`,
    )
    toast.success(t('backoffice.documents.restored'))
    await loadDocuments()
  } catch {
    toast.error(t('backoffice.documents.restoreFailed'))
  } finally {
    workingId.value = null
  }
}

async function toggleDeleted() {
  showDeleted.value = !showDeleted.value
  await loadDocuments()
}

async function handleUploaded() {
  showDeleted.value = false
  await loadDocuments()
}

watch(selectedEmployeeId, loadDocuments)
onMounted(loadEmployees)
</script>

<template>
  <div class="space-y-5">
    <AppCard padding="md">
      <div class="mb-4 flex items-start gap-3">
        <AppIcon name="shield" size="lg" class="mt-0.5 text-primary-700 dark:text-primary-300" />
        <div>
          <h3 class="font-black text-gray-900 dark:text-gray-100">
            {{ t('backoffice.documents.employeeTitle') }}
          </h3>
          <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
            {{ t('backoffice.documents.employeePrivacyNote') }}
          </p>
        </div>
      </div>
      <form class="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]" @submit.prevent="loadEmployees">
        <SearchInput
          v-model="employeeSearch"
          :placeholder="t('backoffice.documents.searchEmployee')"
        />
        <AppButton type="submit" variant="outline" class="min-h-11" :disabled="loadingEmployees">
          <AppIcon name="search" />
          {{ t('backoffice.documents.search') }}
        </AppButton>
      </form>
      <div class="mt-4 grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-end">
        <AppSelect
          v-model="selectedEmployeeId"
          :label="t('backoffice.documents.employee')"
          :placeholder="t('backoffice.documents.selectEmployee')"
          :options="employeeOptions"
        />
        <div v-if="canManage && selectedEmployee" class="flex flex-wrap gap-2">
          <AppButton type="button" variant="outline" class="min-h-11" @click="toggleDeleted">
            <AppIcon :name="showDeleted ? 'arrow-right' : 'delete'" />
            {{ showDeleted ? t('backoffice.documents.backToActive') : t('backoffice.documents.deletedDocuments') }}
          </AppButton>
          <AppButton v-if="!showDeleted" type="button" class="min-h-11" @click="showUpload = true">
            <AppIcon name="upload" />
            {{ t('backoffice.documents.upload') }}
          </AppButton>
        </div>
      </div>
    </AppCard>

    <LoadingState
      v-if="loadingEmployees || loadingDocuments"
      :label="t('backoffice.documents.loading')"
    />
    <ErrorState
      v-else-if="loadError"
      :title="t('backoffice.documents.loadFailed')"
      :message="t('backoffice.documents.loadFailedHint')"
      :retry-label="t('backoffice.documents.retry')"
      @retry="selectedEmployeeId ? loadDocuments() : loadEmployees()"
    />
    <EmptyState
      v-else-if="!selectedEmployee"
      icon="👤"
      :title="t('backoffice.documents.chooseEmployeeTitle')"
      :subtitle="t('backoffice.documents.chooseEmployeeHint')"
    />
    <EmptyState
      v-else-if="documents.length === 0"
      icon="📄"
      :title="showDeleted ? t('backoffice.documents.emptyTrash') : t('backoffice.documents.emptyEmployee')"
      :subtitle="showDeleted ? t('backoffice.documents.emptyTrashHint') : t('backoffice.documents.emptyEmployeeHint', { name: selectedEmployee.full_name })"
    >
      <template v-if="canManage" #action>
        <AppButton type="button" class="min-h-11" @click="showUpload = true">
          <AppIcon name="upload" />
          {{ t('backoffice.documents.uploadFirst') }}
        </AppButton>
      </template>
    </EmptyState>
    <section
      v-else
      class="grid gap-4 sm:grid-cols-2 xl:grid-cols-3"
      :aria-label="t('backoffice.documents.employeeTitle')"
    >
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
      v-if="selectedEmployee"
      :open="showUpload"
      scope="employee"
      :employee-id="selectedEmployee.id"
      @close="showUpload = false"
      @uploaded="handleUploaded"
    />
  </div>
</template>
