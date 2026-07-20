<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, parseApiTimestamp, useAuthStore, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, AppModal, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const { t } = useI18n()
const { formatNumber, formatDate: fmtDateFn, formatDateTime: fmtDateTimeFn } = useStaffFormat()
const toast = useToast()
const authStore = useAuthStore()
const auth = useAuthStore()
const branchId = auth.branchId
const tab = ref<'leads' | 'customers' | 'opportunities' | 'activities' | 'campaigns' | 'guests' | 'loyalty'>('leads')

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
  customer_group_id?: number | null
}
interface CustomerGroup {
  id: number; name: string; name_ar?: string | null; discount_percentage: number; is_active: boolean
}
interface Opportunity {
  id: number; customer_id: number; title: string; product_type: string; stage: string
  expected_value: number; probability: number; assigned_to?: number | null
  expected_close?: string | null; closed_at?: string | null
  lost_reason?: string | null; notes?: string | null; created_at: string
}
interface Activity {
  id: number; customer_id: number; activity_type: string; title: string
  due_date: string; due_time?: string | null; assigned_to?: number | null
  status: string; done_at?: string | null; notes?: string | null; created_at: string
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
const opportunities = ref<Opportunity[]>([])
const activities = ref<Activity[]>([])
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

// ── مجموعات العملاء (خصم دائم) ──────────────────────────────────────────
// قراءة لمدير+، إنشاء/تعديل لـ admin+ فقط — نفس نمط /finance/discounts.
const groups = ref<CustomerGroup[]>([])
const groupModal = ref(false)
const savingGroup = ref(false)
const editingGroup = ref<CustomerGroup | null>(null)
const groupForm = ref({ name: '', name_ar: '', discount_percentage: '10' })

function openCreateGroup() {
  editingGroup.value = null
  groupForm.value = { name: '', name_ar: '', discount_percentage: '10' }
}
function openEditGroup(g: CustomerGroup) {
  editingGroup.value = g
  groupForm.value = { name: g.name, name_ar: g.name_ar ?? '', discount_percentage: String(g.discount_percentage) }
}

const showOpportunityForm = ref(false)
const savingOpportunity = ref(false)
const opportunityForm = ref({
  customer_id: '' as number | '', title: '', product_type: 'other',
  expected_value: '0', probability: '20', expected_close: '', notes: '',
})

const showActivityForm = ref(false)
const savingActivity = ref(false)
const activityForm = ref({
  customer_id: '' as number | '', activity_type: 'follow_up', title: '',
  due_date: '', due_time: '', notes: '',
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

// كل الـobjects دي computed (مش constants) عشان تعيد الحساب لو اللغة اتغيّرت.
const stageConfig = computed<Record<string, { label: string; variant: 'success' | 'warning' | 'danger' | 'info' | 'neutral' }>>(() => ({
  new:       { label: t('backoffice.crm.leadStages.new'),       variant: 'neutral' },
  contacted: { label: t('backoffice.crm.leadStages.contacted'), variant: 'info' },
  qualified: { label: t('backoffice.crm.leadStages.qualified'), variant: 'info' },
  proposal:  { label: t('backoffice.crm.leadStages.proposal'),  variant: 'warning' },
  won:       { label: t('backoffice.crm.leadStages.won'),       variant: 'success' },
  lost:      { label: t('backoffice.crm.leadStages.lost'),      variant: 'danger' },
}))

const interestLabels = computed<Record<string, string>>(() => ({
  timeshare: t('backoffice.crm.interest.timeshare'), leasing: t('backoffice.crm.interest.leasing'),
  booking: t('backoffice.crm.interest.booking'), membership: t('backoffice.crm.interest.membership'),
  other: t('backoffice.crm.interest.other'),
}))

const outcomeLabels = computed<Record<string, string>>(() => ({
  interested: t('backoffice.crm.outcome.interested'), not_interested: t('backoffice.crm.outcome.notInterested'),
  callback: t('backoffice.crm.outcome.callback'), no_decision: t('backoffice.crm.outcome.noDecision'),
  appointment_set: t('backoffice.crm.outcome.appointmentSet'),
}))

const segmentVariants: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'neutral'> = {
  regular: 'neutral', vip: 'warning', corporate: 'info', travel_agent: 'info',
}
const segmentLabels = computed<Record<string, string>>(() => ({
  regular: t('backoffice.crm.segment.regular'), vip: t('backoffice.crm.segment.vip'),
  corporate: t('backoffice.crm.segment.corporate'), travel_agent: t('backoffice.crm.segment.travelAgent'),
}))

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

const tabsList = computed(() => [
  { val: 'leads', label: t('backoffice.crm.tabs.leads') },
  { val: 'customers', label: t('backoffice.crm.tabs.customers') },
  { val: 'opportunities', label: t('backoffice.crm.tabs.opportunities') },
  { val: 'activities', label: t('backoffice.crm.tabs.activities') },
  { val: 'campaigns', label: t('backoffice.crm.tabs.campaigns') },
  { val: 'guests', label: t('backoffice.crm.tabs.guests') },
  { val: 'loyalty', label: `🎁 ${t('backoffice.crm.tabs.loyalty')}` },
])

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

const sourceNameById = computed<Record<number, string>>(() => {
  const map: Record<number, string> = {}
  for (const s of leadSources.value) map[s.id] = s.name
  return map
})

function fmtDate(d?: string | null) {
  if (!d) return '—'
  try { return fmtDateFn(parseApiTimestamp(d)) } catch { return d }
}
function fmtDateTime(d?: string | null) {
  if (!d) return '—'
  try { return fmtDateTimeFn(parseApiTimestamp(d)) } catch { return d }
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
  } catch { toast.error(t('backoffice.crm.msg.loadLeadsError')) }
  finally { loading.value = false }
}

async function loadCustomers() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/crm/customers', { params: { branch_id: branchId } })
    customers.value = res.data.customers ?? res.data.items ?? res.data
    if (authStore.roleLevel >= 60) await loadGroups()
  } catch { toast.error(t('backoffice.crm.msg.loadCustomersError')) }
  finally { loading.value = false }
}

