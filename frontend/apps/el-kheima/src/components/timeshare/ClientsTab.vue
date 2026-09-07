<script setup lang="ts">
// عملاء الملكية الجزئية — القائمة + ملف العميل الموحّد (عقود/زيارات/أقساط/
// تقييمات) + جدولة زيارة + نقل وحدة + استيراد Excel — استُخرج من
// TimeshareView.vue (تقسيم الملفات الكبيرة، 2026-09-07). units هنا نسخة
// محلية مستقلة (لنقل الوحدة) — نفس نمط تكرار الجلب المتبع في باقي التابات
// المُستخرجة.
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import {
  AppBadge, AppButton, AppCard, AppIcon, AppInput, AppModal, AppSelect,
  EmptyState, LoadingState, SearchInput, useConfirm, useToast, type SelectOption,
} from '@resort-os/ui'
import TimeshareUnitPicker from '../TimeshareUnitPicker.vue'

const props = defineProps<{ branchId: number | null }>()

type ApiErr = { response?: { data?: { detail?: string; message?: string }; status?: number } }
type BadgeVariant = 'success' | 'warning' | 'danger' | 'info' | 'neutral'
interface Installment {
  id: number; contract_id: number; installment_no: number; due_date: string
  amount: number; paid_amount: number; status: string
  customer_name?: string; customer_phone?: string; room_type?: string
}
interface MaintenanceDue {
  id: number; contract_id: number; fee_year: number; due_date: string
  amount: number; paid_amount: number; status: string
  customer_name?: string; customer_phone?: string; room_type?: string
}
interface Contract {
  id: number; contract_number: string; customer_name: string; customer_phone: string | null
  customer_email: string | null; customer_national_id?: string | null; room_type: string; week_number: number | null
  nights_per_year: number; season: string; total_value: number; down_payment: number
  installments: number; status: string; booking_frozen: boolean
  start_date: string; end_date: string | null; notes: string | null
  nationality: string | null; address: string | null; rci_included: boolean
  partner_company: string | null; maintenance_fee: number
  installments_list: Installment[]
  maintenance_dues_list: MaintenanceDue[]
  collected?: number; overdue_amount?: number
  unit_id: number | null
  unit_capacity?: number | null
}
interface TimeshareUnit { id: number; branch_id: number; unit_number: string; unit_type: string; status: string; notes?: string | null }
interface Visit {
  id: number; contract_id: number; unit_id: number | null
  check_in: string; check_out: string; nights: number; status: string
  customer_name?: string; customer_phone?: string; room_type?: string
  week_number?: number; visit_start?: string
  days_until: number
}
interface GuestReview {
  id: number; guest_name: string; overall_rating: number; comment: string | null
  source: string; reviewed_at: string
}
interface ImportResult { error?: string; imported?: number; skipped?: number; errors?: string[] }

const toast = useToast()
const { confirm } = useConfirm()
const { t } = useI18n()
const { formatDate, formatMoney } = useStaffFormat()
const auth = useAuthStore()
const branchId = computed(() => props.branchId)
const canCollectInstallments = computed(() => auth.hasPermission('timeshare.installments:collect'))
const canCollectMaintenance = computed(() => auth.hasPermission('timeshare.maintenance_dues:collect'))
const canScheduleVisits = computed(() => auth.hasPermission('timeshare.visits:create'))
const canEditVisits = computed(() => auth.hasPermission('timeshare.visits:edit'))
const canAddWaitlist = computed(() => auth.hasPermission('timeshare.waitlist:create'))

const fmt = (v: number | string | null | undefined) => formatMoney(v, 'EGP')
const formatDateValue = (d?: string) => {
  if (!d) return '—'
  try { return formatDate(d, { day: 'numeric', month: 'short', year: 'numeric' }) }
  catch { return d }
}
function roomTypeLabel(type: string): string {
  return t(`backoffice.timeshare.unitTypes.${type}`, type)
}
function roomTypeBadge(type: string) {
  const m: Record<string, string> = {
    'Studio': 'bg-sky-100 text-sky-700 dark:bg-sky-950/60 dark:text-sky-300',
    'Chalet': 'bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300',
  }
  return `text-xs px-2 py-1 rounded-full font-bold ${m[type] || 'bg-stone-100 dark:bg-gray-700 text-stone-600 dark:text-stone-300'}`
}
const contractStatusVariant: Record<string, BadgeVariant> = {
  active: 'success', suspended: 'warning', cancelled: 'danger', expired: 'neutral',
}
function statusLabel(s: string) {
  const icons: Record<string, string> = { active: '✅', suspended: '⏸️', cancelled: '❌', expired: '⌛' }
  const labels: Record<string, string> = {
    active: t('backoffice.timeshare.contractStatus.active'), suspended: t('backoffice.timeshare.contractStatus.suspended'),
    cancelled: t('backoffice.timeshare.contractStatus.cancelled'), expired: t('backoffice.timeshare.contractStatus.expired'),
  }
  return labels[s] ? `${icons[s]} ${labels[s]}` : s
}
const payStatusVariant: Record<string, BadgeVariant> = {
  paid: 'success', pending: 'warning', overdue: 'danger', partial: 'info',
}
function payLabel(s: string) {
  const icons: Record<string, string> = { paid: '✅', pending: '⏳', overdue: '🔴', partial: '🔵' }
  const labels: Record<string, string> = {
    paid: t('backoffice.timeshare.payStatus.paid'), pending: t('backoffice.timeshare.payStatus.pending'),
    overdue: t('backoffice.timeshare.payStatus.overdue'), partial: t('backoffice.timeshare.payStatus.partial'),
  }
  return labels[s] ? `${icons[s]} ${labels[s]}` : s
}
const visitStatusVariant: Record<string, BadgeVariant> = {
  scheduled: 'info', active: 'success', completed: 'neutral', cancelled: 'danger',
}
function visitStatusLabel(s: string) {
  const icons: Record<string, string> = { scheduled: '📅', active: '🏝️', completed: '✅', cancelled: '❌' }
  const labels: Record<string, string> = {
    scheduled: t('backoffice.timeshare.visitStatus.scheduled'), active: t('backoffice.timeshare.visitStatus.active'),
    completed: t('backoffice.timeshare.visitStatus.completed'), cancelled: t('backoffice.timeshare.visitStatus.cancelled'),
  }
  return labels[s] ? `${icons[s]} ${labels[s]}` : s
}

// ── Clients list ─────────────────────────────────────────────────────────
const allClients = ref<Contract[]>([])
const clientSearch = ref('')
const clientStatusFilter = ref('')
const clientRoomFilter = ref('')
const clientsLoading = ref(false)
const expandedClient = ref<number | null>(null)

const filteredClients = computed(() => {
  let list = allClients.value
  if (clientSearch.value) {
    const q = clientSearch.value.toLowerCase()
    list = list.filter(c => c.customer_name?.toLowerCase().includes(q) || c.customer_phone?.includes(q) || c.contract_number?.toLowerCase().includes(q))
  }
  if (clientStatusFilter.value) list = list.filter(c => c.status === clientStatusFilter.value)
  if (clientRoomFilter.value) list = list.filter(c => c.room_type === clientRoomFilter.value)
  return list
})

async function loadClients() {
  clientsLoading.value = true
  try {
    const clients: Contract[] = []
    let page = 1
    const size = 100
    while (true) {
      const response = await api.get('/api/v1/timeshare/contracts', {
        params: { branch_id: branchId.value, page, size },
      })
      const pageItems: Contract[] = response.data?.items ?? []
      clients.push(...pageItems)
      if (clients.length >= Number(response.data?.total ?? 0) || pageItems.length < size) break
      page += 1
    }
    allClients.value = clients
  } catch (e) { toast.error(t('backoffice.timeshare.msg.loadClientsError')) } finally { clientsLoading.value = false }
}

