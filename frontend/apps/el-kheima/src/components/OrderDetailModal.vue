<script setup lang="ts">
// OrderDetailModal — views a single existing order (held/open/in_kitchen/served)
// with its real OrderItemRead rows (has ids, unlike a local cart line).
// Two things gated on real state, not guessed:
//  - Void a line item: PATCH .../items/{id}/void requires cashier+ on the
//    backend, so the button only renders for auth.hasRole('cashier') — a
//    waiter never sees a control that would just 403.
//  - "Send to kitchen": held orders resume via PATCH status→open, but that
//    alone does NOT create a KitchenTicket (only the open→in_kitchen
//    transition does, per services.update_order_status) — so resuming a
//    held order chains both PATCH calls before the kitchen actually sees it.
import { ref, computed, watch } from 'vue'
import { AppModal, AppButton, AppBadge } from '@resort-os/ui'
import { api, useAuthStore, parseApiTimestamp } from '@resort-os/core'
import { useOrderDiscount } from '@resort-os/core/composables'
import PinGuardModal from './PinGuardModal.vue'

interface OrderItemExtra { id: number; extra_id: number | null; extra_name: string; price_addition: number | string }
interface OrderItem {
  id: number
  menu_item_id: number
  name: string
  unit_price: number | string
  quantity: number
  notes: string | null
  status: string
  extras: OrderItemExtra[]
  voided_reason: string | null
}
interface OrderDetail {
  id: number
  order_number: string
  status: string
  order_type: string
  table_id: number | null
  created_at: string
  guests_count?: number   // restaurant فقط — cafe مش عندها هذا الحقل
  payment_method?: string | null  // #21: متاح بعد الدفع (paid)
  subtotal: number | string
  vat_amount: number | string
  service_charge: number | string
  discount_amount: number | string
  total: number | string
  items: OrderItem[]
}

const props = defineProps<{ orderId: number | null; tableLabel?: string; module?: 'restaurant' | 'cafe' }>()
const emit = defineEmits<{ close: []; changed: [] }>()

// الموديول المستخدم — restaurant (افتراضي) أو cafe
const mod = computed(() => props.module ?? 'restaurant')

const auth = useAuthStore()
const canVoid = computed(() => auth.hasRole('cashier'))

const order = ref<OrderDetail | null>(null)
const loading = ref(false)
const busy = ref(false)
const errorMsg = ref('')
const successMsg = ref('')

// إلغاء صنف — لازم موافقة PIN مدير+ لو المنفّذ نفسه أقل من مدير (راجع
// PinGuardModal.vue وcore.services.resolve_pin_approval). البوابة دي كانت
// منطق inline هنا لحالها (اختيار مدير + إدخال PIN)، اتستخرجت لكومبوننت
// مشترك قابل لإعادة الاستخدام (wagdy.md بند S-03) — راجع requestVoid/
// performVoid تحت لتسلسل التنفيذ الفعلي.
const voidingItemId = ref<number | null>(null)
const voidReason = ref('')
const voidError = ref('')
const showPinGuard = ref(false)

// ── Complete payment (الكاشير بس — نفس مستوى void، إتمام الدفع فعل مالي
// فعلي بيقفل الطاولة/ينشر charge على الفوليو/يرحّل قيد إيراد سيرفر-سايد) ──
const canCompletePayment = computed(() => auth.hasRole('cashier'))
const payingMethod = ref<'cash' | 'card' | 'room' | 'wallet'>('cash')

// طرق الدفع المتاحة — الكافيه مش عندها "حساب الغرفة" من هذه الشاشة (يتم
// عبر CafePOSView مباشرة)، لكن عندها "محفظة" (wallet).
const paymentMethods = computed(() => {
  if (mod.value === 'cafe') {
    return [
      { val: 'cash',   label: 'كاش' },
      { val: 'card',   label: 'كارت' },
      { val: 'wallet', label: 'محفظة' },
    ]
  }
  return [
    { val: 'cash', label: 'كاش' },
    { val: 'card', label: 'كارت' },
    { val: 'room', label: 'حساب الغرفة' },
  ]
})
const roomIdInput = ref('')
const payError = ref('')

// ── Apply discount (كاشير بس — POST /restaurant/orders/{id}/discount كان
// موجود ومغطّى بالتست من غير أي زرار في الواجهة يستخدمه. بيطبّق أفضل قاعدة
// خصم نشطة (ConditionalDiscount في finance) تلقائيًا على الطلب — مش مبلغ
// حر بيكتبه الكاشير، فمفيش أي input هنا، زرار واحد بس. المنطق نفسه مشترك
// مع RestaurantPOSView/CafePOSView عبر useOrderDiscount — راجعها.) ──
const canApplyDiscount = computed(() => auth.hasRole('cashier'))
const { applyingDiscount, discountError, applyDiscount: applyDiscountRule } = useOrderDiscount(mod.value)

