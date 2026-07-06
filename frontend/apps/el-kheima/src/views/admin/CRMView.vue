<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, parseApiTimestamp } from '@resort-os/core'
import { AppCard, AppBadge, AppButton, AppModal, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const toast = useToast()
const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')
const tab = ref<'leads' | 'customers' | 'campaigns' | 'guests'>('leads')

interface LeadSource { id: number; name: string; is_active: boolean }
interface Lead {
  id: number; full_name: string; phone?: string; email?: string; nationality?: string
  interest: string; stage: string; created_at: string; assigned_to?: number
  source_id?: number | null; expected_value: number; notes?: string
  lost_reason?: string | null
}
interface CallNote {
  id: number; lead_id: number; direction: string; duration_min?: number | null
  summary: string; outcome: string; callback_at?: string | null
  called_by: number; called_at: string
}
interface Customer {
  id: number; full_name: string; phone?: string; email?: string; segment: string
  total_spent: number; visits_count: number; vip_flag?: boolean; blacklisted: boolean
}
interface Campaign {
  id: number; name: string; campaign_type: string; status: string
  start_date: string; end_date: string
  budget: number; revenue_attributed: number; leads_generated: number
}
interface GuestProfile {
  id: number; full_name: string; phone: string; email?: string; nationality?: string
  total_visits: number; avg_spend: number; vip_flag: boolean; last_stay?: string | null
}

// ── Leads ────────────────────────────────────────────────────────────────
const leads = ref<Lead[]>([])
const leadSources = ref<LeadSource[]>([])
const customers = ref<Customer[]>([])
const campaigns = ref<Campaign[]>([])
const guestProfiles = ref<GuestProfile[]>([])
const guestVipOnly = ref(false)
const loading = ref(false)

const showLeadForm = ref(false)
const savingLead = ref(false)
const leadForm = ref({
  full_name: '', phone: '', email: '', nationality: '',
  source_id: '' as number | '', interest: 'other', expected_value: '0', notes: '',
})

const showCustomerForm = ref(false)
const savingCustomer = ref(false)
const customerForm = ref({
  full_name: '', phone: '', email: '', nationality: '', segment: 'regular', notes: '',
})

const showCampaignForm = ref(false)
const campaignForm = ref({ name: '', campaign_type: 'social_media', start_date: '', end_date: '', budget: '0' })
const savingCampaign = ref(false)

// ── Lead detail drawer (call notes + edit) ──────────────────────────────
const selectedLead = ref<Lead | null>(null)
const callNotes = ref<CallNote[]>([])
const loadingNotes = ref(false)
const savingCallNote = ref(false)
const callNoteForm = ref({ direction: 'outbound', duration_min: '', summary: '', outcome: 'no_decision' })
const editLeadForm = ref({ phone: '', source_id: '' as number | '', notes: '' })
const savingLeadEdit = ref(false)
const lostReason = ref('')
const savingLost = ref(false)

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

const outcomeLabels: Record<string, string> = {
  interested: 'مهتم', not_interested: 'غير مهتم', callback: 'يتواصل لاحقًا',
  no_decision: 'بدون قرار', appointment_set: 'تم تحديد موعد',
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

const sourceNameById = computed<Record<number, string>>(() => {
  const map: Record<number, string> = {}
  for (const s of leadSources.value) map[s.id] = s.name
  return map
})

function fmtDate(d?: string | null) {
  if (!d) return '—'
  try { return parseApiTimestamp(d).toLocaleDateString('ar-EG') } catch { return d }
}
function fmtDateTime(d?: string | null) {
  if (!d) return '—'
  try { return parseApiTimestamp(d).toLocaleString('ar-EG') } catch { return d }
}

async function loadLeadSources() {
  try {
    const res = await api.get('/api/v1/crm/lead-sources', { params: { branch_id: branchId, active_only: false } })
    leadSources.value = res.data
  } catch { /* المصادر مش حرجة لعرض القائمة نفسها */ }
}

async function loadLeads() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/crm/leads', { params: { branch_id: branchId } })
    leads.value = res.data.leads ?? res.data.items ?? res.data
    if (leadSources.value.length === 0) await loadLeadSources()
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

async function loadGuestProfiles() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/crm/guest-profiles', { params: { branch_id: branchId, vip_only: guestVipOnly.value } })
    guestProfiles.value = res.data
  } catch { toast.error('تعذّر تحميل ملفات الضيوف — حاول تاني') }
  finally { loading.value = false }
}

