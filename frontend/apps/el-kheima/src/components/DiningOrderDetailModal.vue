<script setup lang="ts">
/**
 * DiningOrderDetailModal — dining-module counterpart of OrderDetailModal.vue,
 * adapted for the unified `dining` API (app/modules/dining/api/router.py)
 * instead of restaurant/cafe. Same PIN-approval pattern for void (reuses
 * PinGuardModal.vue + core.services.resolve_pin_approval — no parallel
 * approval flow invented here, per the task's explicit instruction), same
 * discount composable (useOrderDiscount()).
 *
 * Two things dining has that restaurant/cafe's modal doesn't need to show:
 *  - order_type is a 4-way taxonomy (dine_in|takeaway|delivery|room_service),
 *    not just "table or takeaway" — see UnifiedPOSView's order-type tabs.
 *  - order items can carry a free-text extra answer (text_value, e.g. "كام
 *    سمكة؟" -> "3 سمكات") alongside/instead of priced pick-list extras.
 *
 * Refund (post-payment) does NOT go through PinGuardModal: the backend only
 * gates *void* behind resolve_pin_approval (min_approver_level=60) — refund
 * is already router-gated to manager+ alone (require_permission(...,
 * min_role_level=60), no PIN escalation path for a lower role). Mirroring
 * that exactly here, rather than inventing an extra approval step the
 * backend doesn't ask for.
 *
 * Discount (Mohamed, 2026-07-13): the cashier role has zero discount
 * authority at all, so applying a discount is now gated exactly like void —
 * clicking "تطبيق خصم" always mounts PinGuardModal (min-level=60), which
 * self-qualifies silently (no visible UI, immediate `approved` emit) for
 * manager+ and otherwise blocks on an approver pick + PIN. Same backend gate
 * (resolve_pin_approval), same frontend component — no parallel approval
 * flow invented here.
 */
import { ref, computed, watch } from 'vue'
import { AppModal, AppButton, StatusBadge, AppTextarea } from '@resort-os/ui'
import { api, useAuthStore, parseApiTimestamp, ENDPOINTS } from '@resort-os/core'
import { useOrderDiscount } from '@resort-os/core/composables'
import PinGuardModal from './PinGuardModal.vue'

interface OrderItemExtra {
  id: number; extra_id: number | null; extra_name: string
  price_addition: number | string; text_value: string | null
}
interface OrderItem {
  id: number; item_id: number; name: string
  unit_price: number | string; quantity: number; notes: string | null
  status: string; extras: OrderItemExtra[]
  voided_reason: string | null
}
interface OrderDetail {
  id: number; order_number: string; status: string; order_type: string
  table_id: number | null; created_at: string
  guests_count: number; payment_method: string | null
  subtotal: number | string; vat_amount: number | string
  service_charge: number | string; discount_amount: number | string
  refunded_amount: number | string; total: number | string
  items: OrderItem[]
}
interface TableOption { id: number; table_number: string; status: string }

const props = defineProps<{ orderId: number | null; tables?: TableOption[] }>()
const emit = defineEmits<{ close: []; changed: [] }>()

const auth = useAuthStore()
const canVoid = computed(() => auth.hasRole('cashier'))
const canRefund = computed(() => auth.hasRole('manager'))
const canApplyDiscount = computed(() => auth.hasRole('cashier'))
const canCompletePayment = computed(() => auth.hasRole('cashier'))

const order = ref<OrderDetail | null>(null)
const loading = ref(false)
const busy = ref(false)
const errorMsg = ref('')
const successMsg = ref('')

// ── نقل لطاولة (wagdy.md P-01، dining parity — DINING_CUTOVER_PLAN.md Batch 1) ──
// نفس مستوى صلاحية باقي عمليات التشغيل اليومية على الطلب (نادل+، راجع
// PATCH /dining/orders/{id}/transfer::get_waiter_user), مش إجراء مالي.
const canTransferTable = computed(() => auth.hasRole('waiter'))
const transferOpen = ref(false)
const transferTableId = ref<number | null>(null)
const transferError = ref('')
const otherTables = computed(() => (props.tables ?? []).filter(t => t.id !== order.value?.table_id))

