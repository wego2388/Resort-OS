<script setup lang="ts">
// الفرص البيعية (Opportunities) — استُخرج من CRMView.vue (تقسيم الملفات
// الكبيرة، 2026-09-07). customers هنا نسخة محلية مستقلة (لقائمة الاختيار
// المنسدلة + عرض الاسم) — نفس نمط تكرار الجلب المتبع في تقسيم
// FinanceView.vue.
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, parseApiTimestamp } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface Customer { id: number; full_name: string }
interface Opportunity {
  id: number; customer_id: number; title: string; product_type: string; stage: string
  expected_value: number; probability: number; assigned_to?: number | null
  expected_close?: string | null; closed_at?: string | null
  lost_reason?: string | null; notes?: string | null; created_at: string
}

const { t } = useI18n()
const { formatNumber, formatDate: fmtDateFn } = useStaffFormat()
const toast = useToast()
const branchId = computed(() => props.branchId)

const loading = ref(false)
const customers = ref<Customer[]>([])
const opportunities = ref<Opportunity[]>([])
const opportunitiesTotal = ref(0)

const showOpportunityForm = ref(false)
const savingOpportunity = ref(false)
const opportunityForm = ref({
  customer_id: '' as number | '', title: '', product_type: 'other',
  expected_value: '0', probability: '20', expected_close: '', notes: '',
})