async function loadTab(t: typeof tab.value) {
  tab.value = t
  if (t === 'leads') await loadLeads()
  if (t === 'customers') await loadCustomers()
  if (t === 'campaigns') await loadCampaigns()
  if (t === 'guests') await loadGuestProfiles()
}

// ── Leads: create ────────────────────────────────────────────────────────
async function createLead() {
  if (!leadForm.value.full_name) { toast.error('اسم العميل المحتمل مطلوب'); return }
  savingLead.value = true
  try {
    await api.post('/api/v1/crm/leads', {
      branch_id: branchId,
      full_name: leadForm.value.full_name,
      phone: leadForm.value.phone || undefined,
      email: leadForm.value.email || undefined,
      nationality: leadForm.value.nationality || undefined,
      source_id: leadForm.value.source_id || undefined,
      interest: leadForm.value.interest,
      expected_value: leadForm.value.expected_value || '0',
      notes: leadForm.value.notes || undefined,
    })
    toast.success('تم إضافة العميل المحتمل')
    showLeadForm.value = false
    leadForm.value = { full_name: '', phone: '', email: '', nationality: '', source_id: '', interest: 'other', expected_value: '0', notes: '' }
    await loadLeads()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر إضافة العميل المحتمل')
  } finally {
    savingLead.value = false
  }
}

async function advanceLead(lead: Lead) {
  const flow: Record<string, string> = { new: 'contacted', contacted: 'qualified', qualified: 'proposal', proposal: 'won' }
  const next = flow[lead.stage]
  if (!next) return
  try {
    await api.patch(`/api/v1/crm/leads/${lead.id}`, { stage: next })
    lead.stage = next
    if (selectedLead.value?.id === lead.id) selectedLead.value.stage = next
  } catch { toast.error('تعذّر تحديث حالة العميل المحتمل — حاول تاني') }
}

// ── Lead detail drawer ───────────────────────────────────────────────────
async function openLeadDetail(lead: Lead) {
  selectedLead.value = lead
  editLeadForm.value = { phone: lead.phone ?? '', source_id: lead.source_id ?? '', notes: lead.notes ?? '' }
  lostReason.value = ''
  callNoteForm.value = { direction: 'outbound', duration_min: '', summary: '', outcome: 'no_decision' }
  await loadCallNotes(lead.id)
}

function closeLeadDetail() {
  selectedLead.value = null
  callNotes.value = []
}

async function loadCallNotes(leadId: number) {
  loadingNotes.value = true
  try {
    const res = await api.get(`/api/v1/crm/leads/${leadId}/call-notes`)
    callNotes.value = res.data
  } catch { toast.error('تعذّر تحميل سجل المكالمات') }
  finally { loadingNotes.value = false }
}

async function addCallNote() {
  if (!selectedLead.value) return
  if (!callNoteForm.value.summary || callNoteForm.value.summary.trim().length < 3) {
    toast.error('ملخص المكالمة لازم يكون 3 أحرف على الأقل'); return
  }
  savingCallNote.value = true
  try {
    await api.post(`/api/v1/crm/leads/${selectedLead.value.id}/call-notes`, {
      branch_id: branchId,
      lead_id: selectedLead.value.id,
      direction: callNoteForm.value.direction,
      duration_min: callNoteForm.value.duration_min ? Number(callNoteForm.value.duration_min) : undefined,
      summary: callNoteForm.value.summary,
      outcome: callNoteForm.value.outcome,
    })
    toast.success('تم تسجيل ملاحظة المكالمة')
    callNoteForm.value = { direction: 'outbound', duration_min: '', summary: '', outcome: 'no_decision' }
    await loadCallNotes(selectedLead.value.id)
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر تسجيل ملاحظة المكالمة')
  } finally {
    savingCallNote.value = false
  }
}