const ORDER_TYPE_LABELS: Record<string, string> = {
  dine_in: '🍽️ صالة', takeaway: '🥡 تيك أواي', delivery: '🛵 توصيل', room_service: '🛎️ خدمة الغرف',
}
const tableLabel = computed(() => {
  if (!order.value?.table_id) return ORDER_TYPE_LABELS[order.value?.order_type ?? ''] ?? order.value?.order_type
  const t = (props.tables ?? []).find(t => t.id === order.value!.table_id)
  return t ? `طاولة ${t.table_number}` : `طاولة #${order.value.table_id}`
})

async function loadOrder() {
  if (!props.orderId) { order.value = null; return }
  loading.value = true
  errorMsg.value = ''
  try {
    const { data } = await api.get(ENDPOINTS.dining.order(props.orderId))
    order.value = data
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail ?? 'تعذّر تحميل الطلب'
  } finally {
    loading.value = false
  }
}
watch(() => props.orderId, loadOrder, { immediate: true })

function openTransferPrompt() {
  transferOpen.value = true
  transferTableId.value = null
  transferError.value = ''
}
function cancelTransferPrompt() {
  transferOpen.value = false
  transferTableId.value = null
  transferError.value = ''
}
async function confirmTransfer() {
  if (!order.value || !transferTableId.value) {
    transferError.value = 'اختر الطاولة الجديدة'
    return
  }
  busy.value = true
  try {
    const { data } = await api.patch(ENDPOINTS.dining.orderTransfer(order.value.id), { table_id: transferTableId.value })
    order.value = data
    cancelTransferPrompt()
    successMsg.value = 'تم نقل الطلب للطاولة الجديدة ✓'
    emit('changed')
    setTimeout(() => { successMsg.value = '' }, 2500)
  } catch (e: any) {
    transferError.value = e?.response?.data?.detail ?? 'فشل نقل الطلب'
  } finally {
    busy.value = false
  }
}

// ── Void item (cashier+, PIN-gated at manager level if acting user < manager) ──
const voidingItemId = ref<number | null>(null)
const voidReason = ref('')
const voidError = ref('')
const showPinGuard = ref(false)

function openVoidPrompt(itemId: number) {
  voidingItemId.value = itemId
  voidReason.value = ''
  voidError.value = ''
  showPinGuard.value = false
}
function cancelVoidPrompt() {
  voidingItemId.value = null
  voidReason.value = ''
  voidError.value = ''
  showPinGuard.value = false
}
function requestVoid() {
  if (voidReason.value.trim().length < 3) {
    voidError.value = 'السبب لازم يكون 3 حروف على الأقل'
    return
  }
  voidError.value = ''
  showPinGuard.value = true
}
function onVoidPinApproved(payload: { approverUserId: number | null; approverPin: string | null }) {
  performVoid(payload.approverUserId, payload.approverPin)
}
async function performVoid(approverUserId: number | null, approverPin: string | null) {
  if (!order.value || voidingItemId.value === null) return
  busy.value = true
  try {
    const { data } = await api.patch(
      ENDPOINTS.dining.orderItemVoid(order.value.id, voidingItemId.value),
      { reason: voidReason.value.trim(), ...(approverUserId ? { approver_user_id: approverUserId, approver_pin: approverPin } : {}) },
    )
    order.value = data
    cancelVoidPrompt()
    successMsg.value = 'تم إلغاء الصنف ✓'
    emit('changed')
    setTimeout(() => { successMsg.value = '' }, 2500)
  } catch (e: any) {
    voidError.value = e?.response?.data?.detail ?? 'فشل إلغاء الصنف'
  } finally {
    busy.value = false
  }
}

// ── Refund item (manager+ only, post-payment — no PIN escalation, backend
// already gates the whole endpoint at manager level) ──
const refundingItemId = ref<number | null>(null)
const refundReason = ref('')
const refundError = ref('')

