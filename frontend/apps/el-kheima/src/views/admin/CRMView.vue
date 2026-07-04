<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { api } from '@resort-os/core'
import { AppCard, AppBadge, AppButton, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const toast = useToast()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')
const tab = ref<'leads' | 'customers' | 'campaigns'>('leads')

interface Lead {
  id: number; full_name: string; phone?: string; interest: string
  stage: string; created_at: string; assigned_to?: number
}
interface Customer {
  id: number; full_name: string; phone?: string; segment: string
  total_spent: number; visits_count: number; vip_flag?: boolean
}
interface Campaign {
  id: number; name: string; campaign_type: string; status: string
  start_date: string; end_date: string
  budget: number; revenue_attributed: number; leads_generated: number
}

const leads = ref<Lead[]>([])
const customers = ref<Customer[]>([])
const campaigns = ref<Campaign[]>([])
const loading = ref(false)
const showCampaignForm = ref(false)
const campaignForm = ref({ name: '', campaign_type: 'social_media', start_date: '', end_date: '', budget: '0' })
const savingCampaign = ref(false)

const stageConfig: Record<string, { label: string; variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }> = {
  new:       { label: 'جديد',        variant: 'neutral' },
  contacted: { label: 'تم التواصل', variant: 'info' },
  qualified: { label: 'مؤهل',        variant: 'info' },
  proposal:  { label: 'عرض',         variant: 'warning' },
  won:       { label: 'مُغلق ✓',     variant: 'success' },
  lost:      { label: 'خسارة',       variant: 'danger' },
}

const interestLabels: Record<string, string> = {
  timeshare: 'تايم شير', leasing: 'إيجار', booking: 'حجز', membership: 'عضوية', other: 'أخرى'
}

const segmentVariants: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'neutral'> = {
  regular: 'neutral', vip: 'warning', corporate: 'info', travel_agent: 'info',
}

const campaignTypeLabels: Record<string, string> = {
  social_media: 'سوشيال ميديا', email: 'إيميل', sms: 'رسائل نصية',
  event: 'فعالية', referral: 'إحالة', other: 'أخرى',
}
const campaignStatusConfig: Record<string, { label: string; variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }> = {
  planned:   { label: 'مخطط لها', variant: 'neutral' },
  active:    { label: 'نشطة',     variant: 'info' },
  completed: { label: 'مكتملة',   variant: 'success' },
  cancelled: { label: 'ملغاة',    variant: 'danger' },
}

async function loadLeads() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/crm/leads', { params: { branch_id: branchId } })
    leads.value = res.data.leads ?? res.data.items ?? res.data
  } catch { toast.error('تعذّر تحميل العملاء المحتملين — حاول تاني') }
  finally { loading.value = false }
}

async function loadCustomers() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/crm/customers', { params: { branch_id: branchId } })
    customers.value = res.data.customers ?? res.data.items ?? res.data
  } catch { toast.error('تعذّر تحميل العملاء — حاول تاني') }
  finally { loading.value = false }
}

async function loadCampaigns() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/crm/campaigns', { params: { branch_id: branchId, size: 100 } })
    campaigns.value = res.data.items ?? res.data
  } catch { toast.error('تعذّر تحميل الحملات — حاول تاني') }
  finally { loading.value = false }
}

async function loadTab(t: typeof tab.value) {
  tab.value = t
  if (t === 'leads') await loadLeads()
  if (t === 'customers') await loadCustomers()
  if (t === 'campaigns') await loadCampaigns()
}

async function createCampaign() {
  if (!campaignForm.value.name || !campaignForm.value.start_date || !campaignForm.value.end_date) {
    toast.error('املأ الاسم وتاريخ البداية والنهاية'); return
  }
  savingCampaign.value = true
  try {
    await api.post('/api/v1/crm/campaigns', {
      branch_id: branchId,
      name: campaignForm.value.name,
      campaign_type: campaignForm.value.campaign_type,
      start_date: campaignForm.value.start_date,
      end_date: campaignForm.value.end_date,
      budget: campaignForm.value.budget,
    })
    toast.success('تم إنشاء الحملة')
    showCampaignForm.value = false
    campaignForm.value = { name: '', campaign_type: 'social_media', start_date: '', end_date: '', budget: '0' }
    await loadCampaigns()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر إنشاء الحملة')
  } finally {
    savingCampaign.value = false
  }
}