async function loadGroups() {
  try {
    const res = await api.get('/api/v1/crm/customer-groups', { params: { branch_id: branchId, active_only: false } })
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
    }
    if (editingGroup.value) {
      await api.patch(`/api/v1/crm/customer-groups/${editingGroup.value.id}`, payload)
      toast.success(t('backoffice.crm.msg.groupUpdated'))
    } else {
      await api.post('/api/v1/crm/customer-groups', { branch_id: branchId, ...payload })
      toast.success(t('backoffice.crm.msg.groupAdded'))
    }
    openCreateGroup()
    await loadGroups()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.crm.msg.groupSaveError'))
  } finally {
    savingGroup.value = false
  }
}

async function toggleGroupActive(g: CustomerGroup) {
  try {
    await api.patch(`/api/v1/crm/customer-groups/${g.id}`, { is_active: !g.is_active })
    await loadGroups()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.crm.msg.groupStatusUpdateError'))
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
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.crm.msg.customerGroupUpdateError'))
  }
}

async function loadOpportunities() {
  loading.value = true
  try {
    if (customers.value.length === 0) await loadCustomers()
    const res = await api.get('/api/v1/crm/opportunities', { params: { branch_id: branchId, size: 100 } })
    opportunities.value = res.data.items ?? res.data
  } catch { toast.error(t('backoffice.crm.msg.loadOpportunitiesError')) }
  finally { loading.value = false }
}

async function loadActivities() {
  loading.value = true
  try {
    if (customers.value.length === 0) await loadCustomers()
    const res = await api.get('/api/v1/crm/activities', { params: { branch_id: branchId, size: 100 } })
    activities.value = res.data.items ?? res.data
  } catch { toast.error(t('backoffice.crm.msg.loadActivitiesError')) }
  finally { loading.value = false }
}

async function loadCampaigns() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/crm/campaigns', { params: { branch_id: branchId, size: 100 } })
    campaigns.value = res.data.items ?? res.data
  } catch { toast.error(t('backoffice.crm.msg.loadCampaignsError')) }
  finally { loading.value = false }
}

async function loadGuestProfiles() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/crm/guest-profiles', { params: { branch_id: branchId, vip_only: guestVipOnly.value } })
    guestProfiles.value = res.data
  } catch { toast.error(t('backoffice.crm.msg.loadGuestsError')) }
  finally { loading.value = false }
}

async function loadTab(tabId: typeof tab.value) {
  tab.value = tabId
  if (tabId === 'leads') await loadLeads()
  if (tabId === 'customers') await loadCustomers()
  if (tabId === 'opportunities') await loadOpportunities()
  if (tabId === 'activities') await loadActivities()
  if (tabId === 'campaigns') await loadCampaigns()
  if (tabId === 'guests') await loadGuestProfiles()
  if (tabId === 'loyalty') await loadLoyaltyProgram()
}

// ── Loyalty (C-01) ────────────────────────────────────────────────────────
interface LoyaltyProgram {
  id: number; branch_id: number; points_per_egp: number
  redeem_rate: number; min_redeem_points: number; is_active: boolean
}
interface LoyaltyAccount {
  id: number; customer_id: number; balance: number; lifetime_earned: number; lifetime_redeemed: number
}
interface LoyaltyTransaction {
  id: number; points: number; transaction_type: string; reference: string | null; created_at: string
}
interface LoyaltyRedeemForm { customer_id: string; points: string; reference: string }

const loyaltyProgram = ref<LoyaltyProgram | null>(null)
const loyaltyLoading = ref(false)
const loyaltyCustomerId = ref('')
const loyaltyAccount = ref<LoyaltyAccount | null>(null)
const loyaltyTransactions = ref<LoyaltyTransaction[]>([])
const loyaltyAccountLoading = ref(false)
const redeemForm = ref<LoyaltyRedeemForm>({ customer_id: '', points: '', reference: '' })
const redeemLoading = ref(false)
const showLoyaltySetup = ref(false)
const loyaltySetupForm = ref({ points_per_egp: '1', redeem_rate: '0.5', min_redeem_points: '100', is_active: true })

async function loadLoyaltyProgram() {
  loyaltyLoading.value = true
  try {
    const res = await api.get(ENDPOINTS.crm.loyaltyProgram, { params: { branch_id: branchId } })
    loyaltyProgram.value = res.data
  } catch { loyaltyProgram.value = null }
  finally { loyaltyLoading.value = false }
}

async function saveLoyaltyProgram() {
  try {
    const payload = {
      branch_id: branchId,
      points_per_egp: parseFloat(loyaltySetupForm.value.points_per_egp),
      redeem_rate: parseFloat(loyaltySetupForm.value.redeem_rate),
      min_redeem_points: parseInt(loyaltySetupForm.value.min_redeem_points),
      is_active: loyaltySetupForm.value.is_active,
    }
    if (loyaltyProgram.value) {
      const res = await api.patch(ENDPOINTS.crm.loyaltyProgram, payload, { params: { branch_id: branchId } })
      loyaltyProgram.value = res.data
    } else {
      const res = await api.post(ENDPOINTS.crm.loyaltyProgram, payload)
      loyaltyProgram.value = res.data
    }
    showLoyaltySetup.value = false
    toast.success(t('backoffice.crm.msg.loyaltySettingsSaved'))
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.crm.msg.saveFailed'))
  }
}

async function lookupLoyaltyAccount() {
  const id = parseInt(loyaltyCustomerId.value)
  if (!id) return
  loyaltyAccountLoading.value = true
  try {
    const [accRes, txRes] = await Promise.all([
      api.get(ENDPOINTS.crm.loyaltyAccount, { params: { branch_id: branchId, customer_id: id } }),
      api.get(ENDPOINTS.crm.loyaltyTransactions, { params: { branch_id: branchId, customer_id: id, limit: 20 } }),
    ])
    loyaltyAccount.value = accRes.data
    loyaltyTransactions.value = txRes.data ?? []
  } catch { toast.error(t('backoffice.crm.msg.loyaltyAccountNotFound')) }
  finally { loyaltyAccountLoading.value = false }
}

async function redeemPoints() {
  redeemLoading.value = true
  try {
    await api.post(ENDPOINTS.crm.loyaltyRedeem, {
      branch_id: branchId,
      customer_id: parseInt(redeemForm.value.customer_id),
      points: parseInt(redeemForm.value.points),
      reference: redeemForm.value.reference || null,
    })
    toast.success(t('backoffice.crm.msg.pointsRedeemed'))
    redeemForm.value = { customer_id: '', points: '', reference: '' }
    if (loyaltyAccount.value) await lookupLoyaltyAccount()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.crm.msg.redeemPointsError'))
  } finally { redeemLoading.value = false }
}

