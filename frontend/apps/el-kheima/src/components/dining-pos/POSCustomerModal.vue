<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppBadge, AppButton, AppModal, EmptyState, LoadingState, SearchInput } from '@resort-os/ui'
import type { POSCustomer } from './types'

const props = defineProps<{
  open: boolean
  branchId: number
  selectedCustomerId: number | null
}>()
const emit = defineEmits<{
  close: []
  select: [customer: POSCustomer]
  clear: []
}>()

const { t } = useI18n()
const { formatNumber } = useStaffFormat()
const query = ref('')
const customers = ref<POSCustomer[]>([])
const loading = ref(false)
const error = ref('')

watch(() => props.open, (open) => {
  if (!open) return
  query.value = ''
  loadCustomers('')
})

async function loadCustomers(search: string) {
  loading.value = true
  error.value = ''
  try {
    const { data } = await api.get(ENDPOINTS.crm.customers, {
      params: {
        branch_id: props.branchId,
        search: search.trim() || undefined,
        page: 1,
        size: 30,
      },
    })
    customers.value = data?.items ?? []
  } catch {
    error.value = t('backoffice.pos.customer.errors.load')
  } finally {
    loading.value = false
  }
}

function choose(customer: POSCustomer) {
  if (customer.blacklisted) return
  emit('select', customer)
}
</script>

<template>
  <AppModal
    :open="open"
    :title="t('backoffice.pos.customer.title')"
    size="lg"
    :close-label="t('backoffice.pos.close')"
    @close="emit('close')"
  >
    <div class="space-y-4">
      <SearchInput
        v-model="query"
        :placeholder="t('backoffice.pos.customer.searchPlaceholder')"
        :clear-label="t('backoffice.pos.customer.clearSearch')"
        :debounce-ms="300"
        @search="loadCustomers"
      />

      <p v-if="error" role="alert" class="rounded-xl bg-danger/10 text-danger px-4 py-3 text-sm">
        {{ error }}
      </p>
      <LoadingState v-else-if="loading" :label="t('backoffice.pos.customer.loading')" />
      <EmptyState
        v-else-if="customers.length === 0"
        icon="👤"
        :title="t('backoffice.pos.customer.noResults')"
        :subtitle="t('backoffice.pos.customer.noResultsHint')"
      />
      <div v-else class="grid sm:grid-cols-2 gap-2 max-h-[55vh] overflow-y-auto pe-1">
        <button
          v-for="customer in customers"
          :key="customer.id"
          type="button"
          :disabled="customer.blacklisted"
          :aria-pressed="selectedCustomerId === customer.id"
          :class="[
            'min-h-[84px] rounded-xl border-2 px-4 py-3 text-start transition-colors',
            selectedCustomerId === customer.id
              ? 'border-primary-700 bg-primary-50'
              : 'border-stone-200 dark:border-border hover:border-primary-300',
            customer.blacklisted ? 'opacity-60 cursor-not-allowed bg-danger/5' : '',
          ]"
          @click="choose(customer)"
        >
          <div class="flex items-start justify-between gap-2">
            <div class="min-w-0">
              <div class="font-bold text-gray-900 dark:text-gray-100 truncate">{{ customer.full_name }}</div>
              <div class="text-sm text-gray-500 dark:text-gray-400 mt-1">{{ customer.phone || t('backoffice.pos.customer.noPhone') }}</div>
            </div>
            <AppBadge v-if="customer.blacklisted" variant="danger">{{ t('backoffice.pos.customer.blacklisted') }}</AppBadge>
            <AppBadge v-else-if="customer.segment === 'vip'" variant="warning">VIP</AppBadge>
          </div>
          <div class="text-xs text-gray-400 mt-2">
            {{ t('backoffice.pos.customer.visits', { count: formatNumber(customer.visits_count) }) }}
          </div>
          <div v-if="customer.blacklisted && customer.blacklist_reason" class="text-xs text-danger mt-1">
            {{ customer.blacklist_reason }}
          </div>
        </button>
      </div>
    </div>

    <template #footer>
      <div class="flex items-center justify-between gap-2">
        <AppButton
          v-if="selectedCustomerId !== null"
          variant="ghost"
          @click="emit('clear')"
        >
          {{ t('backoffice.pos.customer.remove') }}
        </AppButton>
        <span v-else />
        <AppButton variant="outline" @click="emit('close')">
          {{ t('backoffice.pos.close') }}
        </AppButton>
      </div>
    </template>
  </AppModal>
</template>
