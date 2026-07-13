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
import { api, useAuthStore, ENDPOINTS } from '@resort-os/core'
import { AppCard, AppButton, AppSelect, AppTextarea, MoneyInput, EmptyState, useToast } from '@resort-os/ui'
import type { SelectOption } from '@resort-os/ui'
import PinGuardModal from './PinGuardModal.vue'

const props = defineProps<{ shiftId: number }>()

const auth = useAuthStore()
const toast = useToast()
const canViewLedger = computed(() => auth.hasRole('manager'))

const MOVEMENT_TYPES: SelectOption[] = [
  { value: 'cash_in', label: '💵 إيداع كاش' },
  { value: 'cash_out', label: '💸 سحب كاش' },
  { value: 'petty_cash', label: '🧾 عهدة نثرية' },
  { value: 'safe_drop', label: '🏦 تنزيل خزنة' },
  { value: 'drawer_open', label: '🗄️ فتح الدرج (بدون بيع)' },
  { value: 'correction', label: '✏️ تصحيح' },
]
const MOVEMENT_LABEL: Record<string, string> = Object.fromEntries(MOVEMENT_TYPES.map(o => [o.value, o.label]))

const movementType = ref<string>('cash_in')
const amount = ref('')
const reason = ref('')
const formError = ref('')
const submitting = ref(false)
const showPinGuard = ref(false)

// drawer_open بدون أي بيع مرتبط — منطقيًا مبلغ صفر مقبول (فتح الدرج للفحص
// بس)، بقية الأنواع محتاجة مبلغ حقيقي > 0.
const amountRequired = computed(() => movementType.value !== 'drawer_open')

function requestRecordMovement() {
  formError.value = ''
  if (reason.value.trim().length < 3) {
    formError.value = 'السبب لازم يكون 3 حروف على الأقل'
    return
  }
  if (amountRequired.value && (!amount.value || Number(amount.value) <= 0)) {
    formError.value = 'أدخل مبلغ صحيح'
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
      ...(approverUserId ? { approver_user_id: approverUserId, approver_pin: approverPin } : {}),
    })
    showPinGuard.value = false
    amount.value = ''
    reason.value = ''
    toast.success('تم تسجيل الحركة ✓')
    if (canViewLedger.value) await loadLedger()
  } catch (e: any) {
    formError.value = e?.response?.data?.detail ?? 'فشل تسجيل الحركة'
  } finally {
    submitting.value = false
  }
}

interface CashMovement {
  id: number; movement_type: string; amount: number | string; reason: string
  performed_by: number; approved_by: number | null; created_at: string
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
    toast.error('تعذّر تحميل سجل حركات الكاش')
  } finally {
    loadingLedger.value = false
  }
}
onMounted(loadLedger)

function fmtTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('ar-EG', { hour: '2-digit', minute: '2-digit' })
}
</script>

<template>
  <AppCard title="ضبط الكاش (Cash Control)" class="mb-4">
    <div dir="rtl" class="space-y-3">
      <div class="grid grid-cols-2 gap-2">
        <AppSelect v-model="movementType" label="نوع الحركة" :options="MOVEMENT_TYPES" class="col-span-2 sm:col-span-1" />
        <MoneyInput v-model="amount" :label="amountRequired ? 'المبلغ' : 'المبلغ (اختياري)'" />
      </div>
      <AppTextarea v-model="reason" :rows="2" placeholder="السبب (إجباري)..." />
      <p v-if="formError" class="text-xs text-danger">{{ formError }}</p>
      <AppButton variant="secondary" block :loading="submitting" @click="requestRecordMovement">
        تسجيل الحركة
      </AppButton>

      <template v-if="canViewLedger">
        <div class="border-t border-stone-200 pt-3">
          <h3 class="text-xs font-bold text-gray-400 uppercase mb-1.5">سجل حركات الوردية</h3>
          <div v-if="loadingLedger" class="text-center text-sm text-gray-400 py-3">جاري التحميل...</div>
          <EmptyState v-else-if="!ledger.length" icon="📭" title="مفيش حركات كاش يدوية في الوردية دي لحد دلوقتي" />
          <div v-else class="divide-y divide-stone-100 max-h-64 overflow-y-auto">
            <div v-for="m in ledger" :key="m.id" class="py-2 flex items-center justify-between gap-2">
              <div>
                <div class="text-sm font-semibold text-gray-800">{{ MOVEMENT_LABEL[m.movement_type] ?? m.movement_type }}</div>
                <div class="text-xs text-gray-400">
                  {{ m.reason }} — {{ fmtTime(m.created_at) }}
                  <span v-if="m.approved_by" class="text-emerald-600">— بموافقة مدير</span>
                </div>
              </div>
              <span class="text-sm font-bold text-blue-700">{{ Number(m.amount).toFixed(2) }} ج</span>
            </div>
          </div>
        </div>
      </template>
    </div>
  </AppCard>

  <PinGuardModal
    v-if="showPinGuard"
    :min-level="60"
    title="موافقة حركة كاش"
    message="أي حركة كاش يدوية محتاجة موافقة مدير/محاسب بالـ PIN"
    :loading="submitting"
    :error-message="formError"
    @approved="onPinApproved"
    @cancel="showPinGuard = false"
  />
</template>