// ── Units (لعرض رقم الوحدة الفعلي + ترشيح النقل) ────────────────────────
const units = ref<TimeshareUnit[]>([])
const unitNumberById = computed<Record<number, string>>(() =>
  Object.fromEntries(units.value.map(u => [u.id, u.unit_number])),
)
async function loadUnits() {
  try {
    const r = await api.get('/api/v1/timeshare/units', { params: { branch_id: branchId.value } })
    units.value = r.data ?? []
  } catch { toast.error(t('backoffice.timeshare.msg.loadUnitsError')) }
}

// ── Customer Profile (ملف عميل مجمّع — كل عقوده/زياراته/أقساطه/تقييماته) ──
// العقود مفيهاش كيان "عميل" منفصل — فبنجمّع حسب customer_phone (الأكثر
// ثباتاً ووجوداً) وإلا customer_national_id، وإلا كل عقد بروفايله لوحده.
function customerKey(c: Contract): string {
  return c.customer_phone?.trim() || c.customer_national_id?.trim() || `contract-${c.id}`
}

const profileModal = reactive({
  open: false, loading: false,
  contracts: [] as Contract[],
  visits: [] as Visit[],
  reviews: [] as GuestReview[],
})

const profileCustomerName = computed(() => profileModal.contracts[0]?.customer_name ?? '')
const profileAllInstallments = computed(() =>
  profileModal.contracts.flatMap(c => (c.installments_list ?? []).map(i => ({ ...i, contract_number: c.contract_number }))),
)
const profileAllMaintenanceDues = computed(() =>
  profileModal.contracts.flatMap(c => (c.maintenance_dues_list ?? []).map(d => ({ ...d, contract_number: c.contract_number }))),
)
const profileTotals = computed(() => {
  const totals = { total_value: 0, collected: 0, overdue: 0, pending: 0 }
  for (const c of profileModal.contracts) totals.total_value += Number(c.total_value) || 0
  for (const i of profileAllInstallments.value) {
    if (i.status === 'paid') totals.collected += Number(i.paid_amount) || 0
    else if (i.status === 'overdue') totals.overdue += Number(i.amount) || 0
    else if (i.status === 'pending') totals.pending += Number(i.amount) || 0
  }
  return totals
})

async function openProfile(c: Contract) {
  const key = customerKey(c)
  profileModal.contracts = allClients.value.filter(x => customerKey(x) === key)
  profileModal.visits = []
  profileModal.reviews = []
  profileModal.open = true
  profileModal.loading = true
  try {
    const visitLists = await Promise.all(
      profileModal.contracts.map(ct =>
        api.get('/api/v1/timeshare/visits', { params: { branch_id: branchId.value, contract_id: ct.id } })
          .then(r => r.data as Visit[]).catch(() => [] as Visit[])),
    )
    profileModal.visits = visitLists.flat().sort((a, b) => b.check_in.localeCompare(a.check_in))

    // التقييمات محتاجة صلاحية manager على الباك إند — لو المستخدم أقل من
    // كده بنتخطى القسم ده بهدوء بدل ما نطلب endpoint هيرجع 403.
    if (auth.hasRole('timeshare_admin') && profileModal.visits.length) {
      const reviewLists = await Promise.all(
        profileModal.visits.map(v =>
          api.get('/api/v1/analytics/reviews', { params: { branch_id: branchId.value, timeshare_visit_id: v.id } })
            .then(r => (r.data?.items ?? []) as GuestReview[]).catch(() => [] as GuestReview[])),
      )
      profileModal.reviews = reviewLists.flat()
    }
  } catch (e) { toast.error(t('backoffice.timeshare.msg.loadProfileError')) }
  finally { profileModal.loading = false }
}

// إرسال استبيان الرضا (واتساب) لصاحب زيارة منتهية.
const sendingSurveyId = ref<number | null>(null)
const sentSurveyIds = ref<Set<number>>(new Set())

async function sendSurvey(v: Visit) {
  const ok = await confirm({
    message: t('backoffice.timeshare.confirmSendSurvey'),
    confirmText: t('backoffice.timeshare.yesSend'), cancelText: t('backoffice.timeshare.cancelAction'),
  })
  if (!ok) return
  sendingSurveyId.value = v.id
  try {
    await api.post(`/api/v1/analytics/reviews/survey-token/timeshare/${v.id}/send`, null, {
      params: { branch_id: branchId.value },
    })
    sentSurveyIds.value.add(v.id)
    toast.success(t('backoffice.timeshare.msg.surveySent'))
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.surveyError'))
  } finally {
    sendingSurveyId.value = null
  }
}

// ── Schedule Visit Modal ──────────────────────────────────────────────────
const scheduleModal = reactive({
  open: false,
  loading: false,
  contractId: undefined as number | undefined,
  checkIn: '',
  checkOut: '',
  notes: '',
  error: '',
  unitId: null as number | null,
})

function openScheduleVisit() {
  const active = profileModal.contracts.find(c => c.status === 'active') ?? profileModal.contracts[0]
  scheduleModal.contractId = active?.id ?? undefined
  scheduleModal.checkIn  = ''
  scheduleModal.checkOut = ''
  scheduleModal.notes    = ''
  scheduleModal.error    = ''
  scheduleModal.unitId   = null
  scheduleModal.open     = true
}

const contractOptions = computed<SelectOption[]>(() =>
  profileModal.contracts.map(c => ({
    value: c.id,
    label: `${c.contract_number ?? '#' + c.id} — ${c.nights_per_year ?? ''}n/yr`,
  })),
)

const scheduleModalContract = computed(() => profileModal.contracts.find(c => c.id === scheduleModal.contractId) ?? null)
watch(() => scheduleModal.contractId, () => { scheduleModal.unitId = null })