async function applyDiscount() {
  if (!order.value) return
  try {
    const data = await applyDiscountRule(order.value.id)
    order.value = data
    successMsg.value = Number(data.discount_amount) > 0
      ? `تم تطبيق خصم ${data.discount_amount} ج ✓`
      : 'مفيش قاعدة خصم سارية تنطبق على الطلب ده حاليًا'
    emit('changed')
    setTimeout(() => { successMsg.value = '' }, 3000)
  } catch {
    // discountError من useOrderDiscount بيتعرض في الـ template تحت
  }
}

const statusLabels: Record<string, string> = {
  held: 'معلّق', open: 'مفتوح', in_kitchen: 'في المطبخ',
  served: 'اتقدّم', paid: 'مدفوع', cancelled: 'ملغي',
}
const statusVariant: Record<string, 'success' | 'warning' | 'danger' | 'info' | 'neutral'> = {
  held: 'warning', open: 'info', in_kitchen: 'info', served: 'success', paid: 'success', cancelled: 'danger',
}

async function loadOrder() {
  if (!props.orderId) { order.value = null; return }
  loading.value = true
  errorMsg.value = ''
  try {
    const { data } = await api.get(`/api/v1/${mod.value}/orders/${props.orderId}`)
    order.value = data
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail ?? 'تعذّر تحميل الطلب'
  } finally {
    loading.value = false
  }
}

watch(() => props.orderId, loadOrder, { immediate: true })

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

/** خطوة أولى: تحقق من السبب محليًا، وبعدين افتح PinGuardModal — لو المنفّذ
 * مدير+ (مؤهّل بنفسه)، بيرجع approved فورًا من غير أي UI مرئي (راجع
 * PinGuardModal.vue) والإلغاء بينفّذ على طول. */
function requestVoid() {
  const reason = voidReason.value.trim()
  if (reason.length < 3) {
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
  const reason = voidReason.value.trim()
  busy.value = true
  try {
    const { data } = await api.patch(
      `/api/v1/${mod.value}/orders/${order.value.id}/items/${voidingItemId.value}/void`,
      { reason, ...(approverUserId ? { approver_user_id: approverUserId, approver_pin: approverPin } : {}) },
      {},
    )
    order.value = data
    cancelVoidPrompt()
    successMsg.value = 'تم إلغاء الصنف ✓'
    emit('changed')
    setTimeout(() => { successMsg.value = '' }, 2500)
  } catch (e: any) {
    // showPinGuard يفضل زي ما هو (true لو كان مفتوح) — المستخدم يقدر يصحح
    // الـ PIN ويحاول تاني من غير ما يفقد اختياره للمدير أو سبب الإلغاء.
    voidError.value = e?.response?.data?.detail ?? 'فشل إلغاء الصنف'
  } finally {
    busy.value = false
  }
}

async function setStatus(status: string) {
  if (!order.value) return
  await api.patch(
    `/api/v1/${mod.value}/orders/${order.value.id}/status`,
    { status },
    {},
  )
}

/** Resume a held order: held → open (unholds, table stays occupied as-is)
 * then open → in_kitchen (this second transition is the one that actually
 * creates the KitchenTicket — see services.update_order_status). Without
 * both steps the order would sit as "open" forever, invisible to the KDS. */
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

/** in_kitchen → served — النادل بيأكّد إن الأكل وصل الطاولة. مش فعل مالي،
 * فمفيش أي role gate إضافي غير إنه أصلاً قدر يفتح الطلب. */
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

/** served → paid — يقفل الحساب فعليًا (السيرفر بيقفل الطاولة، ينشر
 * charge على فوليو الغرفة لو "room"، يرحّل قيد إيراد، يخصم مخزون). كاشير
 * أو أعلى بس — الباك إند بيرفض بـ 403 لو نادل حاول (راجع
 * restaurant/api/router.py::update_order_status). */
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
    await api.patch(
      `/api/v1/${mod.value}/orders/${order.value.id}/status`,
      { status: 'paid', charge_to_room_id, payment_method: payingMethod.value },
      {},
    )
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
  if (item.status === 'cancelled') return 0
  const extras = item.extras.reduce((s, e) => s + Number(e.price_addition), 0)
  return (Number(item.unit_price) + extras) * item.quantity
}
</script>

