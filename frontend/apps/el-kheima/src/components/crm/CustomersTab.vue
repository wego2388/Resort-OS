<script setup lang="ts">
// العملاء + مجموعات الخصم الدائم — استُخرج من CRMView.vue (تقسيم الملفات
// الكبيرة، 2026-09-07).
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, AppModal, AppSpinner, EmptyState, SearchInput, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface Customer {
  id: number; full_name: string; phone?: string; email?: string; segment: string
  total_spent: number; visits_count: number; vip_flag?: boolean; blacklisted: boolean
  customer_group_id?: number | null
}
interface CustomerGroup {
  id: number; name: string; name_ar?: string | null; discount_percentage: number; is_active: boolean
  is_complimentary: boolean
}

const { t } = useI18n()
const { formatNumber } = useStaffFormat()
const toast = useToast()
const authStore = useAuthStore()
const branchId = computed(() => props.branchId)

const loading = ref(false)
const customers = ref<Customer[]>([])
const customersTotal = ref(0)
const customerSearch = ref('')

const showCustomerForm = ref(false)
const savingCustomer = ref(false)
const customerForm = ref({
  full_name: '', phone: '', email: '', nationality: '', segment: 'regular', notes: '',
})

// ── مجموعات العملاء (خصم دائم) ──────────────────────────────────────────
// قراءة لمدير+، إنشاء/تعديل لـ admin+ فقط — نفس نمط /finance/discounts.
const groups = ref<CustomerGroup[]>([])
const groupModal = ref(false)
const savingGroup = ref(false)
const editingGroup = ref<CustomerGroup | null>(null)
const groupForm = ref({ name: '', name_ar: '', discount_percentage: '10', is_complimentary: false })

function openCreateGroup() {
  editingGroup.value = null
  groupForm.value = { name: '', name_ar: '', discount_percentage: '10', is_complimentary: false }
}
function openEditGroup(g: CustomerGroup) {
  editingGroup.value = g
  groupForm.value = {
    name: g.name, name_ar: g.name_ar ?? '', discount_percentage: String(g.discount_percentage),
    is_complimentary: g.is_complimentary,
  }
}

const segmentVariants: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'neutral'> = {
  regular: 'neutral', vip: 'warning', corporate: 'info', travel_agent: 'info',
}
const segmentLabels = computed<Record<string, string>>(() => ({
  regular: t('backoffice.crm.segment.regular'), vip: t('backoffice.crm.segment.vip'),
  corporate: t('backoffice.crm.segment.corporate'), travel_agent: t('backoffice.crm.segment.travelAgent'),
}))

async function loadCustomers() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/crm/customers', {
      params: { branch_id: branchId.value, search: customerSearch.value.trim() || undefined, page: 1, size: 100 },
    })
    customers.value = res.data.items ?? []
    customersTotal.value = res.data.total ?? customers.value.length
    if (authStore.roleLevel >= 60) await loadGroups()
  } catch { toast.error(t('backoffice.crm.msg.loadCustomersError')) }
  finally { loading.value = false }
}

async function loadGroups() {
  try {
    const res = await api.get('/api/v1/crm/customer-groups', { params: { branch_id: branchId.value, active_only: false } })
    groups.value = res.data ?? []
  } catch {
    // غير حرج لعرض قائمة العملاء — بس هيمنع تعيين/عرض المجموعات لو فشل
  }
}

async function saveGroup() {
  if (!groupForm.value.name.trim()) { toast.error(t('backoffice.crm.msg.groupNameRequired')); return }
  savingGroup.value = true
  try {
    const payload = {
      name: groupForm.value.name,
      name_ar: groupForm.value.name_ar || undefined,
      discount_percentage: groupForm.value.discount_percentage || '0',
      is_complimentary: groupForm.value.is_complimentary,
    }
    if (editingGroup.value) {
      await api.patch(`/api/v1/crm/customer-groups/${editingGroup.value.id}`, payload)
      toast.success(t('backoffice.crm.msg.groupUpdated'))
    } else {
      await api.post('/api/v1/crm/customer-groups', { branch_id: branchId.value, ...payload })
      toast.success(t('backoffice.crm.msg.groupAdded'))
    }
    openCreateGroup()
    await loadGroups()
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.crm.msg.groupSaveError'))
  } finally {
    savingGroup.value = false
  }
}

async function toggleGroupActive(g: CustomerGroup) {
  try {
    await api.patch(`/api/v1/crm/customer-groups/${g.id}`, { is_active: !g.is_active })
    await loadGroups()
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.crm.msg.groupStatusUpdateError'))
  }
}

async function assignGroup(customer: Customer, groupId: number | '') {
  try {
    const { data } = await api.patch(`/api/v1/crm/customers/${customer.id}/group`, {
      customer_group_id: groupId === '' ? null : groupId,
    })
    const idx = customers.value.findIndex(c => c.id === customer.id)
    if (idx !== -1) customers.value[idx] = data
    toast.success(t('backoffice.crm.msg.customerGroupUpdated'))
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.crm.msg.customerGroupUpdateError'))
  }
}