async function saveLeadDetails() {
  if (!selectedLead.value) return
  savingLeadEdit.value = true
  try {
    const res = await api.patch(`/api/v1/crm/leads/${selectedLead.value.id}/details`, {
      phone: editLeadForm.value.phone || undefined,
      source_id: editLeadForm.value.source_id || undefined,
      notes: editLeadForm.value.notes || undefined,
    })
    toast.success('تم حفظ التعديلات')
    Object.assign(selectedLead.value, res.data)
    const idx = leads.value.findIndex(l => l.id === selectedLead.value!.id)
    if (idx !== -1) leads.value[idx] = { ...leads.value[idx], ...res.data }
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر حفظ التعديلات')
  } finally {
    savingLeadEdit.value = false
  }
}

async function markLeadLost() {
  if (!selectedLead.value) return
  if (!lostReason.value || lostReason.value.trim().length < 1) {
    toast.error('اكتب سبب الخسارة أولًا'); return
  }
  savingLost.value = true
  try {
    const res = await api.patch(`/api/v1/crm/leads/${selectedLead.value.id}`, {
      stage: 'lost', lost_reason: lostReason.value,
    })
    toast.success('تم وسم العميل المحتمل كخسارة')
    Object.assign(selectedLead.value, res.data)
    const idx = leads.value.findIndex(l => l.id === selectedLead.value!.id)
    if (idx !== -1) leads.value[idx] = { ...leads.value[idx], ...res.data }
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر تحديث حالة العميل المحتمل')
  } finally {
    savingLost.value = false
  }
}

// ── Customers: create ────────────────────────────────────────────────────
async function createCustomer() {
  if (!customerForm.value.full_name) { toast.error('اسم العميل مطلوب'); return }
  savingCustomer.value = true
  try {
    await api.post('/api/v1/crm/customers', {
      branch_id: branchId,
      full_name: customerForm.value.full_name,
      phone: customerForm.value.phone || undefined,
      email: customerForm.value.email || undefined,
      nationality: customerForm.value.nationality || undefined,
      segment: customerForm.value.segment,
      source: 'walk_in',
      notes: customerForm.value.notes || undefined,
    })
    toast.success('تم إضافة العميل')
    showCustomerForm.value = false
    customerForm.value = { full_name: '', phone: '', email: '', nationality: '', segment: 'regular', notes: '' }
    await loadCustomers()
  } catch (e: any) {
    // رسالة الباك إند بتوضّح اسم/رقم العميل المكرر فعليًا — نعرضها زي ما هي
    toast.error(e?.response?.data?.detail ?? 'تعذّر إضافة العميل')
  } finally {
    savingCustomer.value = false
  }
}

// ── Campaigns ────────────────────────────────────────────────────────────
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

onMounted(loadLeads)
</script>