async function setCampaignStatus(campaign: Campaign, status: string) {
  try {
    await api.patch(`/api/v1/crm/campaigns/${campaign.id}`, { status })
    campaign.status = status
  } catch { toast.error('تعذّر تحديث حالة الحملة') }
}

async function advanceLead(lead: Lead) {
  const flow: Record<string, string> = { new: 'contacted', contacted: 'qualified', qualified: 'proposal', proposal: 'won' }
  const next = flow[lead.stage]
  if (!next) return
  try {
    await api.patch(`/api/v1/crm/leads/${lead.id}`, { stage: next })
    lead.stage = next
  } catch { toast.error('تعذّر تحديث حالة العميل المحتمل — حاول تاني') }
}

onMounted(loadLeads)
</script>

<template>
  <div dir="rtl">
    <h2 class="text-2xl font-black text-gray-900 mb-6">إدارة العملاء — CRM</h2>

    <div class="flex gap-1 bg-stone-100 p-1 rounded-xl mb-6 w-fit">
      <button v-for="t in [{ val: 'leads', label: 'العملاء المحتملون' }, { val: 'customers', label: 'العملاء' }, { val: 'campaigns', label: 'الحملات' }]"
        :key="t.val" @click="loadTab(t.val as any)"
        :class="['px-4 py-2 rounded-lg text-sm font-semibold transition-all', tab === t.val ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-700']"
      >{{ t.label }}</button>
    </div>

    <!-- Leads -->
    <div v-if="tab === 'leads'">
      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <div v-else class="space-y-3">
        <div v-for="lead in leads" :key="lead.id"
          class="bg-white rounded-2xl border border-stone-200 p-4 shadow-sm flex items-center justify-between">
          <div>
            <div class="flex items-center gap-2 mb-1">
              <span class="font-bold text-gray-900">{{ lead.full_name }}</span>
              <span v-if="lead.phone" class="text-xs text-gray-400">{{ lead.phone }}</span>
            </div>
            <div class="flex items-center gap-2 text-xs">
              <span class="px-2 py-0.5 bg-blue-50 text-blue-700 rounded-full">{{ interestLabels[lead.interest] ?? lead.interest }}</span>
              <span class="text-gray-400">{{ new Date(lead.created_at).toLocaleDateString('ar-EG') }}</span>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <AppBadge size="sm" :variant="stageConfig[lead.stage]?.variant ?? 'neutral'">
              {{ stageConfig[lead.stage]?.label ?? lead.stage }}
            </AppBadge>
            <AppButton v-if="!['won','lost'].includes(lead.stage)" size="sm" @click="advanceLead(lead)">
              تقدم ←
            </AppButton>
          </div>
        </div>
        <EmptyState v-if="leads.length === 0" icon="🤝" title="لا توجد عملاء محتملون" />
      </div>
    </div>

    <!-- Customers -->
    <div v-if="tab === 'customers'">
      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <AppCard v-else padding="none">
        <table class="w-full">
          <thead class="bg-stone-50">
            <tr>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">العميل</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الشريحة</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الزيارات</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">إجمالي الإنفاق</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in customers" :key="c.id" class="border-t border-stone-100 hover:bg-stone-50">
              <td class="px-4 py-3">
                <div class="flex items-center gap-2">
                  <span v-if="c.vip_flag" class="text-amber-500 text-sm">⭐</span>
                  <div>
                    <div class="font-medium text-gray-900 text-sm">{{ c.full_name }}</div>
                    <div v-if="c.phone" class="text-xs text-gray-400">{{ c.phone }}</div>
                  </div>
                </div>
              </td>
              <td class="px-4 py-3">
                <AppBadge size="sm" :variant="segmentVariants[c.segment] ?? 'neutral'">
                  {{ c.segment === 'vip' ? 'VIP' : c.segment === 'corporate' ? 'شركة' : c.segment === 'travel_agent' ? 'وكيل سفر' : 'عادي' }}
                </AppBadge>
              </td>
              <td class="px-4 py-3 text-sm text-gray-700 font-medium">{{ c.visits_count }}</td>
              <td class="px-4 py-3 text-sm font-bold text-blue-700">{{ Number(c.total_spent).toLocaleString('ar-EG') }} ج</td>
            </tr>
            <tr v-if="customers.length === 0">
              <td colspan="4" class="px-4 py-8">
                <EmptyState icon="👥" title="لا توجد عملاء" />
              </td>
            </tr>
          </tbody>
        </table>
      </AppCard>
    </div>

    <!-- Campaigns -->
    <div v-if="tab === 'campaigns'">
      <div class="flex justify-end mb-4">
        <AppButton size="sm" @click="showCampaignForm = !showCampaignForm">
          {{ showCampaignForm ? 'إلغاء' : '+ حملة جديدة' }}
        </AppButton>
      </div>

      <AppCard v-if="showCampaignForm" class="mb-4">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <input v-model="campaignForm.name" type="text" placeholder="اسم الحملة"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm sm:col-span-2" />
          <select v-model="campaignForm.campaign_type" class="border border-stone-200 rounded-xl px-3 py-2 text-sm">
            <option v-for="(label, val) in campaignTypeLabels" :key="val" :value="val">{{ label }}</option>
          </select>
          <input v-model="campaignForm.budget" type="number" min="0" step="0.01" placeholder="الميزانية"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <input v-model="campaignForm.start_date" type="date"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <input v-model="campaignForm.end_date" type="date"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
        </div>
        <AppButton class="mt-3" size="sm" :loading="savingCampaign" @click="createCampaign">حفظ الحملة</AppButton>
      </AppCard>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <div v-else class="space-y-3">
        <div v-for="c in campaigns" :key="c.id"
          class="bg-white rounded-2xl border border-stone-200 p-4 shadow-sm">
          <div class="flex items-center justify-between mb-2">
            <div>
              <span class="font-bold text-gray-900">{{ c.name }}</span>
              <span class="text-xs text-gray-400 mr-2">{{ campaignTypeLabels[c.campaign_type] ?? c.campaign_type }}</span>
            </div>
            <AppBadge size="sm" :variant="campaignStatusConfig[c.status]?.variant ?? 'neutral'">
              {{ campaignStatusConfig[c.status]?.label ?? c.status }}
            </AppBadge>
          </div>
          <div class="flex items-center gap-4 text-xs text-gray-500 mb-3">
            <span>{{ c.start_date }} → {{ c.end_date }}</span>
            <span>ميزانية: {{ Number(c.budget).toLocaleString('ar-EG') }} ج</span>
            <span>إيراد منسوب: {{ Number(c.revenue_attributed).toLocaleString('ar-EG') }} ج</span>
            <span>عملاء محتملون: {{ c.leads_generated }}</span>
          </div>
          <div class="flex gap-2" v-if="!['completed', 'cancelled'].includes(c.status)">
            <AppButton v-if="c.status === 'planned'" size="sm" @click="setCampaignStatus(c, 'active')">تفعيل</AppButton>
            <AppButton v-if="c.status === 'active'" size="sm" @click="setCampaignStatus(c, 'completed')">إنهاء</AppButton>
            <AppButton size="sm" variant="secondary" @click="setCampaignStatus(c, 'cancelled')">إلغاء</AppButton>
          </div>
        </div>
        <EmptyState v-if="campaigns.length === 0" icon="📢" title="لا توجد حملات تسويقية" />
      </div>
    </div>
  </div>
</template>