async function createCustomer() {
  if (!customerForm.value.full_name) { toast.error(t('backoffice.crm.msg.customerNameRequired')); return }
  savingCustomer.value = true
  try {
    await api.post('/api/v1/crm/customers', {
      branch_id: branchId.value,
      full_name: customerForm.value.full_name,
      phone: customerForm.value.phone || undefined,
      email: customerForm.value.email || undefined,
      nationality: customerForm.value.nationality || undefined,
      segment: customerForm.value.segment,
      source: 'walk_in',
      notes: customerForm.value.notes || undefined,
    })
    toast.success(t('backoffice.crm.msg.customerAdded'))
    showCustomerForm.value = false
    customerForm.value = { full_name: '', phone: '', email: '', nationality: '', segment: 'regular', notes: '' }
    await loadCustomers()
  } catch (e: unknown) {
    // رسالة الباك إند بتوضّح اسم/رقم العميل المكرر فعليًا — نعرضها زي ما هي
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.crm.msg.customerAddError'))
  } finally {
    savingCustomer.value = false
  }
}

onMounted(loadCustomers)
</script>

<template>
  <div>
    <div class="flex items-center justify-end mb-4 gap-2">
      <AppButton v-if="authStore.roleLevel >= 60" size="sm" variant="secondary" @click="groupModal = true">
        🏷️ {{ t('backoffice.crm.customerGroups') }}
      </AppButton>
      <AppButton size="sm" @click="showCustomerForm = !showCustomerForm">
        {{ showCustomerForm ? t('backoffice.crm.cancel') : `+ ${t('backoffice.crm.newCustomer')}` }}
      </AppButton>
    </div>

    <SearchInput
      v-model="customerSearch"
      :placeholder="t('backoffice.crm.searchCustomersPlaceholder')"
      :debounce-ms="300"
      class="mb-3"
      @search="loadCustomers"
    />
    <AppCard v-if="showCustomerForm" class="mb-4">
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <input v-model="customerForm.full_name" type="text" :placeholder="t('backoffice.crm.fullNameRequired')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm sm:col-span-2" />
        <input v-model="customerForm.phone" type="text" :placeholder="t('backoffice.crm.phone')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        <input v-model="customerForm.email" type="email" :placeholder="t('backoffice.crm.email')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        <select v-model="customerForm.segment" class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
          <option value="regular">{{ t('backoffice.crm.segment.regular') }}</option>
          <option value="vip">VIP</option>
          <option value="corporate">{{ t('backoffice.crm.segment.corporate') }}</option>
          <option value="travel_agent">{{ t('backoffice.crm.segment.travelAgent') }}</option>
        </select>
        <input v-model="customerForm.nationality" type="text" :placeholder="t('backoffice.crm.nationality')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        <input v-model="customerForm.notes" type="text" :placeholder="t('backoffice.crm.notes')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm sm:col-span-2" />
      </div>
      <AppButton class="mt-3" size="sm" :loading="savingCustomer" @click="createCustomer">{{ t('backoffice.crm.saveCustomer') }}</AppButton>
    </AppCard>

    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
    <AppCard v-else padding="none">
      <div class="overflow-x-auto">
      <table class="w-full min-w-[560px]">
        <thead class="bg-stone-50 dark:bg-gray-800/60">
          <tr>
            <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.crm.customer') }}</th>
            <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.crm.segmentCol') }}</th>
            <th v-if="authStore.roleLevel >= 60" class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.crm.discountGroup') }}</th>
            <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.crm.visits') }}</th>
            <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-400 uppercase">{{ t('backoffice.crm.totalSpent') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in customers" :key="c.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
            <td class="px-4 py-3">
              <div class="flex items-center gap-2">
                <span v-if="c.vip_flag" class="text-amber-500 text-sm">⭐</span>
                <div>
                  <div class="font-medium text-gray-900 dark:text-gray-100 text-sm flex items-center gap-1">
                    {{ c.full_name }}
                    <AppBadge v-if="c.blacklisted" size="sm" variant="danger">{{ t('backoffice.crm.blacklisted') }}</AppBadge>
                  </div>
                  <div v-if="c.phone" class="text-xs text-gray-400 dark:text-gray-400">{{ c.phone }}</div>
                </div>
              </div>
            </td>
            <td class="px-4 py-3">
              <AppBadge size="sm" :variant="segmentVariants[c.segment] ?? 'neutral'">
                {{ segmentLabels[c.segment] ?? segmentLabels.regular }}
              </AppBadge>
            </td>
            <td v-if="authStore.roleLevel >= 60" class="px-4 py-3">
              <select :value="c.customer_group_id ?? ''" @change="assignGroup(c, ($event.target as HTMLSelectElement).value ? Number(($event.target as HTMLSelectElement).value) : '')"
                class="border border-stone-200 dark:border-border rounded-lg px-2 py-1 text-xs">
                <option value="">{{ t('backoffice.crm.noGroup') }}</option>
                <option v-for="g in groups" :key="g.id" :value="g.id">{{ g.name_ar || g.name }} ({{ g.discount_percentage }}%)</option>
              </select>
            </td>
            <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300 font-medium">{{ c.visits_count }}</td>
            <td class="px-4 py-3 text-sm font-bold text-blue-700 dark:text-blue-300">{{ formatNumber(c.total_spent) }} {{ t('backoffice.crm.egp') }}</td>
          </tr>
          <tr v-if="customers.length === 0">
            <td colspan="5" class="px-4 py-8">
              <EmptyState icon="👥" :title="t('backoffice.crm.noCustomers')" />
            </td>
          </tr>
        </tbody>
      </table>
      </div>
    </AppCard>
    <p
      v-if="customersTotal > customers.length"
      class="mt-2 px-4 py-2 text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg"
    >
      ⚠️ {{ t('common.showingOf', { shown: customers.length, total: customersTotal }) }} — {{ t('common.useSearchToFilter') }}
    </p>

    <!-- مجموعات العملاء (خصم دائم) -->
    <AppModal :open="groupModal" :title="t('backoffice.crm.customerGroups')" size="lg" @close="groupModal = false">
      <div class="space-y-4">
        <p class="text-xs text-gray-500 dark:text-gray-400">
          {{ t('backoffice.crm.groupsHint') }}
        </p>

        <AppCard v-if="authStore.hasPermission('crm.customer_groups:manage')" padding="sm">
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <input v-model="groupForm.name" type="text" :placeholder="t('backoffice.crm.nameEnglishRequired')"
              class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
            <input v-model="groupForm.name_ar" type="text" :placeholder="t('backoffice.crm.nameArabic')"
              class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
            <input v-model="groupForm.discount_percentage" type="number" min="0" max="100" step="0.01" :placeholder="t('backoffice.crm.discountPct')"
              class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          </div>
          <label class="flex items-center gap-2 mt-2 text-sm text-gray-700 dark:text-gray-300">
            <input v-model="groupForm.is_complimentary" type="checkbox"
              class="rounded border-stone-300 dark:border-border" />
            {{ t('backoffice.crm.groupComplimentary') }}
            <span class="text-xs text-gray-400 dark:text-gray-400">({{ t('backoffice.crm.groupComplimentaryHint') }})</span>
          </label>
          <div class="flex gap-2 mt-2">
            <AppButton size="sm" :loading="savingGroup" @click="saveGroup">
              {{ editingGroup ? t('backoffice.crm.saveEdits') : t('backoffice.crm.addGroup') }}
            </AppButton>
            <AppButton v-if="editingGroup" size="sm" variant="secondary" @click="openCreateGroup">{{ t('backoffice.crm.cancelEdit') }}</AppButton>
          </div>
        </AppCard>
        <p v-else class="text-xs text-amber-600 dark:text-amber-300">{{ t('backoffice.crm.groupsAdminOnly') }}</p>

        <div class="border-t border-stone-100 dark:border-border/50 pt-3 space-y-2">
          <div v-for="g in groups" :key="g.id" class="flex items-center justify-between bg-stone-50 dark:bg-gray-800/60 rounded-xl px-3 py-2">
            <div>
              <span class="font-medium text-sm text-gray-900 dark:text-gray-100">{{ g.name_ar || g.name }}</span>
              <span class="text-xs text-gray-500 dark:text-gray-400 ms-2">{{ t('backoffice.crm.discountOf', { pct: g.discount_percentage }) }}</span>
              <AppBadge v-if="g.is_complimentary" size="sm" variant="info" class="ms-2">{{ t('backoffice.crm.groupComplimentary') }}</AppBadge>
            </div>
            <div class="flex items-center gap-2">
              <AppBadge size="sm" :variant="g.is_active ? 'success' : 'neutral'">{{ g.is_active ? t('backoffice.crm.groupActive') : t('backoffice.crm.groupSuspended') }}</AppBadge>
              <template v-if="authStore.hasPermission('crm.customer_groups:manage')">
                <button @click="openEditGroup(g)" class="text-xs font-semibold text-primary-700 hover:underline">{{ t('backoffice.crm.edit') }}</button>
                <button @click="toggleGroupActive(g)" class="text-xs font-semibold text-gray-500 dark:text-gray-400 hover:underline">
                  {{ g.is_active ? t('backoffice.crm.suspend') : t('backoffice.crm.activate') }}
                </button>
              </template>
            </div>
          </div>
          <EmptyState v-if="groups.length === 0" icon="🏷️" :title="t('backoffice.crm.noGroups')" />
        </div>
      </div>
    </AppModal>
  </div>
</template>
