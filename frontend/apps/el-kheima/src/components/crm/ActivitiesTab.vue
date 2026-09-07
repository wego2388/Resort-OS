<script setup lang="ts">
// الأنشطة/المتابعات (Activities) — استُخرج من CRMView.vue (تقسيم الملفات
// الكبيرة، 2026-09-07). customers هنا نسخة محلية مستقلة (لقائمة الاختيار
// المنسدلة + عرض الاسم) — نفس نمط تكرار الجلب المتبع في تقسيم
// FinanceView.vue.
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, parseApiTimestamp } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

interface Customer { id: number; full_name: string }
interface Activity {
  id: number; customer_id: number; activity_type: string; title: string
  due_date: string; due_time?: string | null; assigned_to?: number | null
  status: string; done_at?: string | null; notes?: string | null; created_at: string
}

const { t } = useI18n()
const { formatDate: fmtDateFn } = useStaffFormat()
const toast = useToast()
const branchId = computed(() => props.branchId)

const loading = ref(false)
const customers = ref<Customer[]>([])
const activities = ref<Activity[]>([])
const activitiesTotal = ref(0)

const showActivityForm = ref(false)
const savingActivity = ref(false)
const activityForm = ref({
  customer_id: '' as number | '', activity_type: 'follow_up', title: '',
  due_date: '', due_time: '', notes: '',
})

const activityTypeLabels = computed<Record<string, string>>(() => ({
  follow_up: t('backoffice.crm.activityType.followUp'), meeting: t('backoffice.crm.activityType.meeting'),
  demo: t('backoffice.crm.activityType.demo'), proposal_send: t('backoffice.crm.activityType.proposalSend'),
  contract_sign: t('backoffice.crm.activityType.contractSign'),
}))
const activityStatusConfig = computed<Record<string, { label: string; variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }>>(() => ({
  pending:   { label: t('backoffice.crm.activityStatus.pending'),   variant: 'warning' },
  done:      { label: t('backoffice.crm.activityStatus.done'),      variant: 'success' },
  cancelled: { label: t('backoffice.crm.activityStatus.cancelled'), variant: 'danger' },
}))
const customerNameById = computed<Record<number, string>>(() => {
  const map: Record<number, string> = {}
  for (const c of customers.value) map[c.id] = c.full_name
  return map
})

function fmtDate(d?: string | null) {
  if (!d) return '—'
  try { return fmtDateFn(parseApiTimestamp(d)) } catch { return d }
}

async function loadCustomersForPicker() {
  if (customers.value.length) return
  try {
    const res = await api.get('/api/v1/crm/customers', { params: { branch_id: branchId.value, page: 1, size: 100 } })
    customers.value = res.data.items ?? []
  } catch { /* غير حرج — الاختيار المنسدل والعرض هيفضلوا بس بالـID */ }
}

async function loadActivities() {
  loading.value = true
  try {
    await loadCustomersForPicker()
    const res = await api.get('/api/v1/crm/activities', { params: { branch_id: branchId.value, size: 100 } })
    activities.value = res.data.items ?? res.data
    activitiesTotal.value = res.data.total ?? activities.value.length
  } catch { toast.error(t('backoffice.crm.msg.loadActivitiesError')) }
  finally { loading.value = false }
}

