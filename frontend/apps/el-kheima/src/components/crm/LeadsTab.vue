<script setup lang="ts">
// العملاء المحتملون (Leads) + سجل المكالمات + التحويل المباشر لحجز —
// استُخرج من CRMView.vue (تقسيم الملفات الكبيرة، 2026-09-07).
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, parseApiTimestamp } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppBadge, AppButton, AppModal, AppSpinner, EmptyState, useToast } from '@resort-os/ui'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
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
interface AvailableRoom { id: number; name: string }

const { t } = useI18n()
const { formatDate: fmtDateFn, formatDateTime: fmtDateTimeFn } = useStaffFormat()
const toast = useToast()
const branchId = computed(() => props.branchId)

const loading = ref(false)
const leads = ref<Lead[]>([])
const leadSources = ref<LeadSource[]>([])

const showLeadForm = ref(false)
const savingLead = ref(false)
const leadForm = ref({
  full_name: '', phone: '', email: '', nationality: '',
  source_id: '' as number | '', interest: 'other', expected_value: '0', notes: '',
})

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
    const res = await api.get('/api/v1/crm/lead-sources', { params: { branch_id: branchId.value, active_only: false } })
    leadSources.value = res.data
  } catch { /* المصادر مش حرجة لعرض القائمة نفسها */ }
}

async function loadLeads() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/crm/leads', { params: { branch_id: branchId.value } })
    leads.value = res.data.leads ?? res.data.items ?? res.data
    if (leadSources.value.length === 0) await loadLeadSources()
  } catch { toast.error(t('backoffice.crm.msg.loadLeadsError')) }
  finally { loading.value = false }
}

async function createLead() {
  if (!leadForm.value.full_name) { toast.error(t('backoffice.crm.msg.leadNameRequired')); return }
  savingLead.value = true
  try {
    await api.post('/api/v1/crm/leads', {
      branch_id: branchId.value,
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
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.crm.msg.leadAddError'))
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

// ── wagdy.md C-03: تحويل lead لحجز مباشرة بضغطة واحدة ──────────────────
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
      params: { branch_id: branchId.value, check_in: convertForm.value.check_in, check_out: convertForm.value.check_out },
    })
    availableRoomsForConvert.value = res.data ?? []
  } catch {
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
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.crm.msg.convertLeadError'))
  } finally {
    convertingLead.value = false
  }
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
      branch_id: branchId.value,
      lead_id: selectedLead.value.id,
      direction: callNoteForm.value.direction,
      duration_min: callNoteForm.value.duration_min ? Number(callNoteForm.value.duration_min) : undefined,
      summary: callNoteForm.value.summary,
      outcome: callNoteForm.value.outcome,
    })
    toast.success(t('backoffice.crm.msg.callNoteSaved'))
    callNoteForm.value = { direction: 'outbound', duration_min: '', summary: '', outcome: 'no_decision' }
    await loadCallNotes(selectedLead.value.id)
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.crm.msg.callNoteSaveError'))
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
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.crm.msg.editsSaveError'))
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
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.crm.msg.leadStatusUpdateError'))
  } finally {
    savingLost.value = false
  }
}

onMounted(loadLeads)
</script>

<template>
  <div>
    <div class="flex justify-end mb-4">
      <AppButton size="sm" @click="showLeadForm = !showLeadForm">
        {{ showLeadForm ? t('backoffice.crm.cancel') : `+ ${t('backoffice.crm.newLead')}` }}
      </AppButton>
    </div>

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
            <span v-if="lead.phone" class="text-xs text-gray-400 dark:text-gray-400">{{ lead.phone }}</span>
          </div>
          <div class="flex items-center gap-2 text-xs flex-wrap">
            <span class="rounded-full bg-blue-50 px-2 py-0.5 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300">{{ interestLabels[lead.interest] ?? lead.interest }}</span>
            <span v-if="lead.source_id" class="px-2 py-0.5 bg-stone-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded-full">{{ sourceNameById[lead.source_id] ?? t('backoffice.crm.sourceHash', { id: lead.source_id }) }}</span>
            <span v-else class="px-2 py-0.5 bg-stone-100 dark:bg-gray-700 text-gray-400 dark:text-gray-400 rounded-full">{{ t('backoffice.crm.noSource') }}</span>
            <span class="text-gray-400 dark:text-gray-400">{{ fmtDate(lead.created_at) }}</span>
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

    <!-- Lead detail modal — call notes history + inline edit + mark lost -->
    <AppModal :open="!!selectedLead" :title="selectedLead?.full_name" size="lg" @close="closeLeadDetail">
      <div v-if="selectedLead" class="space-y-6">
        <div class="flex items-center gap-2 flex-wrap">
          <AppBadge size="sm" :variant="stageConfig[selectedLead.stage]?.variant ?? 'neutral'">
            {{ stageConfig[selectedLead.stage]?.label ?? selectedLead.stage }}
          </AppBadge>
          <span class="text-xs text-gray-400 dark:text-gray-400">{{ t('backoffice.crm.createdAt') }} {{ fmtDate(selectedLead.created_at) }}</span>
          <span v-if="selectedLead.lost_reason" class="text-xs text-red-600 dark:text-red-300">{{ t('backoffice.crm.lostReasonLabel') }}: {{ selectedLead.lost_reason }}</span>
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
                <span class="text-xs text-gray-400 dark:text-gray-400">{{ fmtDateTime(n.called_at) }}</span>
              </div>
              <p class="text-gray-600 dark:text-gray-400">{{ n.summary }}</p>
              <div class="flex items-center gap-2 mt-1">
                <AppBadge size="sm" variant="info">{{ outcomeLabels[n.outcome] ?? n.outcome }}</AppBadge>
                <span v-if="n.duration_min" class="text-xs text-gray-400 dark:text-gray-400">{{ n.duration_min }} {{ t('backoffice.crm.minutes') }}</span>
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
            class="mt-1 text-xs text-amber-600 dark:text-amber-300">{{ t('backoffice.crm.noRoomsAvailable') }}</p>
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
  </div>
</template>