// ── Leads: create ────────────────────────────────────────────────────────
async function createLead() {
  if (!leadForm.value.full_name) { toast.error(t('backoffice.crm.msg.leadNameRequired')); return }
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
    toast.success(t('backoffice.crm.msg.leadAdded'))
    showLeadForm.value = false
    leadForm.value = { full_name: '', phone: '', email: '', nationality: '', source_id: '', interest: 'other', expected_value: '0', notes: '' }
    await loadLeads()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.crm.msg.leadAddError'))
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
  } catch { toast.error(t('backoffice.crm.msg.leadStatusUpdateErrorRetry')) }
}

// ── Lead detail drawer ───────────────────────────────────────────────────
async function openLeadDetail(lead: Lead) {
  selectedLead.value = lead
  editLeadForm.value = { phone: lead.phone ?? '', source_id: lead.source_id ?? '', notes: lead.notes ?? '' }
  lostReason.value = ''
  convertForm.value = { check_in: '', check_out: '', room_id: '' }
  availableRoomsForConvert.value = []
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
  } catch { toast.error(t('backoffice.crm.msg.loadCallNotesError')) }
  finally { loadingNotes.value = false }
}

async function addCallNote() {
  if (!selectedLead.value) return
  if (!callNoteForm.value.summary || callNoteForm.value.summary.trim().length < 3) {
    toast.error(t('backoffice.crm.msg.callSummaryTooShort')); return
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
    toast.success(t('backoffice.crm.msg.callNoteSaved'))
    callNoteForm.value = { direction: 'outbound', duration_min: '', summary: '', outcome: 'no_decision' }
    await loadCallNotes(selectedLead.value.id)
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.crm.msg.callNoteSaveError'))
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
    toast.success(t('backoffice.crm.msg.editsSaved'))
    Object.assign(selectedLead.value, res.data)
    const idx = leads.value.findIndex(l => l.id === selectedLead.value!.id)
    if (idx !== -1) leads.value[idx] = { ...leads.value[idx], ...res.data }
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.crm.msg.editsSaveError'))
  } finally {
    savingLeadEdit.value = false
  }
}

async function markLeadLost() {
  if (!selectedLead.value) return
  if (!lostReason.value || lostReason.value.trim().length < 1) {
    toast.error(t('backoffice.crm.msg.lostReasonRequired')); return
  }
  savingLost.value = true
  try {
    const res = await api.patch(`/api/v1/crm/leads/${selectedLead.value.id}`, {
      stage: 'lost', lost_reason: lostReason.value,
    })
    toast.success(t('backoffice.crm.msg.leadMarkedLost'))
    Object.assign(selectedLead.value, res.data)
    const idx = leads.value.findIndex(l => l.id === selectedLead.value!.id)
    if (idx !== -1) leads.value[idx] = { ...leads.value[idx], ...res.data }
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.crm.msg.leadStatusUpdateError'))
  } finally {
    savingLost.value = false
  }
}

// ── wagdy.md C-03: تحويل lead لحجز مباشرة بضغطة واحدة ──────────────────
interface AvailableRoom { id: number; name: string }
const convertForm = ref({ check_in: '', check_out: '', room_id: '' as number | '' })
const availableRoomsForConvert = ref<AvailableRoom[]>([])
const loadingAvailableRooms = ref(false)
const convertingLead = ref(false)

async function loadAvailableRoomsForConvert() {
  availableRoomsForConvert.value = []
  convertForm.value.room_id = ''
  if (!convertForm.value.check_in || !convertForm.value.check_out) return
  if (convertForm.value.check_out <= convertForm.value.check_in) return
  loadingAvailableRooms.value = true
  try {
    const res = await api.get('/api/v1/pms/rooms/available', {
      params: { branch_id: branchId, check_in: convertForm.value.check_in, check_out: convertForm.value.check_out },
    })
    availableRoomsForConvert.value = res.data ?? []
  } catch (e) {
    toast.error(t('backoffice.crm.msg.loadRoomsError'))
  } finally {
    loadingAvailableRooms.value = false
  }
}

async function convertLeadToBooking() {
  if (!selectedLead.value) return
  if (!convertForm.value.check_in || !convertForm.value.check_out || !convertForm.value.room_id) {
    toast.error(t('backoffice.crm.msg.selectDatesAndRoom'))
    return
  }
  convertingLead.value = true
  try {
    const res = await api.post(`/api/v1/crm/leads/${selectedLead.value.id}/convert`, {
      check_in: convertForm.value.check_in,
      check_out: convertForm.value.check_out,
      room_ids: [convertForm.value.room_id],
    })
    toast.success(t('backoffice.crm.msg.leadConverted', { number: res.data.booking_number }))
    Object.assign(selectedLead.value, res.data.lead)
    const idx = leads.value.findIndex(l => l.id === selectedLead.value!.id)
    if (idx !== -1) leads.value[idx] = { ...leads.value[idx], ...res.data.lead }
    convertForm.value = { check_in: '', check_out: '', room_id: '' }
    availableRoomsForConvert.value = []
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.crm.msg.convertLeadError'))
  } finally {
    convertingLead.value = false
  }
}

// ── Customers: create ────────────────────────────────────────────────────
async function createCustomer() {
  if (!customerForm.value.full_name) { toast.error(t('backoffice.crm.msg.customerNameRequired')); return }
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
    toast.success(t('backoffice.crm.msg.customerAdded'))
    showCustomerForm.value = false
    customerForm.value = { full_name: '', phone: '', email: '', nationality: '', segment: 'regular', notes: '' }
    await loadCustomers()
  } catch (e: any) {
    // رسالة الباك إند بتوضّح اسم/رقم العميل المكرر فعليًا — نعرضها زي ما هي
    toast.error(e?.response?.data?.detail ?? t('backoffice.crm.msg.customerAddError'))
  } finally {
    savingCustomer.value = false
  }
}