async function confirmScheduleVisit() {
  if (scheduleModal.contractId == null || !scheduleModal.checkIn || !scheduleModal.checkOut) {
    scheduleModal.error = t('backoffice.timeshare.scheduleVisit.validationError')
    return
  }
  scheduleModal.loading = true
  scheduleModal.error   = ''
  try {
    await api.post('/api/v1/timeshare/visits', {
      branch_id:   branchId.value,
      contract_id: scheduleModal.contractId!,
      check_in:    scheduleModal.checkIn,
      check_out:   scheduleModal.checkOut,
      notes:       scheduleModal.notes || undefined,
      unit_id:     scheduleModal.unitId ?? undefined,
    })
    toast.success(t('backoffice.timeshare.scheduleVisit.successToast'))
    scheduleModal.open = false
    const visitLists = await Promise.all(
      profileModal.contracts.map(ct =>
        api.get('/api/v1/timeshare/visits', { params: { branch_id: branchId.value, contract_id: ct.id } })
          .then(r => r.data as Visit[]).catch(() => [] as Visit[])),
    )
    profileModal.visits = visitLists.flat().sort((a, b) => b.check_in.localeCompare(a.check_in))
  } catch (e: unknown) {
    scheduleModal.error = (e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.scheduleVisit.errorToast')
  } finally {
    scheduleModal.loading = false
  }
}

// ── Update Visit Status ────────────────────────────────────────────────────
const updatingVisitId = ref<number | null>(null)

async function updateVisitStatus(v: Visit, newStatus: string) {
  const ok = await confirm({
    message: t('backoffice.timeshare.confirmStatusChange', {
      from: visitStatusLabel(v.status),
      to:   visitStatusLabel(newStatus),
    }),
    confirmText: t('common.save'),
    cancelText:  t('common.cancel'),
  })
  if (!ok) return
  updatingVisitId.value = v.id
  try {
    const res = await api.patch(`/api/v1/timeshare/visits/${v.id}`, { status: newStatus })
    const idx = profileModal.visits.findIndex(x => x.id === v.id)
    if (idx !== -1) profileModal.visits[idx] = { ...profileModal.visits[idx], status: (res.data as Visit).status }
    toast.success(t('backoffice.timeshare.scheduleVisit.statusUpdated'))
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.scheduleVisit.statusError'))
  } finally {
    updatingVisitId.value = null
  }
}

function nextStatuses(current: string): { status: string; label: string }[] {
  const map: Record<string, string[]> = {
    scheduled:  ['active', 'cancelled'],
    active:     ['completed', 'cancelled'],
    completed:  [],
    cancelled:  [],
  }
  return (map[current] ?? []).map(s => ({ status: s, label: visitStatusLabel(s) }))
}

// ── Pay / Maintenance Pay (سريع من صف العميل مباشرة) ───────────────────
const payModal = reactive({
  open: false, saving: false, inst_id: 0, customer_name: '', due_amount: 0,
  amount: 0, method: 'bank_transfer', receipt_number: '',
})
function openPayModal(inst: Installment) {
  Object.assign(payModal, {
    open: true, saving: false, inst_id: inst.id,
    customer_name: inst.customer_name ?? '',
    due_amount: inst.amount - inst.paid_amount,
    amount: inst.amount - inst.paid_amount, method: 'bank_transfer', receipt_number: '',
  })
}
function openPayModalForContract(c: Contract) {
  const next = c.installments_list?.find(i => i.status !== 'paid')
  if (!next) return
  openPayModal({ ...next, customer_name: c.customer_name })
}
async function submitPayment() {
  if (!payModal.amount || payModal.saving) return
  payModal.saving = true
  try {
    await api.post(`/api/v1/timeshare/installments/${payModal.inst_id}/pay`, {
      paid_amount: payModal.amount, payment_method: payModal.method,
      receipt_number: payModal.receipt_number || undefined,
    })
    payModal.open = false
    toast.success(t('backoffice.timeshare.msg.paymentRecorded'))
    await loadClients()
  } catch (e: unknown) { toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.paymentError')) }
  finally { payModal.saving = false }
}

const maintPayModal = reactive({
  open: false, saving: false, due_id: 0, customer_name: '', due_amount: 0,
  amount: 0, method: 'bank_transfer', receipt_number: '',
})
function openMaintenancePayModal(due: MaintenanceDue) {
  Object.assign(maintPayModal, {
    open: true, saving: false, due_id: due.id,
    customer_name: due.customer_name ?? '',
    due_amount: due.amount - due.paid_amount,
    amount: due.amount - due.paid_amount, method: 'bank_transfer', receipt_number: '',
  })
}
function openMaintenancePayModalForContract(c: Contract) {
  const next = c.maintenance_dues_list?.find(d => d.status !== 'paid')
  if (!next) return
  openMaintenancePayModal({ ...next, customer_name: c.customer_name })
}
async function submitMaintenancePayment() {
  if (!maintPayModal.amount || maintPayModal.saving) return
  maintPayModal.saving = true
  try {
    await api.post(`/api/v1/timeshare/maintenance-dues/${maintPayModal.due_id}/pay`, {
      paid_amount: maintPayModal.amount, payment_method: maintPayModal.method,
      receipt_number: maintPayModal.receipt_number || undefined,
    })
    maintPayModal.open = false
    toast.success(t('backoffice.timeshare.msg.paymentRecorded'))
    await loadClients()
  } catch (e: unknown) { toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.paymentError')) }
  finally { maintPayModal.saving = false }
}

// ── Status / Cancel ──────────────────────────────────────────────────────
const statusSaving = ref<number | null>(null)
async function toggleStatus(c: Contract) {
  const next = c.status === 'active' ? 'suspended' : 'active'
  statusSaving.value = c.id
  try {
    await api.patch(`/api/v1/timeshare/contracts/${c.id}`, { status: next })
    c.status = next
    toast.success(next === 'active' ? t('backoffice.timeshare.msg.contractActivated') : t('backoffice.timeshare.msg.contractSuspended'))
  } catch (e: unknown) { toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.statusChangeError')) }
  finally { statusSaving.value = null }
}

async function cancelContract(c: Contract) {
  const ok = await confirm({
    message: t('backoffice.timeshare.confirmCancelContract', { name: c.customer_name }),
    danger: true, confirmText: t('backoffice.timeshare.yesCancel'), cancelText: t('backoffice.timeshare.cancelAction'),
  })
  if (!ok) return
  try {
    await api.post(`/api/v1/timeshare/contracts/${c.id}/cancel`, { cancel_amount: 0 })
    c.status = 'cancelled'
    toast.success(t('backoffice.timeshare.msg.contractCancelled'))
  } catch (e: unknown) { toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.cancelError')) }
}

// ── #10: نقل وحدة (مقصور على نفس room_type بالتصميم) ────────────────────
const transferModal = reactive({ open: false, contract: null as Contract | null, new_unit_id: '' as number | '', reason: '', saving: false })

function openTransferModal(c: Contract) {
  transferModal.contract = c
  transferModal.new_unit_id = ''
  transferModal.reason = ''
  transferModal.open = true
}

const transferCandidateUnits = computed(() => {
  if (!transferModal.contract) return []
  return units.value.filter(u =>
    u.unit_type === transferModal.contract!.room_type &&
    u.id !== transferModal.contract!.unit_id &&
    u.status !== 'maintenance',
  )
})

async function saveTransfer() {
  if (!transferModal.contract) return
  if (!transferModal.new_unit_id) { toast.error(t('backoffice.timeshare.msg.selectNewUnit')); return }
  if (!transferModal.reason.trim() || transferModal.reason.trim().length < 3) {
    toast.error(t('backoffice.timeshare.msg.transferReasonRequired')); return
  }
  transferModal.saving = true
  try {
    const { data } = await api.post(`/api/v1/timeshare/contracts/${transferModal.contract.id}/transfer-unit`, {
      new_unit_id: transferModal.new_unit_id, reason: transferModal.reason,
    })
    transferModal.contract.unit_id = data.unit_id
    toast.success(t('backoffice.timeshare.msg.unitTransferred'))
    transferModal.open = false
  } catch (e: unknown) {
    toast.error((e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.transferError'))
  } finally {
    transferModal.saving = false
  }
}

// ── قائمة الانتظار — إضافة عميل لعقد لقائمة الانتظار (زرار في صف العميل) ──
const newWaitlistModal = ref(false)
const newWaitlistContract = ref<Contract | null>(null)
const newWaitlistForm = ref({ requested_start: '', requested_end: '' })
const savingWaitlist = ref(false)

function openNewWaitlistModal(c: Contract) {
  newWaitlistContract.value = c
  newWaitlistForm.value = { requested_start: '', requested_end: '' }
  newWaitlistModal.value = true
}

async function submitNewWaitlist() {
  if (!newWaitlistContract.value) return
  if (!newWaitlistForm.value.requested_start || !newWaitlistForm.value.requested_end) {
    toast.error(t('backoffice.timeshare.msg.waitlistDatesRequired'))
    return
  }
  savingWaitlist.value = true
  try {
    await api.post('/api/v1/timeshare/waitlist', {
      branch_id: branchId.value,
      contract_id: newWaitlistContract.value.id,
      requested_start: newWaitlistForm.value.requested_start,
      requested_end: newWaitlistForm.value.requested_end,
    })
    toast.success(t('backoffice.timeshare.msg.waitlistAdded'))
    newWaitlistModal.value = false
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? t('backoffice.timeshare.msg.waitlistSaveError'))
  } finally { savingWaitlist.value = false }
}

// ── تحميل PDF العقد ──────────────────────────────────────────────────────
const downloadingPdfId = ref<number | null>(null)
async function downloadContractPdf(c: Contract) {
  downloadingPdfId.value = c.id
  try {
    const res = await api.get(`/api/v1/timeshare/contracts/${c.id}/pdf`, { responseType: 'blob' })
    const url = URL.createObjectURL(res.data)
    const a = document.createElement('a')
    a.href = url
    a.download = `timeshare-${c.contract_number}.pdf`
    a.click()
    setTimeout(() => URL.revokeObjectURL(url), 5000)
  } catch { toast.error(t('backoffice.timeshare.msg.pdfError')) } finally { downloadingPdfId.value = null }
}

// ── استيراد عقود من Excel ────────────────────────────────────────────────
const importModal = reactive({ open: false, uploading: false, result: null as ImportResult | null, file: null as File | null })
function onFilePicked(e: Event) {
  const target = e.target as HTMLInputElement
  importModal.file = target.files?.[0] ?? null
}
async function submitImport() {
  if (!importModal.file || importModal.uploading) return
  importModal.uploading = true
  try {
    const form = new FormData()
    form.append('file', importModal.file)
    const r = await api.post('/api/v1/timeshare/contracts/import-excel', form, {
      headers: { 'Content-Type': 'multipart/form-data' }, params: { branch_id: branchId.value },
    })
    importModal.result = r.data
    await loadClients()
  } catch (e: unknown) {
    const msg = (e as ApiErr)?.response?.data?.detail ?? t('backoffice.timeshare.msg.importError')
    importModal.result = { error: msg }
    toast.error(msg)
  } finally { importModal.uploading = false }
}

onMounted(() => { loadClients(); loadUnits() })
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap gap-3 items-center justify-between">
      <div class="flex flex-wrap gap-3 flex-1">
        <div class="flex-1 min-w-64">
          <SearchInput v-model="clientSearch" :placeholder="t('backoffice.timeshare.searchClientsPlaceholder')" :clear-label="t('backoffice.timeshare.clearClientSearch')" />
        </div>
        <select v-model="clientStatusFilter" :aria-label="t('backoffice.timeshare.filterByStatus')" class="min-h-[44px] bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2.5 outline-none">
          <option value="">{{ t('backoffice.timeshare.allStatuses') }}</option>
          <option value="active">{{ t('backoffice.timeshare.contractStatus.active') }}</option>
          <option value="suspended">{{ t('backoffice.timeshare.contractStatus.suspended') }}</option>
          <option value="cancelled">{{ t('backoffice.timeshare.contractStatus.cancelled') }}</option>
        </select>
        <select v-model="clientRoomFilter" :aria-label="t('backoffice.timeshare.filterByRoomType')" class="min-h-[44px] bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-700 dark:text-gray-300 text-sm rounded-xl px-3 py-2.5 outline-none">
          <option value="">{{ t('backoffice.timeshare.allTypes') }}</option>
          <option value="Studio">Studio</option><option value="Chalet">Chalet</option>
        </select>
      </div>
      <AppButton
        v-if="auth.hasRole('timeshare_admin')"
        variant="outline"
        @click="importModal.open = true; importModal.result = null"
      >
        <AppIcon name="upload" size="sm" /> {{ t('backoffice.timeshare.importExcel') }}
      </AppButton>
    </div>

    <LoadingState v-if="clientsLoading" :label="t('backoffice.timeshare.loadingClients')" />
    <div v-else class="space-y-2">
      <EmptyState v-if="!filteredClients.length" icon="👤" :title="t('backoffice.timeshare.noResults')" />
      <div v-for="c in filteredClients" :key="c.id"
        class="bg-white dark:bg-surface rounded-2xl border overflow-hidden transition-all shadow-sm"
        :class="expandedClient === c.id ? 'border-primary-300' : 'border-stone-200 dark:border-border hover:border-stone-300'">

        <div
          class="p-4 cursor-pointer flex items-center gap-4 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-primary-500"
          role="button"
          tabindex="0"
          :aria-expanded="expandedClient === c.id"
          @click="expandedClient = expandedClient === c.id ? null : c.id"
          @keydown.enter="expandedClient = expandedClient === c.id ? null : c.id"
          @keydown.space.prevent="expandedClient = expandedClient === c.id ? null : c.id"
        >
          <div class="w-9 h-9 rounded-xl flex-shrink-0 flex items-center justify-center text-sm font-black" :class="roomTypeBadge(c.room_type)">
            {{ c.customer_name?.charAt(0) || '?' }}
          </div>
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
              <span class="font-bold text-sm text-gray-900 dark:text-gray-100">{{ c.customer_name }}</span>
              <span :class="roomTypeBadge(c.room_type)">{{ roomTypeLabel(c.room_type) }}</span>
              <span v-if="c.rci_included" class="text-xs px-2 py-1 rounded-full bg-purple-100 text-purple-700 dark:bg-purple-950/60 dark:text-purple-300 font-bold">RCI</span>
              <AppBadge size="sm" :variant="contractStatusVariant[c.status] ?? 'neutral'">{{ statusLabel(c.status) }}</AppBadge>
            </div>
            <div class="text-xs text-gray-500 dark:text-gray-400 mt-1 flex flex-wrap gap-3">
              <span v-if="c.customer_phone">📞 {{ c.customer_phone }}</span>
              <span>{{ t('backoffice.timeshare.weekNumber', { week: c.week_number || '—' }) }}</span>
              <span>{{ c.contract_number }}</span>
            </div>
          </div>
          <div class="text-end flex-shrink-0 hidden sm:block">
            <div class="text-sm font-black text-green-600 dark:text-green-300">{{ fmt(c.total_value) }}</div>
          </div>
          <button @click.stop="openProfile(c)"
            class="flex-shrink-0 min-h-[44px] px-3 py-2 rounded-xl bg-primary-50 text-primary-700 dark:bg-primary-950/40 dark:text-primary-300 text-xs font-bold border border-primary-200 dark:border-primary-800 hover:bg-primary-100 dark:hover:bg-primary-950/60">
            👤 {{ t('backoffice.timeshare.fullProfile') }}
          </button>
          <div class="text-gray-500 dark:text-gray-400 text-xs flex-shrink-0">{{ expandedClient === c.id ? '▲' : '▼' }}</div>
        </div>

        <div v-if="expandedClient === c.id" class="border-t border-stone-100 dark:border-border/50 p-4 space-y-4">
          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
            <div class="space-y-1.5">
              <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-2">{{ t('backoffice.timeshare.contractData') }}</p>
              <div class="flex justify-between gap-3"><span class="text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.contractDuration') }}</span><span>{{ formatDateValue(c.start_date) }} — {{ formatDateValue(c.end_date ?? undefined) }}</span></div>
              <div class="flex justify-between gap-3"><span class="text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.nightsPerYear') }}</span><span class="font-bold text-amber-600 dark:text-amber-300">{{ c.nights_per_year }}</span></div>
              <div v-if="c.nationality" class="flex justify-between gap-3"><span class="text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.nationality') }}</span><span>{{ c.nationality }}</span></div>
              <div v-if="c.maintenance_fee > 0" class="flex justify-between gap-3"><span class="text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.annualMaintenance') }}</span><span class="text-amber-600 dark:text-amber-300">{{ fmt(c.maintenance_fee) }}</span></div>
            </div>
            <div class="space-y-1.5">
              <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-2">{{ t('backoffice.timeshare.financialStatus') }}</p>
              <div class="flex justify-between gap-3"><span class="text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.contractValue') }}</span><span class="font-bold text-green-600 dark:text-green-300">{{ fmt(c.total_value) }}</span></div>
              <div class="flex justify-between gap-3"><span class="text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.downPayment') }}</span><span>{{ fmt(c.down_payment) }}</span></div>
              <div class="flex justify-between gap-3"><span class="text-gray-500 dark:text-gray-400">{{ t('backoffice.timeshare.installmentCount') }}</span><span>{{ c.installments }}</span></div>
            </div>
          </div>

          <div>
            <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-2">{{ t('backoffice.timeshare.installmentSchedule') }}</p>
            <div v-if="c.installments_list?.length" class="overflow-x-auto">
              <table class="w-full min-w-[520px] text-xs">
                <thead><tr class="text-gray-500 dark:text-gray-400 border-b border-stone-100 dark:border-border/50">
                  <th class="text-start py-2 ps-1">#</th><th class="text-start py-2">{{ t('backoffice.timeshare.column.dueDate') }}</th>
                  <th class="text-start py-2">{{ t('backoffice.timeshare.column.amount') }}</th><th class="text-start py-2">{{ t('backoffice.timeshare.column.status') }}</th><th></th>
                </tr></thead>
                <tbody class="divide-y divide-stone-100">
                  <tr v-for="(p, i) in c.installments_list" :key="p.id">
                    <td class="py-2 ps-1 text-gray-500 dark:text-gray-400">{{ i + 1 }}</td>
                    <td class="py-2 text-gray-600 dark:text-gray-300">{{ formatDateValue(p.due_date) }}</td>
                    <td class="py-1.5 font-bold">{{ fmt(p.amount) }}</td>
                    <td class="py-1.5"><AppBadge size="sm" :variant="payStatusVariant[p.status] ?? 'neutral'">{{ payLabel(p.status) }}</AppBadge></td>
                    <td class="py-1.5">
                      <button v-if="p.status !== 'paid' && canCollectInstallments" @click="openPayModal({ ...p, customer_name: c.customer_name })"
                        class="min-h-[44px] px-3 py-2 rounded-lg bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300 text-xs font-bold border border-green-200 dark:border-green-800 hover:bg-green-100 dark:hover:bg-green-950/60">{{ t('backoffice.timeshare.pay') }}</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div v-if="c.maintenance_dues_list?.length">
            <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-2">{{ t('backoffice.timeshare.maintenanceDuesSchedule') }}</p>
            <div class="overflow-x-auto">
              <table class="w-full min-w-[520px] text-xs">
                <thead><tr class="text-gray-500 dark:text-gray-400 border-b border-stone-100 dark:border-border/50">
                  <th class="text-start py-2 ps-1">{{ t('backoffice.timeshare.column.year') }}</th><th class="text-start py-2">{{ t('backoffice.timeshare.column.dueDate') }}</th>
                  <th class="text-start py-2">{{ t('backoffice.timeshare.column.amount') }}</th><th class="text-start py-2">{{ t('backoffice.timeshare.column.status') }}</th><th></th>
                </tr></thead>
                <tbody class="divide-y divide-stone-100">
                  <tr v-for="d in c.maintenance_dues_list" :key="d.id">
                    <td class="py-2 ps-1 text-gray-500 dark:text-gray-400">{{ d.fee_year }}</td>
                    <td class="py-2 text-gray-600 dark:text-gray-300">{{ formatDateValue(d.due_date) }}</td>
                    <td class="py-1.5 font-bold">{{ fmt(d.amount) }}</td>
                    <td class="py-1.5"><AppBadge size="sm" :variant="payStatusVariant[d.status] ?? 'neutral'">{{ payLabel(d.status) }}</AppBadge></td>
                    <td class="py-1.5">
                      <button v-if="d.status !== 'paid' && canCollectMaintenance" @click="openMaintenancePayModal({ ...d, customer_name: c.customer_name })"
                        class="min-h-[44px] px-3 py-2 rounded-lg bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300 text-xs font-bold border border-green-200 dark:border-green-800 hover:bg-green-100 dark:hover:bg-green-950/60">{{ t('backoffice.timeshare.pay') }}</button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          <div class="flex flex-wrap gap-2 pt-2 border-t border-stone-100 dark:border-border/50">
            <button v-if="canCollectInstallments" @click="openPayModalForContract(c)" class="min-h-[44px] px-4 py-2 rounded-xl bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300 text-sm font-bold border border-green-200 dark:border-green-800 hover:bg-green-100 dark:hover:bg-green-950/60">💰 {{ t('backoffice.timeshare.recordPayment') }}</button>
            <button v-if="canCollectMaintenance && c.maintenance_dues_list?.some(d => d.status !== 'paid')" @click="openMaintenancePayModalForContract(c)" class="min-h-[44px] px-4 py-2 rounded-xl bg-teal-50 text-teal-700 dark:bg-teal-950/40 dark:text-teal-300 text-sm font-bold border border-teal-200 dark:border-teal-800 hover:bg-teal-100 dark:hover:bg-teal-950/60">🛠️ {{ t('backoffice.timeshare.recordMaintenancePayment') }}</button>
            <a v-if="c.customer_phone" :href="`tel:${c.customer_phone}`" class="min-h-[44px] inline-flex items-center px-4 py-2 rounded-xl bg-sky-50 text-sky-700 dark:bg-sky-950/40 dark:text-sky-300 text-sm font-bold border border-sky-200 dark:border-sky-800 hover:bg-sky-100 dark:hover:bg-sky-950/60">📞 {{ t('backoffice.timeshare.call') }}</a>
            <button @click="downloadContractPdf(c)" :disabled="downloadingPdfId === c.id"
              class="min-h-[44px] px-4 py-2 rounded-xl bg-stone-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300 text-sm font-bold border border-stone-200 dark:border-border hover:bg-stone-200 dark:hover:bg-gray-700 disabled:opacity-40">📄 {{ downloadingPdfId === c.id ? t('backoffice.timeshare.saving') : t('backoffice.timeshare.downloadPdf') }}</button>
            <button v-if="auth.hasRole('timeshare_admin') && c.status === 'active'" @click="toggleStatus(c)" :disabled="statusSaving === c.id"
              class="min-h-[44px] px-4 py-2 rounded-xl bg-yellow-50 text-yellow-700 dark:bg-yellow-950/40 dark:text-yellow-300 text-sm font-bold border border-yellow-200 dark:border-yellow-800 hover:bg-yellow-100 dark:hover:bg-yellow-950/60 disabled:opacity-40">⏸️ {{ t('backoffice.timeshare.suspend') }}</button>
            <button v-else-if="auth.hasRole('timeshare_admin') && c.status === 'suspended'" @click="toggleStatus(c)" :disabled="statusSaving === c.id"
              class="min-h-[44px] px-4 py-2 rounded-xl bg-green-50 text-green-700 dark:bg-green-950/40 dark:text-green-300 text-sm font-bold border border-green-200 dark:border-green-800 hover:bg-green-100 dark:hover:bg-green-950/60 disabled:opacity-40">▶️ {{ t('backoffice.timeshare.activate') }}</button>
            <button v-if="auth.hasRole('timeshare_admin') && c.unit_id && !['cancelled','expired'].includes(c.status)" @click="openTransferModal(c)"
              class="min-h-[44px] px-4 py-2 rounded-xl bg-violet-50 text-violet-700 dark:bg-violet-950/40 dark:text-violet-300 text-sm font-bold border border-violet-200 dark:border-violet-800 hover:bg-violet-100 dark:hover:bg-violet-950/60">🔑 {{ t('backoffice.timeshare.transferUnit') }}</button>
            <button v-if="canAddWaitlist && !['cancelled','expired'].includes(c.status)" @click="openNewWaitlistModal(c)"
              class="min-h-[44px] px-4 py-2 rounded-xl bg-indigo-50 text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300 text-sm font-bold border border-indigo-200 dark:border-indigo-800 hover:bg-indigo-100 dark:hover:bg-indigo-950/60">⏳ {{ t('backoffice.timeshare.joinWaitlist') }}</button>
            <AppButton v-if="auth.hasRole('timeshare_admin') && c.status !== 'cancelled'" variant="danger" class="min-h-[44px]" @click="cancelContract(c)">🗑️ {{ t('backoffice.timeshare.cancelAction') }}</AppButton>
          </div>
        </div>
      </div>
    </div>

    <!-- ══ IMPORT MODAL ══ -->
    <AppModal v-if="auth.hasRole('timeshare_admin')" :open="importModal.open" :title="`📥 ${t('backoffice.timeshare.importContractsTitle')}`" @close="importModal.open = false">
      <p class="text-sm text-gray-600 dark:text-gray-300 mb-4">
        {{ t('backoffice.timeshare.importHint') }}
      </p>
      <input type="file" accept=".xlsx,.xls" @change="onFilePicked"
        class="min-h-[44px] w-full text-sm text-gray-700 dark:text-gray-300 file:me-3 file:py-2 file:px-4 file:rounded-xl file:border-0 file:bg-primary-50 dark:file:bg-primary-950/40 file:text-primary-700 dark:file:text-primary-300 file:font-bold" />
      <div v-if="importModal.result" class="mt-4 p-3 rounded-xl text-sm" :class="importModal.result.error ? 'bg-red-50 dark:bg-red-950/30 text-red-700 dark:text-red-300' : 'bg-green-50 dark:bg-green-950/30 text-green-700 dark:text-green-300'">
        <div v-if="importModal.result.error">{{ importModal.result.error }}</div>
        <div v-else>
          ✅ {{ t('backoffice.timeshare.importedCount', { count: importModal.result.imported }) }}
          <span v-if="importModal.result.skipped"> · {{ t('backoffice.timeshare.skippedCount', { count: importModal.result.skipped }) }}</span>
          <div v-if="importModal.result.errors?.length" class="mt-2 text-red-500">
            <div v-for="(err, i) in importModal.result.errors" :key="i">{{ err }}</div>
          </div>
        </div>
      </div>
      <template #footer>
        <div class="flex gap-3">
          <AppButton variant="primary" block :loading="importModal.uploading" :disabled="!importModal.file" @click="submitImport">
            📤 {{ t('backoffice.timeshare.importAction') }}
          </AppButton>
          <AppButton variant="ghost" @click="importModal.open = false">{{ t('backoffice.timeshare.close') }}</AppButton>
        </div>
      </template>
    </AppModal>

    <!-- ══ CUSTOMER PROFILE ══ -->
    <AppModal :open="profileModal.open" :title="t('backoffice.timeshare.fullProfileTitle', { name: profileCustomerName })" size="lg" @close="profileModal.open = false">
      <LoadingState v-if="profileModal.loading" :label="t('backoffice.timeshare.loadingProfile')" />
      <div v-else class="space-y-5 text-sm">
        <!-- Totals -->
        <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <div class="bg-stone-50 dark:bg-gray-800/60 rounded-xl p-3">
            <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-1">{{ t('backoffice.timeshare.contractCount') }}</p>
            <p class="font-black text-gray-900 dark:text-gray-100">{{ profileModal.contracts.length }}</p>
          </div>
          <div class="bg-green-50 dark:bg-green-950/30 rounded-xl p-3">
            <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-1">{{ t('backoffice.timeshare.collected') }}</p>
            <p class="font-black text-green-600 dark:text-green-300">{{ fmt(profileTotals.collected) }}</p>
          </div>
          <div class="bg-red-50 dark:bg-red-950/30 rounded-xl p-3">
            <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-1">{{ t('backoffice.timeshare.overdue') }}</p>
            <p class="font-black text-red-600 dark:text-red-300">{{ fmt(profileTotals.overdue) }}</p>
          </div>
          <div class="bg-amber-50 dark:bg-amber-950/30 rounded-xl p-3">
            <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-1">{{ t('backoffice.timeshare.pending') }}</p>
            <p class="font-black text-amber-600 dark:text-amber-300">{{ fmt(profileTotals.pending) }}</p>
          </div>
        </div>

        <!-- Contracts -->
        <div>
          <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-2">{{ t('backoffice.timeshare.contractsCount', { count: profileModal.contracts.length }) }}</p>
          <div class="space-y-1.5">
            <div v-for="c in profileModal.contracts" :key="c.id" class="flex items-center justify-between gap-2 p-2.5 rounded-xl bg-stone-50 dark:bg-gray-800/60 border border-stone-100 dark:border-border/50">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-bold text-gray-900 dark:text-gray-100">{{ c.contract_number }}</span>
                <span :class="roomTypeBadge(c.room_type)">{{ roomTypeLabel(c.room_type) }}</span>
                <AppBadge size="sm" :variant="contractStatusVariant[c.status] ?? 'neutral'">{{ statusLabel(c.status) }}</AppBadge>
              </div>
              <span class="font-bold text-green-600 dark:text-green-300">{{ fmt(c.total_value) }}</span>
            </div>
          </div>
        </div>

        <!-- Visits -->
        <div>
          <div class="flex items-center justify-between mb-2">
            <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase">{{ t('backoffice.timeshare.visitsCount', { count: profileModal.visits.length }) }}</p>
            <AppButton
              v-if="canScheduleVisits"
              size="sm" variant="primary"
              @click="openScheduleVisit"
            >📅 {{ t('backoffice.timeshare.scheduleVisit.btnLabel') }}</AppButton>
          </div>
          <EmptyState v-if="!profileModal.visits.length" icon="🏝️" :title="t('backoffice.timeshare.noVisitsRecorded')" />
          <div v-else class="space-y-1.5">
            <div v-for="v in profileModal.visits" :key="v.id" class="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 rounded-xl bg-sky-50 dark:bg-sky-950/30 border border-sky-100 dark:border-sky-900/60">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="font-bold text-gray-900 dark:text-gray-100">🔑 {{ v.unit_id ? (unitNumberById[v.unit_id] ?? t('backoffice.timeshare.unitHash', { id: v.unit_id })) : '—' }}</span>
                <span class="text-gray-500 dark:text-gray-400">{{ formatDateValue(v.check_in) }} → {{ formatDateValue(v.check_out) }}</span>
              </div>
              <div class="flex items-center gap-2 flex-wrap">
                <template v-if="canEditVisits && nextStatuses(v.status).length">
                  <AppButton
                    v-for="ns in nextStatuses(v.status)" :key="ns.status"
                    size="sm" variant="ghost"
                    :loading="updatingVisitId === v.id"
                    @click="updateVisitStatus(v, ns.status)"
                  >{{ ns.label }}</AppButton>
                </template>
                <AppButton
                  v-if="auth.hasRole('timeshare_admin') && v.status === 'completed' && !sentSurveyIds.has(v.id)"
                  size="sm" variant="ghost" :loading="sendingSurveyId === v.id"
                  @click="sendSurvey(v)"
                >📨 {{ t('backoffice.timeshare.satisfactionSurvey') }}</AppButton>
                <span v-else-if="sentSurveyIds.has(v.id)" class="text-xs text-green-600 dark:text-green-300 font-bold">✓ {{ t('backoffice.timeshare.sentDone') }}</span>
                <AppBadge size="sm" :variant="visitStatusVariant[v.status] ?? 'neutral'">{{ visitStatusLabel(v.status) }}</AppBadge>
              </div>
            </div>
          </div>
        </div>

        <!-- Installments across all contracts -->
        <div>
          <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-2">{{ t('backoffice.timeshare.installmentsCount', { count: profileAllInstallments.length }) }}</p>
          <EmptyState v-if="!profileAllInstallments.length" icon="💰" :title="t('backoffice.timeshare.noInstallments')" />
          <div v-else class="overflow-x-auto">
          <table class="w-full min-w-[520px] text-xs">
            <thead><tr class="text-gray-500 dark:text-gray-400 border-b border-stone-100 dark:border-border/50">
              <th class="text-start py-2 ps-1">{{ t('backoffice.timeshare.column.contract') }}</th><th class="text-start py-2">{{ t('backoffice.timeshare.column.dueDate') }}</th>
              <th class="text-start py-2">{{ t('backoffice.timeshare.column.amount') }}</th><th class="text-start py-2">{{ t('backoffice.timeshare.column.status') }}</th>
            </tr></thead>
            <tbody class="divide-y divide-stone-100 dark:divide-border">
              <tr v-for="p in profileAllInstallments" :key="p.id">
                <td class="py-2 ps-1 text-gray-500 dark:text-gray-400">{{ p.contract_number }}</td>
                <td class="py-2 text-gray-600 dark:text-gray-300">{{ formatDateValue(p.due_date) }}</td>
                <td class="py-2 font-bold">{{ fmt(p.amount) }}</td>
                <td class="py-2"><AppBadge size="sm" :variant="payStatusVariant[p.status] ?? 'neutral'">{{ payLabel(p.status) }}</AppBadge></td>
              </tr>
            </tbody>
          </table>
          </div>
        </div>

        <!-- Maintenance dues across all contracts -->
        <div>
          <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-2">{{ t('backoffice.timeshare.maintenanceDuesCount', { count: profileAllMaintenanceDues.length }) }}</p>
          <EmptyState v-if="!profileAllMaintenanceDues.length" icon="🛠️" :title="t('backoffice.timeshare.noMaintenanceDues')" />
          <div v-else class="overflow-x-auto">
          <table class="w-full min-w-[520px] text-xs">
            <thead><tr class="text-gray-500 dark:text-gray-400 border-b border-stone-100 dark:border-border/50">
              <th class="text-start py-2 ps-1">{{ t('backoffice.timeshare.column.contract') }}</th><th class="text-start py-2">{{ t('backoffice.timeshare.column.year') }}</th>
              <th class="text-start py-2">{{ t('backoffice.timeshare.column.amount') }}</th><th class="text-start py-2">{{ t('backoffice.timeshare.column.status') }}</th>
            </tr></thead>
            <tbody class="divide-y divide-stone-100 dark:divide-border">
              <tr v-for="d in profileAllMaintenanceDues" :key="d.id">
                <td class="py-2 ps-1 text-gray-500 dark:text-gray-400">{{ d.contract_number }}</td>
                <td class="py-2 text-gray-600 dark:text-gray-300">{{ d.fee_year }}</td>
                <td class="py-2 font-bold">{{ fmt(d.amount) }}</td>
                <td class="py-2"><AppBadge size="sm" :variant="payStatusVariant[d.status] ?? 'neutral'">{{ payLabel(d.status) }}</AppBadge></td>
              </tr>
            </tbody>
          </table>
          </div>
        </div>

        <!-- Reviews (manager فقط) -->
        <div v-if="auth.hasRole('timeshare_admin')">
          <p class="text-xs text-gray-500 dark:text-gray-400 font-bold uppercase mb-2">{{ t('backoffice.timeshare.reviewsCount', { count: profileModal.reviews.length }) }}</p>
          <EmptyState v-if="!profileModal.reviews.length" icon="⭐" :title="t('backoffice.timeshare.noReviewsRecorded')" />
          <div v-else class="space-y-1.5">
            <div v-for="r in profileModal.reviews" :key="r.id" class="p-3 rounded-xl bg-amber-50 dark:bg-amber-950/30 border border-amber-100 dark:border-amber-900/60">
              <div class="flex items-center justify-between mb-1">
                <span class="font-bold text-amber-600 dark:text-amber-300">{{ '⭐'.repeat(r.overall_rating) }}</span>
                <span class="text-gray-500 dark:text-gray-400 text-xs">{{ formatDateValue(r.reviewed_at) }}</span>
              </div>
              <p v-if="r.comment" class="text-gray-700 dark:text-gray-300">{{ r.comment }}</p>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <AppButton variant="ghost" block @click="profileModal.open = false">{{ t('backoffice.timeshare.close') }}</AppButton>
      </template>
    </AppModal>

    <!-- ── Schedule Visit Modal ──────────────────────────────────────────── -->
    <AppModal
      v-model:open="scheduleModal.open"
      :title="t('backoffice.timeshare.scheduleVisit.title')"
      max-width="sm"
      @close="scheduleModal.open = false"
    >
      <div class="space-y-4">
        <div v-if="profileModal.contracts.length > 1">
          <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
            {{ t('backoffice.timeshare.scheduleVisit.contract') }}
          </label>
          <AppSelect
            v-model="scheduleModal.contractId"
            :options="contractOptions"
            :placeholder="t('backoffice.timeshare.scheduleVisit.selectContract')"
          />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
            {{ t('backoffice.timeshare.scheduleVisit.checkIn') }}
          </label>
          <AppInput v-model="scheduleModal.checkIn" type="date" />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
            {{ t('backoffice.timeshare.scheduleVisit.checkOut') }}
          </label>
          <AppInput v-model="scheduleModal.checkOut" type="date" :min="scheduleModal.checkIn" />
        </div>
        <div>
          <label class="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">
            {{ t('backoffice.timeshare.scheduleVisit.notes') }}
          </label>
          <AppInput v-model="scheduleModal.notes" :placeholder="t('backoffice.timeshare.scheduleVisit.notesPlaceholder')" />
        </div>
        <TimeshareUnitPicker
          v-model="scheduleModal.unitId"
          :branch-id="branchId"
          :unit-type="scheduleModalContract?.room_type ?? ''"
          :check-in="scheduleModal.checkIn"
          :check-out="scheduleModal.checkOut"
          :contract-unit-id="scheduleModalContract?.unit_id ?? null"
          :unit-capacity="scheduleModalContract?.unit_capacity ?? null"
        />
        <p v-if="scheduleModal.error" class="text-sm text-red-600 dark:text-red-400">{{ scheduleModal.error }}</p>
      </div>
      <template #footer>
        <div class="flex gap-2 justify-end">
          <AppButton variant="ghost" @click="scheduleModal.open = false">{{ t('common.cancel') }}</AppButton>
          <AppButton variant="primary" :loading="scheduleModal.loading" @click="confirmScheduleVisit">
            {{ t('backoffice.timeshare.scheduleVisit.confirm') }}
          </AppButton>
        </div>
      </template>
    </AppModal>

    <!-- ══ NEW WAITLIST ENTRY MODAL ══ -->
    <AppModal :open="newWaitlistModal" :title="`⏳ ${t('backoffice.timeshare.joinWaitlist')}`" size="sm" @close="newWaitlistModal = false">
      <div v-if="newWaitlistContract" class="space-y-3">
        <p class="text-sm text-gray-600 dark:text-gray-300">{{ newWaitlistContract.customer_name }} — {{ newWaitlistContract.contract_number }}</p>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.timeshare.scheduleVisit.checkIn') }}
          <input v-model="newWaitlistForm.requested_start" type="date" class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300">{{ t('backoffice.timeshare.scheduleVisit.checkOut') }}
          <input v-model="newWaitlistForm.requested_end" type="date" class="min-h-[44px] w-full mt-1 bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        </label>
        <AppButton class="w-full min-h-[44px]" :disabled="savingWaitlist" @click="submitNewWaitlist">{{ savingWaitlist ? t('backoffice.timeshare.saving') : t('backoffice.timeshare.save') }}</AppButton>
      </div>
    </AppModal>

    <!-- ══ TRANSFER UNIT MODAL (#10) ══ -->
    <AppModal :open="transferModal.open" :title="`🔑 ${t('backoffice.timeshare.transferUnit')}`" size="sm" @close="transferModal.open = false">
      <div v-if="transferModal.contract" class="space-y-3">
        <p class="text-sm text-gray-600 dark:text-gray-300">
          {{ transferModal.contract.customer_name }} — {{ t('backoffice.timeshare.currentUnit') }}:
          <span class="font-bold">{{ transferModal.contract.unit_id ? (unitNumberById[transferModal.contract.unit_id] ?? `#${transferModal.contract.unit_id}`) : '—' }}</span>
        </p>
        <select v-model="transferModal.new_unit_id" class="min-h-[44px] w-full bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm">
          <option value="">{{ t('backoffice.timeshare.selectNewUnitOfType', { type: roomTypeLabel(transferModal.contract.room_type) }) }}</option>
          <option v-for="u in transferCandidateUnits" :key="u.id" :value="u.id" :disabled="u.status === 'maintenance'">
            {{ u.unit_number }}{{ u.status === 'maintenance' ? ` (${t('backoffice.timeshare.underMaintenance')})` : '' }}
          </option>
        </select>
        <p v-if="transferCandidateUnits.length === 0" class="text-xs text-amber-600 dark:text-amber-300">{{ t('backoffice.timeshare.noCandidateUnits') }}</p>
        <input v-model="transferModal.reason" type="text" :placeholder="t('backoffice.timeshare.transferReasonPlaceholder')"
          class="min-h-[44px] w-full bg-white dark:bg-surface border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 rounded-xl px-3 py-2 text-sm" />
        <AppButton class="w-full" :loading="transferModal.saving" @click="saveTransfer">{{ t('backoffice.timeshare.confirmTransfer') }}</AppButton>
      </div>
    </AppModal>

    <!-- ══ PAY MODAL ══ -->
    <AppModal :open="payModal.open" :title="`💰 ${t('backoffice.timeshare.recordPayment')}`" size="sm" @close="payModal.open = false">
      <p class="text-sm text-gray-600 dark:text-gray-300 mb-4">{{ payModal.customer_name }}</p>
      <div class="space-y-3">
        <div>
          <label class="text-xs text-gray-600 dark:text-gray-300 font-semibold block mb-1">{{ t('backoffice.timeshare.amountPaid') }}</label>
          <input v-model.number="payModal.amount" type="number" min="1" :placeholder="t('backoffice.timeshare.duePlaceholder', { amount: fmt(payModal.due_amount) })"
            class="min-h-[44px] w-full bg-stone-50 dark:bg-gray-800/60 border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 text-sm rounded-xl px-4 py-2.5 outline-none focus:border-primary-500" />
        </div>
        <div>
          <label class="text-xs text-gray-600 dark:text-gray-300 font-semibold block mb-1">{{ t('backoffice.timeshare.paymentMethod') }}</label>
          <select v-model="payModal.method" class="min-h-[44px] w-full bg-stone-50 dark:bg-gray-800/60 border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 text-sm rounded-xl px-4 py-2.5 outline-none">
            <option value="bank_transfer">{{ t('backoffice.timeshare.paymentMethodBankTransfer') }}</option><option value="card">{{ t('backoffice.timeshare.paymentMethodCard') }}</option>
          </select>
        </div>
        <div>
          <label class="text-xs text-gray-600 dark:text-gray-300 font-semibold block mb-1">{{ t('backoffice.timeshare.receiptNumberOptional') }}</label>
          <input v-model="payModal.receipt_number" class="min-h-[44px] w-full bg-stone-50 dark:bg-gray-800/60 border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 text-sm rounded-xl px-4 py-2.5 outline-none" />
        </div>
      </div>
      <template #footer>
        <div class="flex gap-3">
          <AppButton variant="primary" block :loading="payModal.saving" :disabled="!payModal.amount" @click="submitPayment">
            ✅ {{ t('backoffice.timeshare.confirmPayment') }}
          </AppButton>
          <AppButton variant="ghost" @click="payModal.open = false">{{ t('backoffice.timeshare.cancelAction') }}</AppButton>
        </div>
      </template>
    </AppModal>

    <!-- ══ MAINTENANCE PAY MODAL ══ -->
    <AppModal :open="maintPayModal.open" :title="`🛠️ ${t('backoffice.timeshare.recordMaintenancePayment')}`" size="sm" @close="maintPayModal.open = false">
      <p class="text-sm text-gray-600 dark:text-gray-300 mb-4">{{ maintPayModal.customer_name }}</p>
      <div class="space-y-3">
        <div>
          <label class="text-xs text-gray-600 dark:text-gray-300 font-semibold block mb-1">{{ t('backoffice.timeshare.amountPaid') }}</label>
          <input v-model.number="maintPayModal.amount" type="number" min="1" :placeholder="t('backoffice.timeshare.duePlaceholder', { amount: fmt(maintPayModal.due_amount) })"
            class="min-h-[44px] w-full bg-stone-50 dark:bg-gray-800/60 border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 text-sm rounded-xl px-4 py-2.5 outline-none focus:border-primary-500" />
        </div>
        <div>
          <label class="text-xs text-gray-600 dark:text-gray-300 font-semibold block mb-1">{{ t('backoffice.timeshare.paymentMethod') }}</label>
          <select v-model="maintPayModal.method" class="min-h-[44px] w-full bg-stone-50 dark:bg-gray-800/60 border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 text-sm rounded-xl px-4 py-2.5 outline-none">
            <option value="bank_transfer">{{ t('backoffice.timeshare.paymentMethodBankTransfer') }}</option><option value="card">{{ t('backoffice.timeshare.paymentMethodCard') }}</option>
          </select>
        </div>
        <div>
          <label class="text-xs text-gray-600 dark:text-gray-300 font-semibold block mb-1">{{ t('backoffice.timeshare.receiptNumberOptional') }}</label>
          <input v-model="maintPayModal.receipt_number" class="min-h-[44px] w-full bg-stone-50 dark:bg-gray-800/60 border border-stone-200 dark:border-border text-gray-900 dark:text-gray-100 text-sm rounded-xl px-4 py-2.5 outline-none" />
        </div>
      </div>
      <template #footer>
        <div class="flex gap-3">
          <AppButton variant="primary" block :loading="maintPayModal.saving" :disabled="!maintPayModal.amount" @click="submitMaintenancePayment">
            ✅ {{ t('backoffice.timeshare.confirmPayment') }}
          </AppButton>
          <AppButton variant="ghost" @click="maintPayModal.open = false">{{ t('backoffice.timeshare.cancelAction') }}</AppButton>
        </div>
      </template>
    </AppModal>
  </div>
</template>