<template>
  <div dir="rtl">
    <h2 class="text-2xl font-black text-gray-900 mb-6">إدارة العملاء — CRM</h2>

    <div class="flex items-center justify-between mb-6 flex-wrap gap-3">
      <div class="flex gap-1 bg-stone-100 p-1 rounded-xl w-fit">
        <button v-for="t in [{ val: 'leads', label: 'العملاء المحتملون' }, { val: 'customers', label: 'العملاء' }, { val: 'campaigns', label: 'الحملات' }, { val: 'guests', label: 'ملفات الضيوف' }]"
          :key="t.val" @click="loadTab(t.val as any)"
          :class="['px-4 py-2 rounded-lg text-sm font-semibold transition-all', tab === t.val ? 'bg-white shadow-sm text-gray-900' : 'text-gray-500 hover:text-gray-700']"
        >{{ t.label }}</button>
      </div>
      <AppButton v-if="tab === 'leads'" size="sm" @click="showLeadForm = !showLeadForm">
        {{ showLeadForm ? 'إلغاء' : '+ عميل محتمل جديد' }}
      </AppButton>
      <AppButton v-if="tab === 'customers'" size="sm" @click="showCustomerForm = !showCustomerForm">
        {{ showCustomerForm ? 'إلغاء' : '+ عميل جديد' }}
      </AppButton>
      <AppButton v-if="tab === 'campaigns'" size="sm" @click="showCampaignForm = !showCampaignForm">
        {{ showCampaignForm ? 'إلغاء' : '+ حملة جديدة' }}
      </AppButton>
    </div>

    <!-- Leads -->
    <div v-if="tab === 'leads'">
      <AppCard v-if="showLeadForm" class="mb-4">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <input v-model="leadForm.full_name" type="text" placeholder="الاسم الكامل *"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm sm:col-span-2" />
          <input v-model="leadForm.phone" type="text" placeholder="رقم الهاتف"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <input v-model="leadForm.email" type="email" placeholder="البريد الإلكتروني"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <select v-model="leadForm.source_id" class="border border-stone-200 rounded-xl px-3 py-2 text-sm">
            <option value="">مصدر العميل المحتمل (اختياري)</option>
            <option v-for="s in leadSources" :key="s.id" :value="s.id">{{ s.name }}{{ !s.is_active ? ' (متوقف)' : '' }}</option>
          </select>
          <select v-model="leadForm.interest" class="border border-stone-200 rounded-xl px-3 py-2 text-sm">
            <option v-for="(label, val) in interestLabels" :key="val" :value="val">{{ label }}</option>
          </select>
          <input v-model="leadForm.expected_value" type="number" min="0" step="0.01" placeholder="القيمة المتوقعة"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <input v-model="leadForm.notes" type="text" placeholder="ملاحظات"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm sm:col-span-2" />
        </div>
        <AppButton class="mt-3" size="sm" :loading="savingLead" @click="createLead">حفظ العميل المحتمل</AppButton>
      </AppCard>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <div v-else class="space-y-3">
        <div v-for="lead in leads" :key="lead.id"
          class="bg-white rounded-2xl border border-stone-200 p-4 shadow-sm flex items-center justify-between cursor-pointer hover:border-blue-300"
          @click="openLeadDetail(lead)">
          <div>
            <div class="flex items-center gap-2 mb-1">
              <span class="font-bold text-gray-900">{{ lead.full_name }}</span>
              <span v-if="lead.phone" class="text-xs text-gray-400">{{ lead.phone }}</span>
            </div>
            <div class="flex items-center gap-2 text-xs flex-wrap">
              <span class="px-2 py-0.5 bg-blue-50 text-blue-700 rounded-full">{{ interestLabels[lead.interest] ?? lead.interest }}</span>
              <span v-if="lead.source_id" class="px-2 py-0.5 bg-stone-100 text-gray-600 rounded-full">{{ sourceNameById[lead.source_id] ?? `مصدر #${lead.source_id}` }}</span>
              <span v-else class="px-2 py-0.5 bg-stone-100 text-gray-400 rounded-full">بدون مصدر</span>
              <span class="text-gray-400">{{ fmtDate(lead.created_at) }}</span>
            </div>
          </div>
          <div class="flex items-center gap-2" @click.stop>
            <AppBadge size="sm" :variant="stageConfig[lead.stage]?.variant ?? 'neutral'">
              {{ stageConfig[lead.stage]?.label ?? lead.stage }}
            </AppBadge>
            <AppButton v-if="!['won','lost'].includes(lead.stage)" size="sm" @click="advanceLead(lead)">
              تقدم ←
            </AppButton>
            <AppButton size="sm" variant="secondary" @click="openLeadDetail(lead)">تفاصيل</AppButton>
          </div>
        </div>
        <EmptyState v-if="leads.length === 0" icon="🤝" title="لا توجد عملاء محتملون" />
      </div>
    </div>

    <!-- Customers -->
    <div v-if="tab === 'customers'">
      <AppCard v-if="showCustomerForm" class="mb-4">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <input v-model="customerForm.full_name" type="text" placeholder="الاسم الكامل *"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm sm:col-span-2" />
          <input v-model="customerForm.phone" type="text" placeholder="رقم الهاتف"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <input v-model="customerForm.email" type="email" placeholder="البريد الإلكتروني"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <select v-model="customerForm.segment" class="border border-stone-200 rounded-xl px-3 py-2 text-sm">
            <option value="regular">عادي</option>
            <option value="vip">VIP</option>
            <option value="corporate">شركة</option>
            <option value="travel_agent">وكيل سفر</option>
          </select>
          <input v-model="customerForm.nationality" type="text" placeholder="الجنسية"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
          <input v-model="customerForm.notes" type="text" placeholder="ملاحظات"
            class="border border-stone-200 rounded-xl px-3 py-2 text-sm sm:col-span-2" />
        </div>
        <AppButton class="mt-3" size="sm" :loading="savingCustomer" @click="createCustomer">حفظ العميل</AppButton>
      </AppCard>

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
                    <div class="font-medium text-gray-900 text-sm flex items-center gap-1">
                      {{ c.full_name }}
                      <AppBadge v-if="c.blacklisted" size="sm" variant="danger">قائمة سوداء</AppBadge>
                    </div>
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

    <!-- Guest Profiles (PMS checkout integration — read-only) -->
    <div v-if="tab === 'guests'">
      <p class="text-xs text-gray-500 mb-3">
        بتتحدّث أوتوماتيك من عملية تسجيل مغادرة (checkout) حقيقية في الفندق — مفيش إدخال يدوي هنا.
      </p>
      <div class="flex justify-end mb-3">
        <label class="flex items-center gap-2 text-sm text-gray-600">
          <input type="checkbox" v-model="guestVipOnly" @change="loadGuestProfiles" />
          VIP فقط
        </label>
      </div>
      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <AppCard v-else padding="none">
        <table class="w-full">
          <thead class="bg-stone-50">
            <tr>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">الضيف</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">عدد الزيارات</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">متوسط الإنفاق</th>
              <th class="px-4 py-3 text-right text-xs font-semibold text-gray-500 uppercase">آخر إقامة</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="g in guestProfiles" :key="g.id" class="border-t border-stone-100 hover:bg-stone-50">
              <td class="px-4 py-3">
                <div class="flex items-center gap-2">
                  <span v-if="g.vip_flag" class="text-amber-500 text-sm">⭐</span>
                  <div>
                    <div class="font-medium text-gray-900 text-sm">{{ g.full_name }}</div>
                    <div class="text-xs text-gray-400">{{ g.phone }}</div>
                  </div>
                </div>
              </td>
              <td class="px-4 py-3 text-sm text-gray-700 font-medium">{{ g.total_visits }}</td>
              <td class="px-4 py-3 text-sm font-bold text-blue-700">{{ Number(g.avg_spend).toLocaleString('ar-EG') }} ج</td>
              <td class="px-4 py-3 text-sm text-gray-600">{{ fmtDate(g.last_stay) }}</td>
            </tr>
            <tr v-if="guestProfiles.length === 0">
              <td colspan="4" class="px-4 py-8">
                <EmptyState icon="🏨" title="لا توجد ملفات ضيوف بعد" subtitle="هتتعمل أوتوماتيك أول ما ضيف يسجّل مغادرة من الفندق" />
              </td>
            </tr>
          </tbody>
        </table>
      </AppCard>
    </div>

    <!-- Campaigns -->
    <div v-if="tab === 'campaigns'">
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

    <!-- Lead detail modal — call notes history + inline edit + mark lost -->
    <AppModal :open="!!selectedLead" :title="selectedLead?.full_name" size="lg" @close="closeLeadDetail">
      <div v-if="selectedLead" class="space-y-6">
        <div class="flex items-center gap-2 flex-wrap">
          <AppBadge size="sm" :variant="stageConfig[selectedLead.stage]?.variant ?? 'neutral'">
            {{ stageConfig[selectedLead.stage]?.label ?? selectedLead.stage }}
          </AppBadge>
          <span class="text-xs text-gray-400">أُنشئ في {{ fmtDate(selectedLead.created_at) }}</span>
          <span v-if="selectedLead.lost_reason" class="text-xs text-red-600">سبب الخسارة: {{ selectedLead.lost_reason }}</span>
        </div>

        <!-- تعديل بيانات أساسية -->
        <div>
          <h3 class="text-sm font-bold text-gray-700 mb-2">تعديل بيانات العميل المحتمل</h3>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <input v-model="editLeadForm.phone" type="text" placeholder="رقم الهاتف"
              class="border border-stone-200 rounded-xl px-3 py-2 text-sm" />
            <select v-model="editLeadForm.source_id" class="border border-stone-200 rounded-xl px-3 py-2 text-sm">
              <option value="">بدون مصدر</option>
              <option v-for="s in leadSources" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
            <input v-model="editLeadForm.notes" type="text" placeholder="ملاحظات"
              class="border border-stone-200 rounded-xl px-3 py-2 text-sm sm:col-span-2" />
          </div>
          <AppButton class="mt-2" size="sm" variant="secondary" :loading="savingLeadEdit" @click="saveLeadDetails">
            حفظ التعديلات
          </AppButton>
        </div>

        <!-- سجل المكالمات -->
        <div>
          <h3 class="text-sm font-bold text-gray-700 mb-2">سجل المكالمات</h3>
          <div v-if="loadingNotes" class="flex justify-center py-6"><AppSpinner /></div>
          <div v-else class="space-y-2 mb-3">
            <div v-for="n in callNotes" :key="n.id" class="bg-stone-50 rounded-xl p-3 text-sm">
              <div class="flex items-center justify-between mb-1">
                <span class="font-medium text-gray-800">{{ n.direction === 'inbound' ? 'مكالمة واردة' : 'مكالمة صادرة' }}</span>
                <span class="text-xs text-gray-400">{{ fmtDateTime(n.called_at) }}</span>
              </div>
              <p class="text-gray-600">{{ n.summary }}</p>
              <div class="flex items-center gap-2 mt-1">
                <AppBadge size="sm" variant="info">{{ outcomeLabels[n.outcome] ?? n.outcome }}</AppBadge>
                <span v-if="n.duration_min" class="text-xs text-gray-400">{{ n.duration_min }} دقيقة</span>
              </div>
            </div>
            <EmptyState v-if="callNotes.length === 0" icon="📞" title="لا توجد مكالمات مسجّلة بعد" />
          </div>

          <div class="border-t border-stone-100 pt-3 space-y-2">
            <div class="grid grid-cols-2 gap-2">
              <select v-model="callNoteForm.direction" class="border border-stone-200 rounded-xl px-3 py-2 text-sm">
                <option value="outbound">مكالمة صادرة</option>
                <option value="inbound">مكالمة واردة</option>
              </select>
              <select v-model="callNoteForm.outcome" class="border border-stone-200 rounded-xl px-3 py-2 text-sm">
                <option v-for="(label, val) in outcomeLabels" :key="val" :value="val">{{ label }}</option>
              </select>
            </div>
            <textarea v-model="callNoteForm.summary" rows="2" placeholder="ملخص المكالمة (3 أحرف على الأقل) *"
              class="w-full border border-stone-200 rounded-xl px-3 py-2 text-sm" />
            <input v-model="callNoteForm.duration_min" type="number" min="0" placeholder="مدة المكالمة (دقيقة)"
              class="border border-stone-200 rounded-xl px-3 py-2 text-sm w-40" />
            <AppButton size="sm" :loading="savingCallNote" @click="addCallNote">+ تسجيل ملاحظة مكالمة</AppButton>
          </div>
        </div>

        <!-- وسم كخسارة -->
        <div v-if="!['won','lost'].includes(selectedLead.stage)" class="border-t border-stone-100 pt-4">
          <h3 class="text-sm font-bold text-gray-700 mb-2">وسم كخسارة</h3>
          <div class="flex gap-2">
            <input v-model="lostReason" type="text" placeholder="سبب الخسارة (مطلوب)"
              class="flex-1 border border-stone-200 rounded-xl px-3 py-2 text-sm" />
            <AppButton size="sm" variant="secondary" :loading="savingLost" @click="markLeadLost">خسارة</AppButton>
          </div>
        </div>
      </div>
    </AppModal>
  </div>
</template>