// ── Opportunities ─────────────────────────────────────────────────────
async function createOpportunity() {
  if (!opportunityForm.value.customer_id) { toast.error(t('backoffice.crm.msg.selectCustomer')); return }
  if (!opportunityForm.value.title.trim()) { toast.error(t('backoffice.crm.msg.oppTitleRequired')); return }
  savingOpportunity.value = true
  try {
    await api.post('/api/v1/crm/opportunities', {
      branch_id: branchId,
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
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.crm.msg.oppAddError'))
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
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.crm.msg.oppStatusUpdateError'))
  }
}

async function setOpportunityStage(opp: Opportunity, stage: string) {
  try {
    const res = await api.patch(`/api/v1/crm/opportunities/${opp.id}`, { stage })
    opp.stage = res.data.stage
  } catch { toast.error(t('backoffice.crm.msg.oppStatusUpdateError')) }
}

// ── Activities ────────────────────────────────────────────────────────
async function createActivity() {
  if (!activityForm.value.customer_id) { toast.error(t('backoffice.crm.msg.selectCustomer')); return }
  if (!activityForm.value.title.trim()) { toast.error(t('backoffice.crm.msg.activityTitleRequired')); return }
  if (!activityForm.value.due_date) { toast.error(t('backoffice.crm.msg.dueDateRequired')); return }
  savingActivity.value = true
  try {
    await api.post('/api/v1/crm/activities', {
      branch_id: branchId,
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
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.crm.msg.activityAddError'))
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

// ── Campaigns ────────────────────────────────────────────────────────────
async function createCampaign() {
  if (!campaignForm.value.name || !campaignForm.value.start_date || !campaignForm.value.end_date) {
    toast.error(t('backoffice.crm.msg.campaignFieldsRequired')); return
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
    toast.success(t('backoffice.crm.msg.campaignCreated'))
    showCampaignForm.value = false
    campaignForm.value = { name: '', campaign_type: 'social_media', start_date: '', end_date: '', budget: '0' }
    await loadCampaigns()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.crm.msg.campaignCreateError'))
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

onMounted(loadLeads)
</script>

<template>
  <div>
    <h2 class="text-2xl font-black text-gray-900 dark:text-gray-100 mb-6">{{ t('backoffice.crm.title') }}</h2>

    <div class="flex items-center justify-between mb-6 flex-wrap gap-3">
      <div class="flex gap-1 bg-stone-100 dark:bg-gray-700 p-1 rounded-xl w-fit">
        <button v-for="tabDef in tabsList"
          :key="tabDef.val" @click="loadTab(tabDef.val as any)"
          :class="['px-4 py-2 rounded-lg text-sm font-semibold transition-all', tab === tabDef.val ? 'bg-white dark:bg-surface shadow-sm text-gray-900 dark:text-gray-100' : 'text-gray-500 dark:text-gray-500 hover:text-gray-700 dark:text-gray-300']"
        >{{ tabDef.label }}</button>
      </div>
      <AppButton v-if="tab === 'leads'" size="sm" @click="showLeadForm = !showLeadForm">
        {{ showLeadForm ? t('backoffice.crm.cancel') : `+ ${t('backoffice.crm.newLead')}` }}
      </AppButton>
      <div v-if="tab === 'customers'" class="flex items-center gap-2">
        <AppButton v-if="authStore.roleLevel >= 60" size="sm" variant="secondary" @click="groupModal = true">
          🏷️ {{ t('backoffice.crm.customerGroups') }}
        </AppButton>
        <AppButton size="sm" @click="showCustomerForm = !showCustomerForm">
          {{ showCustomerForm ? t('backoffice.crm.cancel') : `+ ${t('backoffice.crm.newCustomer')}` }}
        </AppButton>
      </div>
      <AppButton v-if="tab === 'opportunities'" size="sm" @click="showOpportunityForm = !showOpportunityForm">
        {{ showOpportunityForm ? t('backoffice.crm.cancel') : `+ ${t('backoffice.crm.newOpportunity')}` }}
      </AppButton>
      <AppButton v-if="tab === 'activities'" size="sm" @click="showActivityForm = !showActivityForm">
        {{ showActivityForm ? t('backoffice.crm.cancel') : `+ ${t('backoffice.crm.newActivity')}` }}
      </AppButton>
      <AppButton v-if="tab === 'campaigns'" size="sm" @click="showCampaignForm = !showCampaignForm">
        {{ showCampaignForm ? t('backoffice.crm.cancel') : `+ ${t('backoffice.crm.newCampaign')}` }}
      </AppButton>
    </div>

    <!-- Leads -->
    <div v-if="tab === 'leads'">
      <AppCard v-if="showLeadForm" class="mb-4">
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <input v-model="leadForm.full_name" type="text" :placeholder="t('backoffice.crm.fullNameRequired')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm sm:col-span-2" />
          <input v-model="leadForm.phone" type="text" :placeholder="t('backoffice.crm.phone')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="leadForm.email" type="email" :placeholder="t('backoffice.crm.email')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <select v-model="leadForm.source_id" class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
            <option value="">{{ t('backoffice.crm.leadSourceOptional') }}</option>
            <option v-for="s in leadSources" :key="s.id" :value="s.id">{{ s.name }}{{ !s.is_active ? ` (${t('backoffice.crm.inactive')})` : '' }}</option>
          </select>
          <select v-model="leadForm.interest" class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
            <option v-for="(label, val) in interestLabels" :key="val" :value="val">{{ label }}</option>
          </select>
          <input v-model="leadForm.expected_value" type="number" min="0" step="0.01" :placeholder="t('backoffice.crm.expectedValue')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          <input v-model="leadForm.notes" type="text" :placeholder="t('backoffice.crm.notes')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm sm:col-span-2" />
        </div>
        <AppButton class="mt-3" size="sm" :loading="savingLead" @click="createLead">{{ t('backoffice.crm.saveLead') }}</AppButton>
      </AppCard>

      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <div v-else class="space-y-3">
        <div v-for="lead in leads" :key="lead.id"
          class="bg-white dark:bg-surface rounded-2xl border border-stone-200 dark:border-border p-4 shadow-sm flex items-center justify-between cursor-pointer hover:border-blue-300"
          @click="openLeadDetail(lead)">
          <div>
            <div class="flex items-center gap-2 mb-1">
              <span class="font-bold text-gray-900 dark:text-gray-100">{{ lead.full_name }}</span>
              <span v-if="lead.phone" class="text-xs text-gray-400 dark:text-gray-500">{{ lead.phone }}</span>
            </div>
            <div class="flex items-center gap-2 text-xs flex-wrap">
              <span class="px-2 py-0.5 bg-blue-50 text-blue-700 rounded-full">{{ interestLabels[lead.interest] ?? lead.interest }}</span>
              <span v-if="lead.source_id" class="px-2 py-0.5 bg-stone-100 dark:bg-gray-700 text-gray-600 dark:text-gray-500 rounded-full">{{ sourceNameById[lead.source_id] ?? t('backoffice.crm.sourceHash', { id: lead.source_id }) }}</span>
              <span v-else class="px-2 py-0.5 bg-stone-100 dark:bg-gray-700 text-gray-400 dark:text-gray-500 rounded-full">{{ t('backoffice.crm.noSource') }}</span>
              <span class="text-gray-400 dark:text-gray-500">{{ fmtDate(lead.created_at) }}</span>
            </div>
          </div>
          <div class="flex items-center gap-2" @click.stop>
            <AppBadge size="sm" :variant="stageConfig[lead.stage]?.variant ?? 'neutral'">
              {{ stageConfig[lead.stage]?.label ?? lead.stage }}
            </AppBadge>
            <AppButton v-if="!['won','lost'].includes(lead.stage)" size="sm" @click="advanceLead(lead)">
              {{ t('backoffice.crm.advance') }} ←
            </AppButton>
            <AppButton size="sm" variant="secondary" @click="openLeadDetail(lead)">{{ t('backoffice.crm.details') }}</AppButton>
          </div>
        </div>
        <EmptyState v-if="leads.length === 0" icon="🤝" :title="t('backoffice.crm.noLeads')" />
      </div>
    </div>

    <!-- Customers -->
    <div v-if="tab === 'customers'">
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
        <table class="w-full">
          <thead class="bg-stone-50 dark:bg-gray-800/60">
            <tr>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.crm.customer') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.crm.segmentCol') }}</th>
              <th v-if="authStore.roleLevel >= 60" class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.crm.discountGroup') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.crm.visits') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.crm.totalSpent') }}</th>
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
                    <div v-if="c.phone" class="text-xs text-gray-400 dark:text-gray-500">{{ c.phone }}</div>
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
              <td class="px-4 py-3 text-sm font-bold text-blue-700">{{ formatNumber(c.total_spent) }} {{ t('backoffice.crm.egp') }}</td>
            </tr>
            <tr v-if="customers.length === 0">
              <td colspan="5" class="px-4 py-8">
                <EmptyState icon="👥" :title="t('backoffice.crm.noCustomers')" />
              </td>
            </tr>
          </tbody>
        </table>
      </AppCard>
    </div>

    <!-- Opportunities -->
    <div v-if="tab === 'opportunities'">
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
              <span class="text-xs text-gray-400 dark:text-gray-500 ms-2">{{ customerNameById[opp.customer_id] ?? t('backoffice.crm.customerHash', { id: opp.customer_id }) }}</span>
            </div>
            <AppBadge size="sm" :variant="oppStageConfig[opp.stage]?.variant ?? 'neutral'">
              {{ oppStageConfig[opp.stage]?.label ?? opp.stage }}
            </AppBadge>
          </div>
          <div class="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-500 mb-3 flex-wrap">
            <span>{{ productTypeLabels[opp.product_type] ?? opp.product_type }}</span>
            <span>{{ t('backoffice.crm.expectedValueLabel') }}: {{ formatNumber(opp.expected_value) }} {{ t('backoffice.crm.egp') }}</span>
            <span>{{ t('backoffice.crm.probabilityLabel') }}: {{ opp.probability }}%</span>
            <span v-if="opp.expected_close">{{ t('backoffice.crm.expectedCloseLabel') }}: {{ fmtDate(opp.expected_close) }}</span>
            <span v-if="opp.lost_reason" class="text-red-600">{{ t('backoffice.crm.lostReasonLabel') }}: {{ opp.lost_reason }}</span>
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
      </div>
    </div>

    <!-- Activities -->
    <div v-if="tab === 'activities'">
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
              <span class="text-xs text-gray-400 dark:text-gray-500">{{ customerNameById[act.customer_id] ?? t('backoffice.crm.customerHash', { id: act.customer_id }) }}</span>
            </div>
            <div class="flex items-center gap-2 text-xs flex-wrap">
              <span class="px-2 py-0.5 bg-blue-50 text-blue-700 rounded-full">{{ activityTypeLabels[act.activity_type] ?? act.activity_type }}</span>
              <span class="text-gray-400 dark:text-gray-500">{{ t('backoffice.crm.dueLabel') }} {{ fmtDate(act.due_date) }}<span v-if="act.due_time"> — {{ act.due_time }}</span></span>
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
      </div>
    </div>

    <!-- Guest Profiles (PMS checkout integration — read-only) -->
    <div v-if="tab === 'guests'">
      <p class="text-xs text-gray-500 dark:text-gray-500 mb-3">
        {{ t('backoffice.crm.guestProfilesHint') }}
      </p>
      <div class="flex justify-end mb-3">
        <label class="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-500">
          <input type="checkbox" v-model="guestVipOnly" @change="loadGuestProfiles" />
          {{ t('backoffice.crm.vipOnly') }}
        </label>
      </div>
      <div v-if="loading" class="flex justify-center py-12"><AppSpinner size="lg" /></div>
      <AppCard v-else padding="none">
        <table class="w-full">
          <thead class="bg-stone-50 dark:bg-gray-800/60">
            <tr>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.crm.guest') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.crm.visitCount') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.crm.avgSpend') }}</th>
              <th class="px-4 py-3 text-start text-xs font-semibold text-gray-500 dark:text-gray-500 uppercase">{{ t('backoffice.crm.lastStay') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="g in guestProfiles" :key="g.id" class="border-t border-stone-100 dark:border-border/50 hover:bg-stone-50 dark:bg-gray-800/60">
              <td class="px-4 py-3">
                <div class="flex items-center gap-2">
                  <span v-if="g.vip_flag" class="text-amber-500 text-sm">⭐</span>
                  <div>
                    <div class="font-medium text-gray-900 dark:text-gray-100 text-sm">{{ g.full_name }}</div>
                    <div class="text-xs text-gray-400 dark:text-gray-500">{{ g.phone }}</div>
                  </div>
                </div>
              </td>
              <td class="px-4 py-3 text-sm text-gray-700 dark:text-gray-300 font-medium">{{ g.total_visits }}</td>
              <td class="px-4 py-3 text-sm font-bold text-blue-700">{{ formatNumber(g.avg_spend) }} {{ t('backoffice.crm.egp') }}</td>
              <td class="px-4 py-3 text-sm text-gray-600 dark:text-gray-500">{{ fmtDate(g.last_stay) }}</td>
            </tr>
            <tr v-if="guestProfiles.length === 0">
              <td colspan="4" class="px-4 py-8">
                <EmptyState icon="🏨" :title="t('backoffice.crm.noGuestProfiles')" :subtitle="t('backoffice.crm.noGuestProfilesHint')" />
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
              <span class="text-xs text-gray-400 dark:text-gray-500 ms-2">{{ campaignTypeLabels[c.campaign_type] ?? c.campaign_type }}</span>
            </div>
            <AppBadge size="sm" :variant="campaignStatusConfig[c.status]?.variant ?? 'neutral'">
              {{ campaignStatusConfig[c.status]?.label ?? c.status }}
            </AppBadge>
          </div>
          <div class="flex items-center gap-4 text-xs text-gray-500 dark:text-gray-500 mb-3">
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
      </div>
    </div>

    <!-- Lead detail modal — call notes history + inline edit + mark lost -->
    <AppModal :open="!!selectedLead" :title="selectedLead?.full_name" size="lg" @close="closeLeadDetail">
      <div v-if="selectedLead" class="space-y-6">
        <div class="flex items-center gap-2 flex-wrap">
          <AppBadge size="sm" :variant="stageConfig[selectedLead.stage]?.variant ?? 'neutral'">
            {{ stageConfig[selectedLead.stage]?.label ?? selectedLead.stage }}
          </AppBadge>
          <span class="text-xs text-gray-400 dark:text-gray-500">{{ t('backoffice.crm.createdAt') }} {{ fmtDate(selectedLead.created_at) }}</span>
          <span v-if="selectedLead.lost_reason" class="text-xs text-red-600">{{ t('backoffice.crm.lostReasonLabel') }}: {{ selectedLead.lost_reason }}</span>
        </div>

        <!-- تعديل بيانات أساسية -->
        <div>
          <h3 class="text-sm font-bold text-gray-700 dark:text-gray-300 mb-2">{{ t('backoffice.crm.editLeadInfo') }}</h3>
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <input v-model="editLeadForm.phone" type="text" :placeholder="t('backoffice.crm.phone')"
              class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
            <select v-model="editLeadForm.source_id" class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
              <option value="">{{ t('backoffice.crm.noSource') }}</option>
              <option v-for="s in leadSources" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
            <input v-model="editLeadForm.notes" type="text" :placeholder="t('backoffice.crm.notes')"
              class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm sm:col-span-2" />
          </div>
          <AppButton class="mt-2" size="sm" variant="secondary" :loading="savingLeadEdit" @click="saveLeadDetails">
            {{ t('backoffice.crm.saveEdits') }}
          </AppButton>
        </div>

        <!-- سجل المكالمات -->
        <div>
          <h3 class="text-sm font-bold text-gray-700 dark:text-gray-300 mb-2">{{ t('backoffice.crm.callHistory') }}</h3>
          <div v-if="loadingNotes" class="flex justify-center py-6"><AppSpinner /></div>
          <div v-else class="space-y-2 mb-3">
            <div v-for="n in callNotes" :key="n.id" class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3 text-sm">
              <div class="flex items-center justify-between mb-1">
                <span class="font-medium text-gray-800 dark:text-gray-200">{{ n.direction === 'inbound' ? t('backoffice.crm.inboundCall') : t('backoffice.crm.outboundCall') }}</span>
                <span class="text-xs text-gray-400 dark:text-gray-500">{{ fmtDateTime(n.called_at) }}</span>
              </div>
              <p class="text-gray-600 dark:text-gray-500">{{ n.summary }}</p>
              <div class="flex items-center gap-2 mt-1">
                <AppBadge size="sm" variant="info">{{ outcomeLabels[n.outcome] ?? n.outcome }}</AppBadge>
                <span v-if="n.duration_min" class="text-xs text-gray-400 dark:text-gray-500">{{ n.duration_min }} {{ t('backoffice.crm.minutes') }}</span>
              </div>
            </div>
            <EmptyState v-if="callNotes.length === 0" icon="📞" :title="t('backoffice.crm.noCallsYet')" />
          </div>

          <div class="border-t border-stone-100 dark:border-border/50 pt-3 space-y-2">
            <div class="grid grid-cols-2 gap-2">
              <select v-model="callNoteForm.direction" class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
                <option value="outbound">{{ t('backoffice.crm.outboundCall') }}</option>
                <option value="inbound">{{ t('backoffice.crm.inboundCall') }}</option>
              </select>
              <select v-model="callNoteForm.outcome" class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
                <option v-for="(label, val) in outcomeLabels" :key="val" :value="val">{{ label }}</option>
              </select>
            </div>
            <textarea v-model="callNoteForm.summary" rows="2" :placeholder="t('backoffice.crm.callSummaryPlaceholder')"
              class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
            <input v-model="callNoteForm.duration_min" type="number" min="0" :placeholder="t('backoffice.crm.callDuration')"
              class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm w-40" />
            <AppButton size="sm" :loading="savingCallNote" @click="addCallNote">+ {{ t('backoffice.crm.logCallNote') }}</AppButton>
          </div>
        </div>

        <!-- wagdy.md C-03: تحويل مباشر لحجز -->
        <div v-if="!['won','lost'].includes(selectedLead.stage)" class="border-t border-stone-100 dark:border-border/50 pt-4">
          <h3 class="text-sm font-bold text-gray-700 dark:text-gray-300 mb-2">🏨 {{ t('backoffice.crm.convertToBooking') }}</h3>
          <div class="grid grid-cols-2 gap-2 mb-2">
            <input v-model="convertForm.check_in" @change="loadAvailableRoomsForConvert" type="date"
              class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
            <input v-model="convertForm.check_out" @change="loadAvailableRoomsForConvert" type="date"
              class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          </div>
          <div class="flex gap-2">
            <select v-model="convertForm.room_id" class="flex-1 border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm">
              <option value="" disabled>{{ loadingAvailableRooms ? t('backoffice.crm.loadingRooms') : t('backoffice.crm.selectAvailableRoom') }}</option>
              <option v-for="r in availableRoomsForConvert" :key="r.id" :value="r.id">{{ r.name }}</option>
            </select>
            <AppButton size="sm" variant="primary" :loading="convertingLead" @click="convertLeadToBooking">{{ t('backoffice.crm.convertButton') }}</AppButton>
          </div>
          <p v-if="convertForm.check_in && convertForm.check_out && !loadingAvailableRooms && !availableRoomsForConvert.length"
            class="text-xs text-amber-600 mt-1">{{ t('backoffice.crm.noRoomsAvailable') }}</p>
        </div>

        <!-- وسم كخسارة -->
        <div v-if="!['won','lost'].includes(selectedLead.stage)" class="border-t border-stone-100 dark:border-border/50 pt-4">
          <h3 class="text-sm font-bold text-gray-700 dark:text-gray-300 mb-2">{{ t('backoffice.crm.markAsLost') }}</h3>
          <div class="flex gap-2">
            <input v-model="lostReason" type="text" :placeholder="t('backoffice.crm.lostReasonRequiredField')"
              class="flex-1 border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
            <AppButton size="sm" variant="secondary" :loading="savingLost" @click="markLeadLost">{{ t('backoffice.crm.markLost') }}</AppButton>
          </div>
        </div>
      </div>
    </AppModal>

    <!-- مجموعات العملاء (خصم دائم) -->
    <AppModal :open="groupModal" :title="t('backoffice.crm.customerGroups')" size="lg" @close="groupModal = false">
      <div class="space-y-4">
        <p class="text-xs text-gray-500 dark:text-gray-500">
          {{ t('backoffice.crm.groupsHint') }}
        </p>

        <AppCard v-if="authStore.roleLevel >= 80" padding="sm">
          <div class="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <input v-model="groupForm.name" type="text" :placeholder="t('backoffice.crm.nameEnglishRequired')"
              class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
            <input v-model="groupForm.name_ar" type="text" :placeholder="t('backoffice.crm.nameArabic')"
              class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
            <input v-model="groupForm.discount_percentage" type="number" min="0" max="100" step="0.01" :placeholder="t('backoffice.crm.discountPct')"
              class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
          </div>
          <div class="flex gap-2 mt-2">
            <AppButton size="sm" :loading="savingGroup" @click="saveGroup">
              {{ editingGroup ? t('backoffice.crm.saveEdits') : t('backoffice.crm.addGroup') }}
            </AppButton>
            <AppButton v-if="editingGroup" size="sm" variant="secondary" @click="openCreateGroup">{{ t('backoffice.crm.cancelEdit') }}</AppButton>
          </div>
        </AppCard>
        <p v-else class="text-xs text-amber-600">{{ t('backoffice.crm.groupsAdminOnly') }}</p>

        <div class="border-t border-stone-100 dark:border-border/50 pt-3 space-y-2">
          <div v-for="g in groups" :key="g.id" class="flex items-center justify-between bg-stone-50 dark:bg-gray-800/60 rounded-xl px-3 py-2">
            <div>
              <span class="font-medium text-sm text-gray-900 dark:text-gray-100">{{ g.name_ar || g.name }}</span>
              <span class="text-xs text-gray-500 dark:text-gray-500 ms-2">{{ t('backoffice.crm.discountOf', { pct: g.discount_percentage }) }}</span>
            </div>
            <div class="flex items-center gap-2">
              <AppBadge size="sm" :variant="g.is_active ? 'success' : 'neutral'">{{ g.is_active ? t('backoffice.crm.groupActive') : t('backoffice.crm.groupSuspended') }}</AppBadge>
              <template v-if="authStore.roleLevel >= 80">
                <button @click="openEditGroup(g)" class="text-xs font-semibold text-primary-700 hover:underline">{{ t('backoffice.crm.edit') }}</button>
                <button @click="toggleGroupActive(g)" class="text-xs font-semibold text-gray-500 dark:text-gray-500 hover:underline">
                  {{ g.is_active ? t('backoffice.crm.suspend') : t('backoffice.crm.activate') }}
                </button>
              </template>
            </div>
          </div>
          <EmptyState v-if="groups.length === 0" icon="🏷️" :title="t('backoffice.crm.noGroups')" />
        </div>
      </div>
    </AppModal>

    <!-- ══ TAB: LOYALTY ══ -->
    <div v-if="tab === 'loyalty'" class="space-y-5">
      <!-- إعدادات البرنامج -->
      <AppCard :title="t('backoffice.crm.loyaltyProgramTitle')">
        <div v-if="loyaltyLoading" class="flex justify-center py-6"><AppSpinner /></div>
        <div v-else-if="loyaltyProgram" class="space-y-3">
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
            <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
              <div class="text-xs text-gray-500 dark:text-gray-500 mb-1">{{ t('backoffice.crm.pointPer') }}</div>
              <div class="text-xl font-black text-gray-800 dark:text-gray-200">{{ loyaltyProgram.points_per_egp }} {{ t('backoffice.crm.egp') }}</div>
            </div>
            <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
              <div class="text-xs text-gray-500 dark:text-gray-500 mb-1">{{ t('backoffice.crm.pointValue') }}</div>
              <div class="text-xl font-black text-gray-800 dark:text-gray-200">{{ loyaltyProgram.redeem_rate }} {{ t('backoffice.crm.egp') }}</div>
            </div>
            <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
              <div class="text-xs text-gray-500 dark:text-gray-500 mb-1">{{ t('backoffice.crm.minRedeem') }}</div>
              <div class="text-xl font-black text-gray-800 dark:text-gray-200">{{ loyaltyProgram.min_redeem_points }}</div>
            </div>
            <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
              <div class="text-xs text-gray-500 dark:text-gray-500 mb-1">{{ t('backoffice.crm.statusLabel') }}</div>
              <AppBadge :variant="loyaltyProgram.is_active ? 'success' : 'neutral'">
                {{ loyaltyProgram.is_active ? t('backoffice.crm.programActive') : t('backoffice.crm.programSuspended') }}
              </AppBadge>
            </div>
          </div>
          <AppButton v-if="authStore.roleLevel >= 80" size="sm" variant="outline" @click="showLoyaltySetup = !showLoyaltySetup">
            ✏️ {{ t('backoffice.crm.editSettings') }}
          </AppButton>
        </div>
        <EmptyState v-else icon="🎁" :title="t('backoffice.crm.noLoyaltyProgram')" :subtitle="t('backoffice.crm.noLoyaltyProgramHint')">
          <AppButton size="sm" @click="showLoyaltySetup = true">{{ t('backoffice.crm.createProgram') }}</AppButton>
        </EmptyState>

        <!-- فورم الإعدادات -->
        <div v-if="showLoyaltySetup" class="mt-4 border-t border-stone-200 dark:border-border pt-4 space-y-3">
          <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div>
              <label class="text-xs font-semibold text-gray-600 dark:text-gray-500 block mb-1">{{ t('backoffice.crm.pointPerEgp') }}</label>
              <input v-model="loyaltySetupForm.points_per_egp" type="number" min="0.01" step="0.01"
                class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
            </div>
            <div>
              <label class="text-xs font-semibold text-gray-600 dark:text-gray-500 block mb-1">{{ t('backoffice.crm.pointValueEgp') }}</label>
              <input v-model="loyaltySetupForm.redeem_rate" type="number" min="0.01" step="0.01"
                class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
            </div>
            <div>
              <label class="text-xs font-semibold text-gray-600 dark:text-gray-500 block mb-1">{{ t('backoffice.crm.minRedeem') }}</label>
              <input v-model="loyaltySetupForm.min_redeem_points" type="number" min="1"
                class="w-full border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm" />
            </div>
            <div class="flex flex-col justify-end">
              <label class="flex items-center gap-2 text-sm cursor-pointer">
                <input v-model="loyaltySetupForm.is_active" type="checkbox" class="rounded" />
                {{ t('backoffice.crm.activateProgram') }}
              </label>
            </div>
          </div>
          <div class="flex gap-2">
            <AppButton size="sm" @click="saveLoyaltyProgram">{{ t('backoffice.crm.save') }}</AppButton>
            <AppButton size="sm" variant="ghost" @click="showLoyaltySetup = false">{{ t('backoffice.crm.cancel') }}</AppButton>
          </div>
        </div>
      </AppCard>

      <!-- بحث عن عميل -->
      <AppCard :title="t('backoffice.crm.customerPoints')">
        <div class="flex gap-2 mb-4">
          <input v-model="loyaltyCustomerId" type="number" :placeholder="t('backoffice.crm.customerIdNumber')"
            class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm w-40"
            @keyup.enter="lookupLoyaltyAccount" />
          <AppButton size="sm" :loading="loyaltyAccountLoading" @click="lookupLoyaltyAccount">{{ t('backoffice.crm.search') }}</AppButton>
        </div>

        <div v-if="loyaltyAccount" class="space-y-4">
          <!-- ملخص الرصيد -->
          <div class="grid grid-cols-3 gap-3 text-center">
            <div class="bg-green-50 rounded-xl p-3">
              <div class="text-xs text-gray-500 dark:text-gray-500 mb-1">{{ t('backoffice.crm.currentBalance') }}</div>
              <div class="text-2xl font-black text-green-700">{{ loyaltyAccount.balance }}</div>
              <div class="text-xs text-gray-400 dark:text-gray-500">{{ t('backoffice.crm.point') }}</div>
            </div>
            <div class="bg-blue-50 rounded-xl p-3">
              <div class="text-xs text-gray-500 dark:text-gray-500 mb-1">{{ t('backoffice.crm.lifetimeEarned') }}</div>
              <div class="text-xl font-black text-blue-700">{{ loyaltyAccount.lifetime_earned }}</div>
            </div>
            <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
              <div class="text-xs text-gray-500 dark:text-gray-500 mb-1">{{ t('backoffice.crm.lifetimeRedeemed') }}</div>
              <div class="text-xl font-black text-gray-700 dark:text-gray-300">{{ loyaltyAccount.lifetime_redeemed }}</div>
            </div>
          </div>

          <!-- فورم الاسترداد -->
          <div class="border border-amber-200 bg-amber-50 rounded-xl p-4 space-y-2">
            <div class="text-sm font-bold text-amber-800">🎁 {{ t('backoffice.crm.redeemPoints') }}</div>
            <div class="flex gap-2 flex-wrap">
              <input v-model="redeemForm.customer_id" type="number" :placeholder="t('backoffice.crm.customerIdShort')"
                :value="loyaltyCustomerId"
                class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm w-32" />
              <input v-model="redeemForm.points" type="number" min="1" :placeholder="t('backoffice.crm.pointsCount')"
                class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm w-32" />
              <input v-model="redeemForm.reference" type="text" :placeholder="t('backoffice.crm.referenceOptional')"
                class="border border-stone-200 dark:border-border rounded-xl px-3 py-2 text-sm flex-1 min-w-[120px]" />
              <AppButton size="sm" variant="primary" :loading="redeemLoading" @click="redeemPoints">{{ t('backoffice.crm.redeem') }}</AppButton>
            </div>
            <div v-if="loyaltyProgram" class="text-xs text-amber-700">
              {{ t('backoffice.crm.redeemValueLine', { value: redeemForm.points ? (parseFloat(redeemForm.points) * loyaltyProgram.redeem_rate).toFixed(2) : '0', min: loyaltyProgram.min_redeem_points }) }}
            </div>
          </div>

          <!-- سجل المعاملات -->
          <div>
            <div class="text-sm font-bold text-gray-700 dark:text-gray-300 mb-2">{{ t('backoffice.crm.recentTransactions') }}</div>
            <div v-if="loyaltyTransactions.length === 0" class="text-sm text-gray-400 dark:text-gray-500">{{ t('backoffice.crm.noTransactions') }}</div>
            <div v-for="tx in loyaltyTransactions" :key="tx.id"
              class="flex items-center justify-between py-2 border-b border-stone-100 dark:border-border/50 last:border-0 text-sm">
              <div>
                <span :class="tx.points > 0 ? 'text-green-600 font-bold' : 'text-red-600 font-bold'">
                  {{ tx.points > 0 ? '+' : '' }}{{ tx.points }} {{ t('backoffice.crm.point') }}
                </span>
                <span class="text-gray-500 dark:text-gray-500 ms-2 text-xs">{{ tx.transaction_type }}</span>
                <span v-if="tx.reference" class="text-gray-400 dark:text-gray-500 ms-1 text-xs">· {{ tx.reference }}</span>
              </div>
              <div class="text-xs text-gray-400 dark:text-gray-500">{{ fmtDate(tx.created_at) }}</div>
            </div>
          </div>
        </div>

        <EmptyState v-else-if="!loyaltyAccountLoading" icon="🔍" :title="t('backoffice.crm.searchByCustomerId')" />
      </AppCard>
    </div>

  </div>
</template>