function openRefundPrompt(itemId: number) {
  refundingItemId.value = itemId
  refundReason.value = ''
  refundError.value = ''
}
function cancelRefundPrompt() {
  refundingItemId.value = null
  refundReason.value = ''
  refundError.value = ''
}
async function confirmRefund() {
  if (!order.value || refundingItemId.value === null) return
  if (refundReason.value.trim().length < 3) {
    refundError.value = 'السبب لازم يكون 3 حروف على الأقل'
    return
  }
  busy.value = true
  try {
    const { data } = await api.patch(
      ENDPOINTS.dining.orderItemRefund(order.value.id, refundingItemId.value),
      { reason: refundReason.value.trim() },
    )
    order.value = data
    cancelRefundPrompt()
    successMsg.value = 'تم تسجيل المرتجع ✓'
    emit('changed')
    setTimeout(() => { successMsg.value = '' }, 2500)
  } catch (e: any) {
    refundError.value = e?.response?.data?.detail ?? 'فشل تسجيل المرتجع'
  } finally {
    busy.value = false
  }
}

// ── Discount (best active ConditionalDiscount rule — no manual amount,
// PIN-gated at manager level since the cashier has zero discount authority) ──
const { applyingDiscount, discountError, applyDiscount: applyDiscountRule } = useOrderDiscount()
const showDiscountPinGuard = ref(false)
function requestDiscount() {
  showDiscountPinGuard.value = true
}
function onDiscountPinApproved(payload: { approverUserId: number | null; approverPin: string | null }) {
  showDiscountPinGuard.value = false
  performApplyDiscount(payload)
}
async function performApplyDiscount(approver: { approverUserId: number | null; approverPin: string | null }) {
  if (!order.value) return
  try {
    const data = await applyDiscountRule(order.value.id, approver)
    order.value = data
    successMsg.value = Number(data.discount_amount) > 0
      ? `تم تطبيق خصم ${data.discount_amount} ج ✓`
      : 'مفيش قاعدة خصم سارية تنطبق على الطلب ده حاليًا'
    emit('changed')
    setTimeout(() => { successMsg.value = '' }, 3000)
  } catch { /* discountError renders below */ }
}

async function setStatus(status: string, extra: Record<string, unknown> = {}) {
  if (!order.value) return
  await api.patch(ENDPOINTS.dining.orderStatus(order.value.id), { status, ...extra })
}

async function resumeAndSend() {
  if (!order.value) return
  busy.value = true
  errorMsg.value = ''
  try {
    if (order.value.status === 'held') await setStatus('open')
    await setStatus('in_kitchen')
    successMsg.value = 'تم إرسال الطلب للمطبخ ✓'
    emit('changed')
    await loadOrder()
    setTimeout(() => { successMsg.value = '' }, 2500)
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail ?? 'فشل إرسال الطلب للمطبخ'
  } finally {
    busy.value = false
  }
}

async function markServed() {
  if (!order.value) return
  busy.value = true
  errorMsg.value = ''
  try {
    await setStatus('served')
    successMsg.value = 'تم تقديم الطلب ✓'
    emit('changed')
    await loadOrder()
    setTimeout(() => { successMsg.value = '' }, 2500)
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail ?? 'فشل تحديث حالة الطلب'
  } finally {
    busy.value = false
  }
}

const payingMethod = ref<'cash' | 'card' | 'room' | 'wallet'>('cash')
const roomIdInput = ref('')
const payError = ref('')
async function completePayment() {
  if (!order.value) return
  payError.value = ''
  let charge_to_room_id: number | undefined
  if (payingMethod.value === 'room') {
    const roomId = parseInt(roomIdInput.value, 10)
    if (!roomIdInput.value || Number.isNaN(roomId) || roomId <= 0) {
      payError.value = 'اكتب رقم غرفة صحيح'
      return
    }
    charge_to_room_id = roomId
  }
  busy.value = true
  try {
    await setStatus('paid', { charge_to_room_id, payment_method: payingMethod.value })
    successMsg.value = 'تم إتمام الدفع ✓'
    roomIdInput.value = ''
    emit('changed')
    await loadOrder()
    setTimeout(() => { successMsg.value = '' }, 2500)
  } catch (e: any) {
    payError.value = e?.response?.data?.detail ?? 'فشل إتمام الدفع'
  } finally {
    busy.value = false
  }
}

