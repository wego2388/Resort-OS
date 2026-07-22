<script setup lang="ts">
/**
 * CashControlPanel — Cash Control ledger (Operations & Control Layer plan
 * §3.2, Batch 2). Lives inside ShiftDashboardView.vue next to the existing
 * shift open/close flow (ShiftPanel.vue), not a separate screen.
 *
 * Backend: POST/GET /finance/shifts/{id}/cash-movements
 * (finance.services.record_cash_movement/list_cash_movements). Every
 * movement type (cash_in/cash_out/petty_cash/safe_drop/drawer_open/
 * correction) is gated the same way as void/discount — the cashier has zero
 * autonomous authority on any of them (Mohamed, 2026-07-13), so recording a
 * movement always mounts PinGuardModal (min-level=60) first, exactly like
 * DiningOrderDetailModal's void flow and UnifiedPOSView's discount flow. No
 * parallel approval mechanism invented here.
 *
 * The ledger *list* (who moved how much, who approved) is a different
 * concept — it's audit-trail detail, gated manager+ only at the router
 * level with no PIN-escalation path for a cashier (GET .../cash-movements
 * is `Depends(get_manager_user)`, full stop). So a cashier can record a
 * movement (with manager PIN) but cannot see the shift's movement history —
 * matches Batch 4's "audit-trail visibility must not leak to cashiers"
 * requirement. The history list below only renders for manager+.
 */
import { ref, computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, useAuthStore, ENDPOINTS } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { AppCard, AppButton, AppSelect, AppTextarea, MoneyInput, EmptyState, useToast } from '@resort-os/ui'
import type { SelectOption } from '@resort-os/ui'
import PinGuardModal from './PinGuardModal.vue'

const props = defineProps<{ shiftId: number }>()

const auth = useAuthStore()
const toast = useToast()
const { t } = useI18n()
const { formatMoney, formatTime } = useStaffFormat()
const canViewLedger = computed(() => auth.hasRole('manager'))

const movementTypes = computed<SelectOption[]>(() => [
  { value: 'cash_in', label: `💵 ${t('backoffice.shiftDashboard.cashControl.types.cashIn')}` },
  { value: 'cash_out', label: `💸 ${t('backoffice.shiftDashboard.cashControl.types.cashOut')}` },
  { value: 'petty_cash', label: `🧾 ${t('backoffice.shiftDashboard.cashControl.types.pettyCash')}` },
  { value: 'safe_drop', label: `🏦 ${t('backoffice.shiftDashboard.cashControl.types.safeDrop')}` },
  { value: 'drawer_open', label: `🗄️ ${t('backoffice.shiftDashboard.cashControl.types.drawerOpen')}` },
  { value: 'correction', label: `✏️ ${t('backoffice.shiftDashboard.cashControl.types.correction')}` },
])
const movementLabel = computed<Record<string, string>>(() => Object.fromEntries(movementTypes.value.map(o => [o.value, o.label])))

// فين رايح الكاش — بس لـ safe_drop (2026-07-16، بحث مقارنة Click القديم:
// الخزنة الرئيسية/البنك كانوا مواقع مستقلة، مش مجرد "خرج من الدرج").
const destinations = computed<SelectOption[]>(() => [
  { value: 'main_safe', label: `🏦 ${t('backoffice.shiftDashboard.cashControl.destinations.mainSafe')}` },
  { value: 'bank', label: `🏛️ ${t('backoffice.shiftDashboard.cashControl.destinations.bank')}` },
  { value: 'petty_cash_box', label: `🧾 ${t('backoffice.shiftDashboard.cashControl.destinations.pettyCashBox')}` },
])
const destinationLabel = computed<Record<string, string>>(() => Object.fromEntries(destinations.value.map(o => [o.value, o.label])))

const movementType = ref<string>('cash_in')
const amount = ref('')
const reason = ref('')
const destination = ref<string>('')
const costCenterId = ref<string>('')
const formError = ref('')
const submitting = ref(false)
const showPinGuard = ref(false)

// drawer_open بدون أي بيع مرتبط — منطقيًا مبلغ صفر مقبول (فتح الدرج للفحص
// بس)، بقية الأنواع محتاجة مبلغ حقيقي > 0.
const amountRequired = computed(() => movementType.value !== 'drawer_open')
const showDestination = computed(() => movementType.value === 'safe_drop')

interface CostCenter { id: number; code: string; name: string }
const costCenters = ref<CostCenter[]>([])
const costCenterOptions = computed<SelectOption[]>(() => [
  { value: '', label: t('backoffice.shiftDashboard.cashControl.noCostCenter') },
  ...costCenters.value.map(c => ({ value: String(c.id), label: `${c.code} — ${c.name}` })),
])
async function loadCostCenters() {
  try {
    const { data } = await api.get(ENDPOINTS.finance.costCenters)
    costCenters.value = data
  } catch { /* اختياري — فشل التحميل مش لازم يوقف الفورم */ }
}

function requestRecordMovement() {
  formError.value = ''
  if (reason.value.trim().length < 3) {
    formError.value = t('backoffice.shiftDashboard.cashControl.reasonTooShort')
    return
  }
  if (amountRequired.value && (!amount.value || Number(amount.value) <= 0)) {
    formError.value = t('backoffice.shiftDashboard.cashControl.invalidAmount')
    return
  }
  showPinGuard.value = true
}

function onPinApproved(payload: { approverUserId: number | null; approverPin: string | null }) {
  performRecordMovement(payload.approverUserId, payload.approverPin)
}