<template>
  <AppModal :open="!!orderId" title="تفاصيل الطلب" size="md" @close="emit('close')">
    <div dir="rtl" class="space-y-4">
      <div v-if="loading" class="flex items-center justify-center py-10">
        <div class="animate-spin w-7 h-7 border-4 border-blue-600 border-t-transparent rounded-full" />
      </div>

      <template v-else-if="order">
        <div class="flex items-center justify-between">
          <div>
            <div class="font-bold text-gray-900">{{ order.order_number }}</div>
            <div class="text-xs text-gray-500 mt-0.5">
              {{ tableLabel || (order.table_id ? `طاولة ${order.table_id}` : 'Takeaway') }}
              <template v-if="order.guests_count">
                — {{ order.guests_count }} {{ order.guests_count === 1 ? 'غطاء' : 'غطاءات' }}
              </template>
            </div>
            <!-- #27: وقت تقديم الطلب — مهم لتوقيت المطبخ وحل نزاعات الزبائن -->
            <div v-if="order.created_at" class="text-[11px] text-gray-400 mt-0.5">
              🕐 {{ parseApiTimestamp(order.created_at).toLocaleString('ar-EG', { hour: '2-digit', minute: '2-digit', day: 'numeric', month: 'short' }) }}
            </div>
          </div>
          <AppBadge :variant="statusVariant[order.status] ?? 'neutral'">
            {{ statusLabels[order.status] ?? order.status }}
          </AppBadge>
        </div>

        <div class="space-y-2 max-h-64 overflow-y-auto">
          <div
            v-for="item in order.items"
            :key="item.id"
            class="rounded-lg border p-3"
            :class="item.status === 'cancelled' ? 'border-stone-100 bg-stone-50 opacity-60' : 'border-stone-200'"
          >
            <div class="flex items-start justify-between gap-2">
              <div class="flex-1">
                <div class="text-sm font-semibold text-gray-900" :class="item.status === 'cancelled' && 'line-through'">
                  {{ item.quantity }}× {{ item.name }}
                </div>
                <div v-if="item.extras.length" class="text-xs text-gray-500 mt-0.5">
                  {{ item.extras.map(e => e.extra_name).join('، ') }}
                </div>
                <div v-if="item.notes" class="text-xs text-gray-400 mt-0.5">📝 {{ item.notes }}</div>
                <div v-if="item.status === 'cancelled'" class="text-xs text-red-500 mt-1">
                  ملغي{{ item.voided_reason ? ` — ${item.voided_reason}` : '' }}
                </div>
              </div>
              <div class="flex flex-col items-end gap-1.5 flex-shrink-0">
                <span class="text-sm font-bold text-blue-700">{{ lineTotal(item) }} ج</span>
                <button
                  v-if="canVoid && item.status !== 'cancelled' && !['paid','cancelled'].includes(order.status)"
                  @click="openVoidPrompt(item.id)"
                  class="text-xs text-red-500 hover:text-red-700 font-medium"
                >إلغاء الصنف</button>
              </div>
            </div>

            <div v-if="voidingItemId === item.id" class="mt-2.5 pt-2.5 border-t border-stone-200 space-y-2">
              <textarea
                v-model="voidReason"
                rows="2"
                placeholder="سبب الإلغاء (إجباري)..."
                class="w-full border border-stone-300 rounded-lg p-2 text-xs focus:outline-none focus:ring-2 focus:ring-red-400 resize-none"
                autofocus
              />
              <p v-if="voidError" class="text-xs text-red-600">{{ voidError }}</p>
              <div class="flex gap-2">
                <button @click="cancelVoidPrompt" class="flex-1 py-1.5 text-xs font-semibold text-gray-600 border border-stone-200 rounded-lg">إلغاء</button>
                <button :disabled="busy" @click="requestVoid" class="flex-1 py-1.5 text-xs font-bold text-white bg-red-600 rounded-lg disabled:opacity-50">تأكيد الإلغاء</button>
              </div>
            </div>
          </div>
        </div>

        <div class="border-t border-stone-200 pt-3 space-y-1 text-sm">
          <div class="flex justify-between text-gray-500"><span>المجموع الفرعي</span><span>{{ order.subtotal }} ج</span></div>
          <div class="flex justify-between text-gray-500"><span>ضريبة</span><span>{{ order.vat_amount }} ج</span></div>
          <div class="flex justify-between text-gray-500"><span>خدمة</span><span>{{ order.service_charge }} ج</span></div>
          <div v-if="Number(order.discount_amount) > 0" class="flex justify-between text-green-600 font-medium">
            <span>خصم</span><span>−{{ order.discount_amount }} ج</span>
          </div>
          <div class="flex justify-between font-bold text-gray-900 text-base"><span>الإجمالي</span><span>{{ order.total }} ج</span></div>
          <!-- #21: عرض طريقة الدفع للطلبات المدفوعة -->
          <div v-if="order.status === 'paid' && order.payment_method" class="flex justify-between text-gray-500 pt-1 border-t border-stone-100 mt-1">
            <span>طريقة الدفع</span>
            <span class="font-medium text-gray-700">{{
              order.payment_method === 'cash'   ? '💵 كاش'   :
              order.payment_method === 'card'   ? '💳 كارت'  :
              order.payment_method === 'room'   ? '🛏️ حساب الغرفة' :
              order.payment_method === 'wallet' ? '👛 محفظة' :
              order.payment_method
            }}</span>
          </div>
        </div>

        <!-- ── تطبيق خصم (كاشير+ بس) — قبل قفل الحساب، أي حالة غير مدفوعة/ملغاة ── -->
        <div
          v-if="canApplyDiscount && !['paid', 'cancelled'].includes(order.status)"
          class="border-t border-stone-200 pt-3"
        >
          <AppButton variant="secondary" block :loading="applyingDiscount" @click="applyDiscount">
            🏷️ تطبيق خصم
          </AppButton>
          <p v-if="discountError" class="text-xs text-red-600 mt-1.5">{{ discountError }}</p>
        </div>

        <!-- ── إتمام الدفع (كاشير+ بس) — متاح من أي حالة غير نهائية، مش
             لازم "served" تحديدًا: جاهزية الأكل الفعلية بتتابَع على مستوى
             تذكرة الـ KDS (pending→in_progress→done)، مش Order.status —
             فالكاشير ممكن يقفل الحساب فور ما الطلب يوصل المطبخ لو حتى
             الأكل خرج فعليًا، من غير ما ينتظر transition "served" يدوي. ── -->
        <div v-if="['open', 'in_kitchen', 'served'].includes(order.status) && canCompletePayment" class="border-t border-stone-200 pt-3 space-y-2">
          <div class="text-sm font-bold text-gray-900">إتمام الدفع</div>
          <div class="grid grid-cols-3 gap-1">
            <button
              v-for="m in paymentMethods"
              :key="m.val"
              @click="payingMethod = (m.val as 'cash' | 'card' | 'room' | 'wallet')"
              :class="[
                'py-1.5 rounded-lg text-xs font-semibold border-2 transition-all',
                payingMethod === m.val ? 'border-blue-600 bg-blue-50 text-blue-700' : 'border-stone-200 text-gray-600',
              ]"
            >{{ m.label }}</button>
          </div>
          <input
            v-if="payingMethod === 'room'"
            v-model="roomIdInput"
            type="number"
            min="1"
            placeholder="رقم الغرفة (ID)"
            class="w-full border border-stone-300 rounded-lg p-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <p v-if="payError" class="text-xs text-red-600">{{ payError }}</p>
          <AppButton variant="primary" block :loading="busy" @click="completePayment">
            💳 إتمام الدفع — {{ order.total }} ج
          </AppButton>
        </div>

        <transition name="fade">
          <div v-if="successMsg" class="bg-green-100 text-green-700 text-xs px-2 py-2 rounded-lg text-center font-medium">{{ successMsg }}</div>
        </transition>
        <transition name="fade">
          <div v-if="errorMsg" class="bg-red-100 text-red-700 text-xs px-2 py-2 rounded-lg text-center font-medium">{{ errorMsg }}</div>
        </transition>
      </template>
    </div>

    <template v-if="order" #footer>
      <div class="flex gap-2">
        <AppButton variant="ghost" block @click="emit('close')">إغلاق</AppButton>
        <AppButton
          v-if="['held', 'open'].includes(order.status)"
          variant="primary"
          block
          :loading="busy"
          @click="resumeAndSend"
        >🍳 إرسال للمطبخ</AppButton>
        <AppButton
          v-if="order.status === 'in_kitchen'"
          variant="primary"
          block
          :loading="busy"
          @click="markServed"
        >🍽️ قدّم الطلب</AppButton>
      </div>
    </template>
  </AppModal>

  <!-- بوابة موافقة PIN لإلغاء صنف — راجع requestVoid/performVoid فوق -->
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
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.3s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