function lineTotal(item: OrderItem): number {
  if (item.status === 'cancelled' || item.status === 'refunded') return 0
  const extras = item.extras.reduce((s, e) => s + Number(e.price_addition), 0)
  return (Number(item.unit_price) + extras) * item.quantity
}
</script>

<template>
  <AppModal :open="!!orderId" title="تفاصيل الطلب" size="md" @close="emit('close')">
    <div dir="rtl" class="space-y-4">
      <div v-if="loading" class="flex items-center justify-center py-10">
        <div class="animate-spin w-7 h-7 border-4 border-primary-600 border-t-transparent rounded-full" />
      </div>

      <template v-else-if="order">
        <div class="flex items-center justify-between">
          <div>
            <div class="font-bold text-gray-900">{{ order.order_number }}</div>
            <div class="text-xs text-gray-500 mt-0.5">
              {{ tableLabel }}
              <template v-if="order.guests_count > 1"> — {{ order.guests_count }} غطاءات</template>
            </div>
            <div v-if="order.created_at" class="text-[11px] text-gray-400 mt-0.5">
              🕐 {{ parseApiTimestamp(order.created_at).toLocaleString('ar-EG', { hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' }) }}
            </div>
          </div>
          <StatusBadge :status="order.status" :map="{
            held: { label: 'معلّق', variant: 'warning' },
            open: { label: 'مفتوح', variant: 'info' },
            in_kitchen: { label: 'في المطبخ', variant: 'info' },
            served: { label: 'اتقدّم', variant: 'success' },
            paid: { label: 'مدفوع', variant: 'success' },
            cancelled: { label: 'ملغي', variant: 'danger' },
            refunded: { label: 'مرتجع', variant: 'danger' },
          }" />
        </div>

        <!-- ── نقل لطاولة (wagdy.md P-01) — نادل+، أي حالة غير مقفولة ── -->
        <div v-if="canTransferTable && !['paid', 'cancelled'].includes(order.status)">
          <button
            v-if="!transferOpen"
            @click="openTransferPrompt"
            class="text-xs text-blue-600 hover:text-blue-800 font-semibold flex items-center gap-1"
          >🔀 نقل لطاولة تانية</button>

          <div v-else class="mt-2 space-y-2 bg-blue-50 border border-blue-200 rounded-lg p-2.5">
            <select v-model="transferTableId" class="w-full border border-stone-300 rounded-lg p-1.5 text-xs">
              <option :value="null" disabled>اختر الطاولة الجديدة...</option>
              <option v-for="t in otherTables" :key="t.id" :value="t.id" :disabled="t.status === 'occupied' || t.status === 'out_of_service'">
                طاولة {{ t.table_number }} — {{ t.status === 'available' ? 'متاحة' : t.status === 'occupied' ? 'مشغولة' : t.status === 'out_of_service' ? 'خارج الخدمة' : t.status }}
              </option>
            </select>
            <p v-if="transferError" class="text-xs text-red-600">{{ transferError }}</p>
            <div class="flex gap-2">
              <button @click="cancelTransferPrompt" class="flex-1 py-1.5 text-xs font-semibold text-gray-600 border border-stone-200 rounded-lg bg-white">إلغاء</button>
              <button :disabled="busy" @click="confirmTransfer" class="flex-1 py-1.5 text-xs font-bold text-white bg-blue-600 rounded-lg disabled:opacity-50">تأكيد النقل</button>
            </div>
          </div>
        </div>

        <div class="space-y-2 max-h-64 overflow-y-auto">
          <div
            v-for="item in order.items"
            :key="item.id"
            class="rounded-lg border p-3"
            :class="['cancelled', 'refunded'].includes(item.status) ? 'border-stone-100 bg-stone-50 opacity-60' : 'border-stone-200'"
          >
            <div class="flex items-start justify-between gap-2">
              <div class="flex-1">
                <div class="text-sm font-semibold text-gray-900" :class="['cancelled', 'refunded'].includes(item.status) && 'line-through'">
                  {{ item.quantity }}× {{ item.name }}
                </div>
                <div v-if="item.extras.length" class="text-xs text-gray-500 mt-0.5 space-y-0.5">
                  <div v-for="e in item.extras" :key="e.id">
                    {{ e.extra_name }}<template v-if="e.text_value">: {{ e.text_value }}</template>
                  </div>
                </div>
                <div v-if="item.notes" class="text-xs text-gray-400 mt-0.5">📝 {{ item.notes }}</div>
                <div v-if="item.status === 'cancelled'" class="text-xs text-danger mt-1">
                  ملغي{{ item.voided_reason ? ` — ${item.voided_reason}` : '' }}
                </div>
                <div v-if="item.status === 'refunded'" class="text-xs text-danger mt-1">
                  مرتجع{{ item.voided_reason ? ` — ${item.voided_reason}` : '' }}
                </div>
              </div>
              <div class="flex flex-col items-end gap-1.5 flex-shrink-0">
                <span class="text-sm font-bold text-primary-700">{{ lineTotal(item) }} ج</span>
                <button
                  v-if="canVoid && item.status !== 'cancelled' && !['paid','cancelled'].includes(order.status)"
                  @click="openVoidPrompt(item.id)"
                  class="text-xs text-danger hover:opacity-80 font-medium"
                >إلغاء الصنف</button>
                <button
                  v-if="canRefund && order.status === 'paid' && !['cancelled', 'refunded'].includes(item.status)"
                  @click="openRefundPrompt(item.id)"
                  class="text-xs text-danger hover:opacity-80 font-medium"
                >مرتجع</button>
              </div>
            </div>

            <div v-if="voidingItemId === item.id" class="mt-2.5 pt-2.5 border-t border-stone-200 space-y-2">
              <AppTextarea v-model="voidReason" :rows="2" placeholder="سبب الإلغاء (إجباري)..." />
              <p v-if="voidError" class="text-xs text-danger">{{ voidError }}</p>
              <div class="flex gap-2">
                <AppButton variant="ghost" size="sm" block @click="cancelVoidPrompt">إلغاء</AppButton>
                <AppButton variant="danger" size="sm" block :loading="busy" @click="requestVoid">تأكيد الإلغاء</AppButton>
              </div>
            </div>

            <div v-if="refundingItemId === item.id" class="mt-2.5 pt-2.5 border-t border-stone-200 space-y-2">
              <AppTextarea v-model="refundReason" :rows="2" placeholder="سبب المرتجع (إجباري)..." />
              <p v-if="refundError" class="text-xs text-danger">{{ refundError }}</p>
              <div class="flex gap-2">
                <AppButton variant="ghost" size="sm" block @click="cancelRefundPrompt">إلغاء</AppButton>
                <AppButton variant="danger" size="sm" block :loading="busy" @click="confirmRefund">تأكيد المرتجع</AppButton>
              </div>
            </div>
          </div>
        </div>

        <div class="border-t border-stone-200 pt-3 space-y-1 text-sm">
          <div class="flex justify-between text-gray-500"><span>المجموع الفرعي</span><span>{{ order.subtotal }} ج</span></div>
          <div class="flex justify-between text-gray-500"><span>ضريبة</span><span>{{ order.vat_amount }} ج</span></div>
          <div class="flex justify-between text-gray-500"><span>خدمة</span><span>{{ order.service_charge }} ج</span></div>
          <div v-if="Number(order.discount_amount) > 0" class="flex justify-between text-success font-medium">
            <span>خصم</span><span>−{{ order.discount_amount }} ج</span>
          </div>
          <div v-if="Number(order.refunded_amount) > 0" class="flex justify-between text-danger font-medium">
            <span>إجمالي المرتجعات</span><span>−{{ order.refunded_amount }} ج</span>
          </div>
          <div class="flex justify-between font-bold text-gray-900 text-base"><span>الإجمالي</span><span>{{ order.total }} ج</span></div>
          <div v-if="order.status === 'paid' && order.payment_method" class="flex justify-between text-gray-500 pt-1 border-t border-stone-100 mt-1">
            <span>طريقة الدفع</span>
            <span class="font-medium text-gray-700">{{
              order.payment_method === 'cash' ? '💵 كاش' :
              order.payment_method === 'card' ? '💳 كارت' :
              order.payment_method === 'room' ? '🛏️ حساب الغرفة' :
              order.payment_method === 'wallet' ? '👛 محفظة' : order.payment_method
            }}</span>
          </div>
        </div>

        <div v-if="canApplyDiscount && !['paid', 'cancelled'].includes(order.status)" class="border-t border-stone-200 pt-3">
          <AppButton variant="secondary" block :loading="applyingDiscount" @click="requestDiscount">🏷️ تطبيق خصم</AppButton>
          <p v-if="discountError" class="text-xs text-danger mt-1.5">{{ discountError }}</p>
        </div>

        <div v-if="['open', 'in_kitchen', 'served'].includes(order.status) && canCompletePayment" class="border-t border-stone-200 pt-3 space-y-2">
          <div class="text-sm font-bold text-gray-900">إتمام الدفع</div>
          <div class="grid grid-cols-4 gap-1">
            <button
              v-for="m in [{ val: 'cash', label: 'كاش' }, { val: 'card', label: 'كارت' }, { val: 'room', label: 'أوضة' }, { val: 'wallet', label: 'محفظة' }]"
              :key="m.val"
              type="button"
              @click="payingMethod = (m.val as 'cash' | 'card' | 'room' | 'wallet')"
              :class="[
                'py-2 rounded-lg text-xs font-semibold border-2 transition-all min-h-[44px]',
                payingMethod === m.val ? 'border-primary-600 bg-primary-50 text-primary-700' : 'border-stone-200 text-gray-600',
              ]"
            >{{ m.label }}</button>
          </div>
          <input
            v-if="payingMethod === 'room'"
            v-model="roomIdInput"
            type="number"
            min="1"
            placeholder="رقم الغرفة (ID)"
            class="w-full border border-stone-300 rounded-lg p-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 min-h-[44px]"
          />
          <p v-if="payError" class="text-xs text-danger">{{ payError }}</p>
          <AppButton variant="primary" block :loading="busy" @click="completePayment">💳 إتمام الدفع — {{ order.total }} ج</AppButton>
        </div>

        <transition name="fade">
          <div v-if="successMsg" class="bg-success/10 text-success text-xs px-2 py-2 rounded-lg text-center font-medium">{{ successMsg }}</div>
        </transition>
        <transition name="fade">
          <div v-if="errorMsg" class="bg-danger/10 text-danger text-xs px-2 py-2 rounded-lg text-center font-medium">{{ errorMsg }}</div>
        </transition>
      </template>
    </div>

    <template v-if="order" #footer>
      <div class="flex gap-2">
        <AppButton variant="ghost" block @click="emit('close')">إغلاق</AppButton>
        <AppButton v-if="['held', 'open'].includes(order.status)" variant="primary" block :loading="busy" @click="resumeAndSend">🍳 إرسال للمطبخ</AppButton>
        <AppButton v-if="order.status === 'in_kitchen'" variant="primary" block :loading="busy" @click="markServed">🍽️ قدّم الطلب</AppButton>
      </div>
    </template>
  </AppModal>

  <PinGuardModal
    v-if="showPinGuard"
    :min-level="60"
    title="موافقة إلغاء الصنف"
    message="إلغاء صنف من الطلب يحتاج موافقة مدير بالـ PIN"
    :loading="busy"
    :error-message="voidError"
    @approved="onVoidPinApproved"
    @cancel="showPinGuard = false"
  />

  <PinGuardModal
    v-if="showDiscountPinGuard"
    :min-level="60"
    title="موافقة تطبيق خصم"
    message="الكاشير مالوش صلاحية خصم — محتاج موافقة مدير/محاسب بالـ PIN"
    :loading="applyingDiscount"
    :error-message="discountError"
    @approved="onDiscountPinApproved"
    @cancel="showDiscountPinGuard = false"
  />
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