const productTypeLabels = computed<Record<string, string>>(() => ({
  timeshare: t('backoffice.crm.productType.timeshare'), leasing: t('backoffice.crm.productType.leasing'),
  membership: t('backoffice.crm.productType.membership'), group_booking: t('backoffice.crm.productType.groupBooking'),
  other: t('backoffice.crm.productType.other'),
}))
const oppStageConfig = computed<Record<string, { label: string; variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }>>(() => ({
  lead:        { label: t('backoffice.crm.oppStages.lead'),        variant: 'neutral' },
  qualified:   { label: t('backoffice.crm.oppStages.qualified'),   variant: 'info' },
  proposal:    { label: t('backoffice.crm.oppStages.proposal'),    variant: 'warning' },
  negotiation: { label: t('backoffice.crm.oppStages.negotiation'), variant: 'warning' },
  won:         { label: t('backoffice.crm.oppStages.won'),         variant: 'success' },
  lost:        { label: t('backoffice.crm.oppStages.lost'),        variant: 'danger' },
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

async function loadOpportunities() {
  loading.value = true
  try {
    await loadCustomersForPicker()
    const res = await api.get('/api/v1/crm/opportunities', { params: { branch_id: branchId.value, size: 100 } })
    opportunities.value = res.data.items ?? res.data
    opportunitiesTotal.value = res.data.total ?? opportunities.value.length
  } catch { toast.error(t('backoffice.crm.msg.loadOpportunitiesError')) }
  finally { loading.value = false }
}

async function createOpportunity() {
  if (!opportunityForm.value.customer_id) { toast.error(t('backoffice.crm.msg.selectCustomer')); return }
  if (!opportunityForm.value.title.trim()) { toast.error(t('backoffice.crm.msg.oppTitleRequired')); return }
  savingOpportunity.value = true
  try {
    await api.post('/api/v1/crm/opportunities', {
      branch_id: branchId.value,
      customer_id: opportunityForm.value.customer_id,
      title: opportunityForm.value.title,
      product_type: opportunityForm.value.product_type,
      expected_value: opportunityForm.value.expected_value || '0',
      probability: Number(opportunityForm.value.probability) || 20,
      expected_close: opportunityForm.value.expected_close || undefined,
      notes: opportunityForm.value.notes || undefined,
    })
    toast.success(t('backoffice.crm.msg.oppAdded'))
    showOpportunityForm.value = false
    opportunityForm.value = { customer_id: '', title: '', product_type: 'other', expected_value: '0', probability: '20', expected_close: '', notes: '' }
    await loadOpportunities()
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.crm.msg.oppAddError'))
  } finally {
    savingOpportunity.value = false
  }
}

// خسارة فرصة محتاجة سبب إجباري — بدل window.prompt() (اتشالت من المشروع
// كله في مراجعة سابقة، راجع CLAUDE.md)، حقل نص مصغّر بيظهر جوه الصف نفسه.
const lostOpportunityId = ref<number | null>(null)
const lostOpportunityReason = ref('')

function openLostOpportunity(opp: Opportunity) {
  lostOpportunityId.value = opp.id
  lostOpportunityReason.value = ''
}

async function confirmOpportunityLost() {
  if (!lostOpportunityId.value) return
  if (!lostOpportunityReason.value.trim()) { toast.error(t('backoffice.crm.msg.lostReasonRequired')); return }
  try {
    const res = await api.patch(`/api/v1/crm/opportunities/${lostOpportunityId.value}`, {
      stage: 'lost', lost_reason: lostOpportunityReason.value,
    })
    const opp = opportunities.value.find(o => o.id === lostOpportunityId.value)
    if (opp) { opp.stage = res.data.stage; opp.lost_reason = res.data.lost_reason }
    lostOpportunityId.value = null
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.crm.msg.oppStatusUpdateError'))
  }
}

async function setOpportunityStage(opp: Opportunity, stage: string) {
  try {
    const res = await api.patch(`/api/v1/crm/opportunities/${opp.id}`, { stage })
    opp.stage = res.data.stage
  } catch { toast.error(t('backoffice.crm.msg.oppStatusUpdateError')) }
}

onMounted(loadOpportunities)
</script>

<template>
  <div>
    <div class="flex justify-end mb-4">
      <AppButton size="sm" @click="showOpportunityForm = !showOpportunityForm">
        {{ showOpportunityForm ? t('backoffice.crm.cancel') : `+ ${t('backoffice.crm.newOpportunity')}` }}
      </AppButton>
    </div>

    <AppCard v-if="showOpportunityForm" class="mb-4">
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <select v-model="opportunityForm.customer_id" class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm sm:col-span-2">
          <option value="">{{ t('backoffice.crm.selectCustomerRequired') }}</option>
          <option v-for="c in customers" :key="c.id" :value="c.id">{{ c.full_name }}</option>
        </select>
        <input v-model="opportunityForm.title" type="text" :placeholder="t('backoffice.crm.opportunityTitleRequired')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm sm:col-span-2" />
        <select v-model="opportunityForm.product_type" class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
          <option v-for="(label, val) in productTypeLabels" :key="val" :value="val">{{ label }}</option>
        </select>
        <input v-model="opportunityForm.expected_value" type="number" min="0" step="0.01" :placeholder="t('backoffice.crm.expectedValue')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        <input v-model="opportunityForm.probability" type="number" min="0" max="100" :placeholder="t('backoffice.crm.probabilityPct')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        <input v-model="opportunityForm.expected_close" type="date" :placeholder="t('backoffice.crm.expectedCloseDate')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        <input v-model="opportunityForm.notes" type="text" :placeholder="t('backoffice.crm.notes')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm sm:col-span-2" />
      </div>
      <AppButton class="mt-3" size="sm" :loading="savingOpportunity" @click="createOpportunity">{{ t('backoffice.crm.saveOpportunity') }}</AppButton>
    </AppCard>

    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
    <div v-else class="space-y-3">
      <div v-for="opp in opportunities" :key="opp.id" class="bg-white dark:bg-surface rounded-2xl border border-stone-200 dark:border-border p-4 shadow-sm">
        <div class="flex items-center justify-between mb-2">
          <div>
            <span class="font-bold text-gray-900 dark:text-gray-100">{{ opp.title }}</span>
            <span class="text-xs text-gray-400 dark:text-gray-400 ms-2">{{ customerNameById[opp.customer_id] ?? t('backoffice.crm.customerHash', { id: opp.customer_id }) }}</span>
          </div>
          <AppBadge size="sm" :variant="oppStageConfig[opp.stage]?.variant ?? 'neutral'">
            {{ oppStageConfig[opp.stage]?.label ?? opp.stage }}
          </AppBadge>
        </div>
        <div class="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400 mb-3 flex-wrap">
          <span>{{ productTypeLabels[opp.product_type] ?? opp.product_type }}</span>
          <span>{{ t('backoffice.crm.expectedValueLabel') }}: {{ formatNumber(opp.expected_value) }} {{ t('backoffice.crm.egp') }}</span>
          <span>{{ t('backoffice.crm.probabilityLabel') }}: {{ opp.probability }}%</span>
          <span v-if="opp.expected_close">{{ t('backoffice.crm.expectedCloseLabel') }}: {{ fmtDate(opp.expected_close) }}</span>
          <span v-if="opp.lost_reason" class="text-red-600 dark:text-red-300">{{ t('backoffice.crm.lostReasonLabel') }}: {{ opp.lost_reason }}</span>
        </div>
        <div v-if="!['won','lost'].includes(opp.stage)" class="flex items-center gap-2 flex-wrap">
          <AppButton v-if="opp.stage === 'lead'" size="sm" @click="setOpportunityStage(opp, 'qualified')">{{ t('backoffice.crm.qualify') }}</AppButton>
          <AppButton v-if="opp.stage === 'qualified'" size="sm" @click="setOpportunityStage(opp, 'proposal')">{{ t('backoffice.crm.sendProposal') }}</AppButton>
          <AppButton v-if="opp.stage === 'proposal'" size="sm" @click="setOpportunityStage(opp, 'negotiation')">{{ t('backoffice.crm.negotiate') }}</AppButton>
          <AppButton v-if="['proposal','negotiation'].includes(opp.stage)" size="sm" @click="setOpportunityStage(opp, 'won')">{{ t('backoffice.crm.closeWon') }}</AppButton>
          <AppButton size="sm" variant="secondary" @click="openLostOpportunity(opp)">{{ t('backoffice.crm.markLost') }}</AppButton>
        </div>
        <div v-if="lostOpportunityId === opp.id" class="flex gap-2 mt-2 pt-2 border-t border-stone-100 dark:border-border/50">
          <input v-model="lostOpportunityReason" type="text" :placeholder="t('backoffice.crm.lostReasonRequiredField')"
            class="flex-1 border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <AppButton size="sm" variant="secondary" @click="confirmOpportunityLost">{{ t('backoffice.crm.confirm') }}</AppButton>
          <AppButton size="sm" variant="secondary" @click="lostOpportunityId = null">{{ t('backoffice.crm.cancel') }}</AppButton>
        </div>
      </div>
      <EmptyState v-if="opportunities.length === 0" icon="💼" :title="t('backoffice.crm.noOpportunities')" />
      <!-- Truncation warning -->
      <p
        v-if="opportunitiesTotal > opportunities.length"
        class="px-4 py-2 text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg"
      >
        ⚠️ {{ t('common.showingOf', { shown: opportunities.length, total: opportunitiesTotal }) }} — {{ t('common.useSearchToFilter') }}
      </p>
    </div>
  </div>
</template>