async function createActivity() {
  if (!activityForm.value.customer_id) { toast.error(t('backoffice.crm.msg.selectCustomer')); return }
  if (!activityForm.value.title.trim()) { toast.error(t('backoffice.crm.msg.activityTitleRequired')); return }
  if (!activityForm.value.due_date) { toast.error(t('backoffice.crm.msg.dueDateRequired')); return }
  savingActivity.value = true
  try {
    await api.post('/api/v1/crm/activities', {
      branch_id: branchId.value,
      customer_id: activityForm.value.customer_id,
      activity_type: activityForm.value.activity_type,
      title: activityForm.value.title,
      due_date: activityForm.value.due_date,
      due_time: activityForm.value.due_time || undefined,
      notes: activityForm.value.notes || undefined,
    })
    toast.success(t('backoffice.crm.msg.activityAdded'))
    showActivityForm.value = false
    activityForm.value = { customer_id: '', activity_type: 'follow_up', title: '', due_date: '', due_time: '', notes: '' }
    await loadActivities()
  } catch (e: unknown) {
    toast.error((e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? t('backoffice.crm.msg.activityAddError'))
  } finally {
    savingActivity.value = false
  }
}

async function setActivityStatus(activity: Activity, newStatus: string) {
  try {
    const res = await api.patch(`/api/v1/crm/activities/${activity.id}`, { status: newStatus })
    activity.status = res.data.status
    activity.done_at = res.data.done_at
  } catch { toast.error(t('backoffice.crm.msg.activityStatusUpdateError')) }
}

onMounted(loadActivities)
</script>

<template>
  <div>
    <div class="flex justify-end mb-4">
      <AppButton size="sm" @click="showActivityForm = !showActivityForm">
        {{ showActivityForm ? t('backoffice.crm.cancel') : `+ ${t('backoffice.crm.newActivity')}` }}
      </AppButton>
    </div>

    <AppCard v-if="showActivityForm" class="mb-4">
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <select v-model="activityForm.customer_id" class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm sm:col-span-2">
          <option value="">{{ t('backoffice.crm.selectCustomerRequired') }}</option>
          <option v-for="c in customers" :key="c.id" :value="c.id">{{ c.full_name }}</option>
        </select>
        <select v-model="activityForm.activity_type" class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
          <option v-for="(label, val) in activityTypeLabels" :key="val" :value="val">{{ label }}</option>
        </select>
        <input v-model="activityForm.title" type="text" :placeholder="t('backoffice.crm.activityTitleRequired')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        <input v-model="activityForm.due_date" type="date" class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        <input v-model="activityForm.due_time" type="time" class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        <input v-model="activityForm.notes" type="text" :placeholder="t('backoffice.crm.notes')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm sm:col-span-2" />
      </div>
      <AppButton class="mt-3" size="sm" :loading="savingActivity" @click="createActivity">{{ t('backoffice.crm.saveActivity') }}</AppButton>
    </AppCard>

    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
    <div v-else class="space-y-3">
      <div v-for="act in activities" :key="act.id" class="bg-white dark:bg-surface rounded-2xl border border-stone-200 dark:border-border p-4 shadow-sm flex items-center justify-between">
        <div>
          <div class="flex items-center gap-2 mb-1">
            <span class="font-bold text-gray-900 dark:text-gray-100">{{ act.title }}</span>
            <span class="text-xs text-gray-400 dark:text-gray-400">{{ customerNameById[act.customer_id] ?? t('backoffice.crm.customerHash', { id: act.customer_id }) }}</span>
          </div>
          <div class="flex items-center gap-2 text-xs flex-wrap">
            <span class="rounded-full bg-blue-50 px-2 py-0.5 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300">{{ activityTypeLabels[act.activity_type] ?? act.activity_type }}</span>
            <span class="text-gray-400 dark:text-gray-400">{{ t('backoffice.crm.dueLabel') }} {{ fmtDate(act.due_date) }}<span v-if="act.due_time"> — {{ act.due_time }}</span></span>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <AppBadge size="sm" :variant="activityStatusConfig[act.status]?.variant ?? 'neutral'">
            {{ activityStatusConfig[act.status]?.label ?? act.status }}
          </AppBadge>
          <AppButton v-if="act.status === 'pending'" size="sm" @click="setActivityStatus(act, 'done')">{{ t('backoffice.crm.markDone') }}</AppButton>
          <AppButton v-if="act.status === 'pending'" size="sm" variant="secondary" @click="setActivityStatus(act, 'cancelled')">{{ t('backoffice.crm.cancel') }}</AppButton>
        </div>
      </div>
      <EmptyState v-if="activities.length === 0" icon="🗓️" :title="t('backoffice.crm.noActivities')" />
      <!-- Truncation warning -->
      <p
        v-if="activitiesTotal > activities.length"
        class="px-4 py-2 text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg"
      >
        ⚠️ {{ t('common.showingOf', { shown: activities.length, total: activitiesTotal }) }} — {{ t('common.useSearchToFilter') }}
      </p>
    </div>
  </div>
</template>
