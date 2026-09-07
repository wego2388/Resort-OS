<script setup lang="ts">
// الحملات التسويقية (Campaigns) — استُخرج من CRMView.vue (تقسيم الملفات
// الكبيرة، 2026-09-07).
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
interface Campaign {
  id: number; name: string; campaign_type: string; status: string
  start_date: string; end_date: string
  budget: number; revenue_attributed: number; leads_generated: number
}

const { t } = useI18n()
const { formatNumber } = useStaffFormat()
const toast = useToast()
const branchId = computed(() => props.branchId)

const loading = ref(false)
const campaigns = ref<Campaign[]>([])
const campaignsTotal = ref(0)

const showCampaignForm = ref(false)
const campaignForm = ref({ name: '', campaign_type: 'social_media', start_date: '', end_date: '', budget: '0' })
const savingCampaign = ref(false)

const campaignTypeLabels = computed<Record<string, string>>(() => ({
  social_media: t('backoffice.crm.campaignType.socialMedia'), email: t('backoffice.crm.campaignType.email'),
  sms: t('backoffice.crm.campaignType.sms'), event: t('backoffice.crm.campaignType.event'),
  referral: t('backoffice.crm.campaignType.referral'), other: t('backoffice.crm.campaignType.other'),
}))
const campaignStatusConfig = computed<Record<string, { label: string; variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }>>(() => ({
  planned:   { label: t('backoffice.crm.campaignStatus.planned'),   variant: 'neutral' },
  active:    { label: t('backoffice.crm.campaignStatus.active'),    variant: 'info' },
  completed: { label: t('backoffice.crm.campaignStatus.completed'), variant: 'success' },
  cancelled: { label: t('backoffice.crm.campaignStatus.cancelled'), variant: 'danger' },
}))

async function loadCampaigns() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/crm/campaigns', { params: { branch_id: branchId.value, size: 100 } })
    campaigns.value = res.data.items ?? res.data
    campaignsTotal.value = res.data.total ?? campaigns.value.length
  } catch { toast.error(t('backoffice.crm.msg.loadCampaignsError')) }
  finally { loading.value = false }
}

async function createCampaign() {
  if (!campaignForm.value.name || !campaignForm.value.start_date || !campaignForm.value.end_date) {
    toast.error(t('backoffice.crm.msg.campaignFieldsRequired')); return
  }
  savingCampaign.value = true
  try {
    await api.post('/api/v1/crm/campaigns', {
      branch_id: branchId.value,
      name: campaignForm.value.name,
      campaign_type: campaignForm.value.campaign_type,
      start_date: campaignForm.value.start_date,
      end_date: campaignForm.value.end_date,
      budget: campaignForm.value.budget,
    })
    toast.success(t('backoffice.crm.msg.campaignCreated'))
    showCampaignForm.value = false
    campaignForm.value = { name: '', campaign_type: 'social_media', start_date: '', end_date: '', budget: '0' }
    await loadCampaigns()
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.crm.msg.campaignCreateError'))
  } finally {
    savingCampaign.value = false
  }
}

async function setCampaignStatus(campaign: Campaign, status: string) {
  try {
    await api.patch(`/api/v1/crm/campaigns/${campaign.id}`, { status })
    campaign.status = status
  } catch { toast.error(t('backoffice.crm.msg.campaignStatusUpdateError')) }
}

onMounted(loadCampaigns)
</script>

<template>
  <div>
    <div class="flex justify-end mb-4">
      <AppButton size="sm" @click="showCampaignForm = !showCampaignForm">
        {{ showCampaignForm ? t('backoffice.crm.cancel') : `+ ${t('backoffice.crm.newCampaign')}` }}
      </AppButton>
    </div>

    <AppCard v-if="showCampaignForm" class="mb-4">
      <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <input v-model="campaignForm.name" type="text" :placeholder="t('backoffice.crm.campaignName')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm sm:col-span-2" />
        <select v-model="campaignForm.campaign_type" class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
          <option v-for="(label, val) in campaignTypeLabels" :key="val" :value="val">{{ label }}</option>
        </select>
        <input v-model="campaignForm.budget" type="number" min="0" step="0.01" :placeholder="t('backoffice.crm.budget')"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        <input v-model="campaignForm.start_date" type="date"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
        <input v-model="campaignForm.end_date" type="date"
          class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
      </div>
      <AppButton class="mt-3" size="sm" :loading="savingCampaign" @click="createCampaign">{{ t('backoffice.crm.saveCampaign') }}</AppButton>
    </AppCard>

    <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
    <div v-else class="space-y-3">
      <div v-for="c in campaigns" :key="c.id"
        class="bg-white dark:bg-surface rounded-2xl border border-stone-200 dark:border-border p-4 shadow-sm">
        <div class="flex items-center justify-between mb-2">
          <div>
            <span class="font-bold text-gray-900 dark:text-gray-100">{{ c.name }}</span>
            <span class="text-xs text-gray-400 dark:text-gray-400 ms-2">{{ campaignTypeLabels[c.campaign_type] ?? c.campaign_type }}</span>
          </div>
          <AppBadge size="sm" :variant="campaignStatusConfig[c.status]?.variant ?? 'neutral'">
            {{ campaignStatusConfig[c.status]?.label ?? c.status }}
          </AppBadge>
        </div>
        <div class="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400 mb-3">
          <span>{{ c.start_date }} → {{ c.end_date }}</span>
          <span>{{ t('backoffice.crm.budgetLabel') }}: {{ formatNumber(c.budget) }} {{ t('backoffice.crm.egp') }}</span>
          <span>{{ t('backoffice.crm.attributedRevenue') }}: {{ formatNumber(c.revenue_attributed) }} {{ t('backoffice.crm.egp') }}</span>
          <span>{{ t('backoffice.crm.leadsGenerated') }}: {{ c.leads_generated }}</span>
        </div>
        <div class="flex gap-2" v-if="!['completed', 'cancelled'].includes(c.status)">
          <AppButton v-if="c.status === 'planned'" size="sm" @click="setCampaignStatus(c, 'active')">{{ t('backoffice.crm.activate') }}</AppButton>
          <AppButton v-if="c.status === 'active'" size="sm" @click="setCampaignStatus(c, 'completed')">{{ t('backoffice.crm.finish') }}</AppButton>
          <AppButton size="sm" variant="secondary" @click="setCampaignStatus(c, 'cancelled')">{{ t('backoffice.crm.cancel') }}</AppButton>
        </div>
      </div>
      <EmptyState v-if="campaigns.length === 0" icon="📢" :title="t('backoffice.crm.noCampaigns')" />
      <!-- Truncation warning -->
      <p
        v-if="campaignsTotal > campaigns.length"
        class="px-4 py-2 text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg"
      >
        ⚠️ {{ t('common.showingOf', { shown: campaigns.length, total: campaignsTotal }) }} — {{ t('common.useSearchToFilter') }}
      </p>
    </div>
  </div>
</template>