async function performRecordMovement(approverUserId: number | null, approverPin: string | null) {
  submitting.value = true
  try {
    await api.post(ENDPOINTS.finance.shiftCashMovements(props.shiftId), {
      movement_type: movementType.value,
      amount: amount.value || '0',
      reason: reason.value.trim(),
      ...(showDestination.value && destination.value ? { destination: destination.value } : {}),
      ...(costCenterId.value ? { cost_center_id: Number(costCenterId.value) } : {}),
      ...(approverUserId ? { approver_user_id: approverUserId, approver_pin: approverPin } : {}),
    })
    showPinGuard.value = false
    amount.value = ''
    reason.value = ''
    destination.value = ''
    costCenterId.value = ''
    toast.success(t('backoffice.shiftDashboard.cashControl.recorded'))
    if (canViewLedger.value) await loadLedger()
  } catch (e: any) {
    formError.value = e?.response?.data?.detail ?? t('backoffice.shiftDashboard.cashControl.recordFailed')
  } finally {
    submitting.value = false
  }
}

interface CashMovement {
  id: number; movement_type: string; amount: number | string; reason: string
  performed_by: number; approved_by: number | null; created_at: string
  destination: string | null; cost_center_id: number | null
}
const ledger = ref<CashMovement[]>([])
const loadingLedger = ref(false)

async function loadLedger() {
  if (!canViewLedger.value) return
  loadingLedger.value = true
  try {
    const { data } = await api.get(ENDPOINTS.finance.shiftCashMovements(props.shiftId))
    ledger.value = data
  } catch {
    toast.error(t('backoffice.shiftDashboard.cashControl.loadFailed'))
  } finally {
    loadingLedger.value = false
  }
}
onMounted(() => {
  loadLedger()
  loadCostCenters()
})

function fmtTime(iso: string): string {
  return formatTime(iso)
}
</script>

<template>
  <AppCard :title="t('backoffice.shiftDashboard.cashControl.title')" class="mb-4">
    <div class="space-y-3">
      <div class="grid grid-cols-2 gap-2">
        <AppSelect v-model="movementType" :label="t('backoffice.shiftDashboard.cashControl.type')" :options="movementTypes" class="col-span-2 sm:col-span-1" />
        <MoneyInput v-model="amount" currency="EGP" :label="amountRequired ? t('backoffice.shiftDashboard.cashControl.amount') : t('backoffice.shiftDashboard.cashControl.optionalAmount')" />
      </div>
      <div v-if="showDestination" class="grid grid-cols-2 gap-2">
        <AppSelect v-model="destination" :label="t('backoffice.shiftDashboard.cashControl.destination')" :options="destinations" class="col-span-2 sm:col-span-1" />
      </div>
      <AppSelect v-if="costCenters.length" v-model="costCenterId" :label="t('backoffice.shiftDashboard.cashControl.costCenter')" :options="costCenterOptions" />
      <AppTextarea v-model="reason" :rows="2" :placeholder="t('backoffice.shiftDashboard.cashControl.reason')" />
      <p v-if="formError" role="alert" class="text-sm text-danger">{{ formError }}</p>
      <AppButton variant="secondary" block :loading="submitting" @click="requestRecordMovement">
        {{ t('backoffice.shiftDashboard.cashControl.record') }}
      </AppButton>

      <template v-if="canViewLedger">
        <div class="border-t border-stone-200 pt-3 dark:border-border">
          <h3 class="mb-1.5 text-xs font-bold uppercase text-gray-500 dark:text-gray-400">{{ t('backoffice.shiftDashboard.cashControl.ledgerTitle') }}</h3>
          <div v-if="loadingLedger" class="py-3 text-center text-sm text-gray-500 dark:text-gray-400">{{ t('backoffice.shiftDashboard.loading') }}</div>
          <EmptyState v-else-if="!ledger.length" icon="📭" :title="t('backoffice.shiftDashboard.cashControl.empty')" />
          <div v-else class="max-h-64 divide-y divide-stone-100 overflow-y-auto dark:divide-border">
            <div v-for="m in ledger" :key="m.id" class="py-2 flex items-center justify-between gap-2">
              <div>
                <div class="text-sm font-semibold text-gray-800 dark:text-gray-200">
                  {{ movementLabel[m.movement_type] ?? m.movement_type }}
                  <span v-if="m.destination" class="text-xs font-normal text-gray-500 dark:text-gray-400">← {{ destinationLabel[m.destination] ?? m.destination }}</span>
                </div>
                <div class="text-xs text-gray-400">
                  {{ m.reason }} — {{ fmtTime(m.created_at) }}
                  <span v-if="m.approved_by" class="text-emerald-600 dark:text-emerald-300">— {{ t('backoffice.shiftDashboard.cashControl.managerApproved') }}</span>
                </div>
              </div>
              <span class="text-sm font-bold text-blue-700 dark:text-blue-300">{{ formatMoney(m.amount, 'EGP') }}</span>
            </div>
          </div>
        </div>
      </template>
    </div>
  </AppCard>

  <PinGuardModal
    v-if="showPinGuard"
    :min-level="60"
    :title="t('backoffice.shiftDashboard.cashControl.approvalTitle')"
    :message="t('backoffice.shiftDashboard.cashControl.approvalMessage')"
    :loading="submitting"
    :error-message="formError"
    @approved="onPinApproved"
    @cancel="showPinGuard = false"
  />
</template>
