<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api, ENDPOINTS } from '@resort-os/core'
import { useOfflineQueue, usePrintDocument, useOrderDiscount } from '@resort-os/core/composables'
import { AppBadge, useToast } from '@resort-os/ui'
import OrderDetailModal from '../../components/OrderDetailModal.vue'

const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')
const toast = useToast()
const { printBlob } = usePrintDocument()
// #5: زرار "تطبيق خصم" وقت بناء طلب جديد — نفس منطق RestaurantPOSView
// (راجع applyDiscountToCart تحت) بنفس الـ composable المستخدم في OrderDetailModal.
const { applyingDiscount, discountError, applyDiscount: applyDiscountRule } = useOrderDiscount('cafe')

// ── Offline queue ──────────────────────────────────────────────────────────────
// #4: بدل queue محلي منفصل، بنستخدم useOfflineQueue من core مع module='cafe'
// وده بيعني طلبات الكافيه offline بتتزامن لـ /api/v1/cafe/orders/sync
// وبتتحفظ في IndexedDB زي المطعم بالظبط (FIFO, server-authoritative stock)
const {
  isOnline,
  pendingCount,
  lastPartialRejection,
  submitOrder: submitOrderOnlineOrQueue,
  syncPendingOrders,
} = useOfflineQueue('cafe')

function handleOnline() {
  syncPendingOrders()
}
function handleOffline() {
  // isOnline بيتحدث تلقائياً في الـ composable
}

let pollTimer: ReturnType<typeof setInterval> | null = null

// ── Types ──────────────────────────────────────────────────────────────────────
// ملاحظة (wagdy.md #3): الكاشير محتاج يعرف طاولة/موقع كل طلب جاري من غير ما
// يفتح تفاصيله — نفس الحل الموجود في RestaurantPOSView.tableLabelFor بالظبط،
// بس هنا لازم ناخد بالنا إن الشمسيات/البرجولات ممثّلة كصفوف cafe_tables
// عادية برقم واصف زي "شمسية 12" (نفس آلية ترقيم الكافيه، مفيش موديل منفصل —
// راجع CLAUDE.md §18)، فـ table_number ممكن يكون رقم صرف أو نص واصف كامل.
interface CafeTable { id: number; table_number: string }
interface Category { id: number; name: string; name_ar: string }
interface Variant  { id: number; name: string; name_ar: string | null; price: number; is_available: boolean }
interface MenuItem { id: number; name: string; name_ar: string; price: number; is_available: boolean; category_id: number; variants?: Variant[] }
interface CartItem {
  menu_item_id: number; variant_id: number | null; variant_label: string | null
  name: string; name_ar: string; price: number; quantity: number; notes: string
}

// ── State ──────────────────────────────────────────────────────────────────────
const tables             = ref<CafeTable[]>([])
const categories         = ref<Category[]>([])
const menuItems          = ref<MenuItem[]>([])
const selectedCategoryId = ref<number | null>(null)
const cart               = ref<CartItem[]>([])
// UI-only, نفس فلسفة BeachPOSView.paymentMethod — الـ order/paid endpoints
// (CafeOrderCreate + OrderStatusUpdate) مفيهاش payment_method خالص، الكاش
// reconciliation بيحصل على مستوى قفل الوردية (finance shift close + cash
// count) مش لكل عملية لوحدها. مجرد تلميح بصري للكاشير.
const paymentMethod      = ref<'cash' | 'card' | 'wallet'>('cash')
const loading            = ref(false)
const loadError          = ref(false)
const submitting         = ref(false)
const successMsg         = ref('')
const errorMsg           = ref('')

// ── #5: تطبيق خصم قبل إرسال الطلب للبار ──────────────────────────────
// نفس منطق RestaurantPOSView بالظبط: POST /cafe/orders/{id}/discount محتاج
// order_id حقيقي، فأول ضغطة على "تطبيق خصم" بتنشئ الطلب كـ "held" عبر
// /cafe/orders/hold (موجود بالفعل، بيستخدمه heldOrders تحت من واجهة تانية)،
// وبعدين تطبّق الخصم عليه. السلة بتتقفل لحد ما الطلب يتبعت أو يتلغي.
const pendingOrderId      = ref<number | null>(null)
const pendingOrderNumber  = ref('')
const pendingOrderSummary = ref<{ discount_amount: number | string; total: number | string } | null>(null)
const cancellingPendingOrder = ref(false)
const cartLocked = computed(() => pendingOrderId.value !== null)

// Quick-qty pad: when user long-presses or uses number-pad modal
const qtyPadItem   = ref<MenuItem | null>(null)
const qtyPadValue  = ref('1')

// Note editor — مفتاح مركّب (راجع cartKey) عشان يميّز بين سطرين لنفس
// الصنف بمتغيّرات مختلفة
const editingNoteId = ref<string | null>(null)
const tempNote      = ref('')

// اختيار الحجم/النوع — لو الصنف عنده متغيّرات متاحة، لازم يتحدد واحد
// إجباريًا وقت الطلب (الباك إند بيرفض غير كده)
const variantPickerItem = ref<MenuItem | null>(null)

// ── الطلبات الجارية (كاشير — تحصيل) ──────────────────────────────────
// المسار الرئيسي للدفع في الكافيه: الوايتر/POS يبعت طلب للبار (in_kitchen)،
// البار يحضّره ويعلّم "جاهز"، الكاشير يفتح الطلب من هنا ويعمل "تحصيل".
interface ActiveCafeOrder {
  id: number; order_number: string; status: string
  table_id: number | null; order_type: string; total: number | string
}
const activeOrdersOpen    = ref(false)
const activeOrders        = ref<ActiveCafeOrder[]>([])
const activeOrdersLoading = ref(false)
const selectedOrderId     = ref<number | null>(null)
const cafePayingId        = ref<number | null>(null)
const cafePayingMethod    = ref<'cash' | 'card' | 'wallet'>('cash')
const cafePayError        = ref('')
const cafePaySuccess      = ref('')

// ── #13: Held orders — استعادة طلب معلّق ─────────────────────────────
interface HeldCafeOrder { id: number; order_number: string; table_id: number | null; total: number | string }
const heldOrdersOpen    = ref(false)
const heldOrders        = ref<HeldCafeOrder[]>([])
const heldOrdersLoading = ref(false)
const resumingOrderId   = ref<number | null>(null)

async function loadHeldOrders() {
  heldOrdersLoading.value = true
  try {
    const { data } = await api.get(ENDPOINTS.cafe.heldOrders, {
      params: { branch_id: branchId },
    })
    heldOrders.value = Array.isArray(data) ? data : (data.items ?? [])
  } catch {
    toast.error('تعذّر تحميل الطلبات المعلّقة')
  } finally {
    heldOrdersLoading.value = false
  }
}

async function resumeHeldOrder(order: HeldCafeOrder) {
  resumingOrderId.value = order.id
  try {
    // held → open → in_kitchen (نفس منطق OrderDetailModal.resumeAndSend)
    await api.patch(ENDPOINTS.cafe.orderStatus(order.id), { status: 'open' })
    await api.patch(ENDPOINTS.cafe.orderStatus(order.id), { status: 'in_kitchen' })
    toast.success(`تم إرسال طلب #${order.order_number} للبار ✓`)
    heldOrders.value = heldOrders.value.filter(o => o.id !== order.id)
    if (heldOrders.value.length === 0) heldOrdersOpen.value = false
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'تعذّر استعادة الطلب المعلّق')
  } finally {
    resumingOrderId.value = null
  }
}

const ACTIVE_STATUSES = new Set(['open', 'in_kitchen', 'served'])

async function loadActiveOrders() {
  activeOrdersLoading.value = true
  try {
    const { data } = await api.get('/api/v1/cafe/orders', {
      params: { branch_id: branchId, size: 100 },
    })
    const items: ActiveCafeOrder[] = data.items ?? data
    activeOrders.value = items.filter(o => ACTIVE_STATUSES.has(o.status))
  } catch {
    toast.error('تعذّر تحميل الطلبات الجارية — حاول تاني')
  } finally {
    activeOrdersLoading.value = false
  }
}

function openActiveOrders() {
  activeOrdersOpen.value = true
  loadActiveOrders()
}

function cafeTableLabelFor(order: { table_id: number | null }): string {
  if (!order.table_id) return 'Takeaway'
  const t = tables.value.find(t => t.id === order.table_id)
  if (!t) return `طاولة #${order.table_id}`
  // رقم صرف (طاولة كافيه عادية) ياخد بادئة "طاولة" زي المطعم بالظبط، أما
  // نص واصف كامل (شمسية/برجولة الشاطئ، زي "شمسية 12") فبيتعرض زي ما هو —
  // "طاولة شمسية 12" تكرار مربك، مش تحسين.
  return /^\d+$/.test(t.table_number) ? `طاولة ${t.table_number}` : t.table_number
}

function cafeStatusLabel(status: string): string {
  if (status === 'open')       return 'مفتوح'
  if (status === 'in_kitchen') return 'عند البار'
  if (status === 'served')     return 'تم التقديم'
  return status
}

function cafeStatusColor(status: string): string {
  if (status === 'open')       return 'bg-blue-100 text-blue-700'
  if (status === 'in_kitchen') return 'bg-amber-100 text-amber-700'
  if (status === 'served')     return 'bg-green-100 text-green-700'
  return 'bg-gray-100 text-gray-600'
}

async function collectCafeOrder(order: ActiveCafeOrder) {
  cafePayingId.value = order.id
  cafePayError.value = ''
  cafePaySuccess.value = ''
  try {
    await api.patch(`/api/v1/cafe/orders/${order.id}/status`, {
      status: 'paid',
      payment_method: cafePayingMethod.value,
    })
    // طباعة إيصال
    try {
      const receiptRes = await api.get(`/api/v1/cafe/orders/${order.id}/receipt`, { responseType: 'blob' })
      const outcome = printBlob(receiptRes.data, `cafe-receipt-${order.id}.pdf`)
      if (outcome.downloadedInstead) {
        toast.error('الإيصال اتحمّل كملف — افتحه واطبعه يدويًا')
      }
    } catch {
      // إيصال اختياري — متوقّفش عشانه
    }
    cafePaySuccess.value = `✓ تم تحصيل طلب #${order.order_number}`
    activeOrders.value = activeOrders.value.filter(o => o.id !== order.id)
    setTimeout(() => { cafePaySuccess.value = '' }, 3000)
  } catch (e: any) {
    cafePayError.value = e?.response?.data?.detail ?? 'فشل إتمام الدفع'
  } finally {
    cafePayingId.value = null
  }
}

function openOrderDetail(orderId: number) {
  activeOrdersOpen.value = false
  selectedOrderId.value = orderId
}

function onOrderDetailClosed() {
  selectedOrderId.value = null
  loadActiveOrders()
}

// ── Computed ───────────────────────────────────────────────────────────────────
const filteredItems = computed(() =>
  selectedCategoryId.value !== null
    ? menuItems.value.filter(i => i.category_id === selectedCategoryId.value && i.is_available)
    : menuItems.value.filter(i => i.is_available)
)

const total    = computed(() => cart.value.reduce((s, i) => s + i.price * i.quantity, 0))
const hasItems = computed(() => cart.value.length > 0)
// #5: بعد تطبيق الخصم، الإجمالي الحقيقي (بعد VAT/خدمة/خصم) بييجي من السيرفر
// (pendingOrderSummary) مش من مجموع السلة الخام المحلي.
const displayTotal = computed(() => pendingOrderSummary.value?.total ?? total.value)

// مفتاح تعريف سطر السلة — menu_item_id لوحده مش كافي لما يبقى فيه أكتر من
// سطر لنفس الصنف بمتغيّرات مختلفة (راجع RestaurantPOSView.vue.cartKey لنفس المنطق).
function cartKey(menuItemId: number, variantId: number | null): string {
  return variantId != null ? `${menuItemId}:${variantId}` : `${menuItemId}`
}

// ── Cart actions ───────────────────────────────────────────────────────────────
function addToCart(item: MenuItem, qty = 1) {
  if (cartLocked.value) return
  const availableVariants = (item.variants ?? []).filter(v => v.is_available)
  if (availableVariants.length > 0) {
    variantPickerItem.value = item
    return
  }
  const existing = cart.value.find(c => cartKey(c.menu_item_id, c.variant_id) === cartKey(item.id, null))
  if (existing) {
    existing.quantity += qty
    return
  }
  cart.value.push({
    menu_item_id: item.id,
    variant_id:   null,
    variant_label: null,
    name:         item.name,
    name_ar:      item.name_ar,
    price:        item.price,
    quantity:     qty,
    notes:        '',
  })
}

function addToCartWithVariant(item: MenuItem, variant: Variant, qty = 1) {
  if (cartLocked.value) return
  variantPickerItem.value = null
  const key = cartKey(item.id, variant.id)
  const existing = cart.value.find(c => cartKey(c.menu_item_id, c.variant_id) === key)
  if (existing) { existing.quantity += qty; return }
  cart.value.push({
    menu_item_id: item.id,
    variant_id:   variant.id,
    variant_label: variant.name_ar || variant.name,
    name:         item.name,
    name_ar:      item.name_ar,
    price:        variant.price,
    quantity:     qty,
    notes:        '',
  })
}

function removeFromCart(menuItemId: number, variantId: number | null) {
  if (cartLocked.value) return
  const key = cartKey(menuItemId, variantId)
  cart.value = cart.value.filter(c => cartKey(c.menu_item_id, c.variant_id) !== key)
}

function adjustQty(menuItemId: number, variantId: number | null, delta: number) {
  if (cartLocked.value) return
  const key = cartKey(menuItemId, variantId)
  const item = cart.value.find(c => cartKey(c.menu_item_id, c.variant_id) === key)
  if (!item) return
  item.quantity = Math.max(0, item.quantity + delta)
  if (item.quantity === 0) removeFromCart(menuItemId, variantId)
}

/** يمسح السلة المحلية — ولو كان عندنا طلب "held" اتنشأ سيرفر-سايد بس عشان
 * نطبّق خصم عليه (راجع applyDiscountToCart)، يلغيه فعليًا (status→cancelled)
 * قبل كده عشان الطلب ميفضلش معلّق للأبد بلا داعي. */
async function clearOrder() {
  if (pendingOrderId.value !== null) {
    cancellingPendingOrder.value = true
    try {
      await api.patch(`/api/v1/cafe/orders/${pendingOrderId.value}/status`, { status: 'cancelled' })
    } catch {
      toast.error('تعذّر إلغاء الطلب المحفوظ من السيرفر — راجعه من الطلبات الجارية وألغِه يدويًا')
    } finally {
      cancellingPendingOrder.value = false
    }
  }
  cart.value = []
  pendingOrderId.value = null
  pendingOrderNumber.value = ''
  pendingOrderSummary.value = null
}

// ── Quick qty pad ──────────────────────────────────────────────────────────────
function openQtyPad(item: MenuItem) {
  if (cartLocked.value) return
  // صنف عنده متغيّرات — لازم يتحدد الحجم/النوع الأول (مفيش سعر واحد معروف
  // نعرضه في الـ pad قبل كده)؛ الكمية بعد كده تتظبط من أزرار +/- في السلة.
  if ((item.variants ?? []).some(v => v.is_available)) {
    variantPickerItem.value = item
    return
  }
  qtyPadItem.value  = item
  qtyPadValue.value = '1'
}

function qtyPadPress(char: string) {
  if (char === 'C') { qtyPadValue.value = '1'; return }
  if (char === '⌫') {
    qtyPadValue.value = qtyPadValue.value.length > 1
      ? qtyPadValue.value.slice(0, -1)
      : '1'
    return
  }
  if (qtyPadValue.value === '1' && char !== '0') {
    qtyPadValue.value = char
  } else if (qtyPadValue.value.length < 3) {
    qtyPadValue.value += char
  }
}

function confirmQtyPad() {
  const qty = parseInt(qtyPadValue.value) || 1
  if (qtyPadItem.value) addToCart(qtyPadItem.value, qty)
  qtyPadItem.value = null
}

// ── Note editor ────────────────────────────────────────────────────────────────
function openNoteEditor(menuItemId: number, variantId: number | null, currentNote: string) {
  editingNoteId.value = cartKey(menuItemId, variantId)
  tempNote.value = currentNote
}

function saveNote() {
  const item = cart.value.find(c => cartKey(c.menu_item_id, c.variant_id) === editingNoteId.value)
  if (item) item.notes = tempNote.value
  editingNoteId.value = null
}

// ── API ────────────────────────────────────────────────────────────────────────
async function loadData() {
  loading.value = true
  loadError.value = false
  try {
    const [tablesRes, catsRes, itemsRes] = await Promise.all([
      api.get(ENDPOINTS.cafe.tables, {
        params: { branch_id: branchId },
      }),
      api.get('/api/v1/cafe/categories', {
        params: { branch_id: branchId },
      }),
      api.get('/api/v1/cafe/items', {
        params: { branch_id: branchId },
      }),
    ])

    tables.value     = tablesRes.data.tables    ?? tablesRes.data.items    ?? tablesRes.data
    categories.value = catsRes.data.categories  ?? catsRes.data.items  ?? catsRes.data
    menuItems.value  = itemsRes.data.items       ?? itemsRes.data

    if (categories.value.length) {
      selectedCategoryId.value = categories.value[0].id
    }
  } catch (e) {
    console.error('Failed to load cafe data', e)
    loadError.value = true
  } finally {
    loading.value = false
  }
}

/** ⚠️ نفس منطق RestaurantPOSView.finalizeOrderToKitchen — إنشاء الطلب لوحده
 * بيسيبه open/held، وتذكرة الـ KDS بترتبط بس بانتقالة →in_kitchen. لو الطلب
 * كان "held" (اتنشأ وقت تطبيق خصم — راجع applyDiscountToCart)، لازم يعدّي
 * held→open الأول (نفس منطق resumeHeldOrder فوق) قبل ما يتحول لـ in_kitchen. */
async function finalizeOrderToKitchen(orderId: number, wasHeld: boolean) {
  try {
    if (wasHeld) await api.patch(`/api/v1/cafe/orders/${orderId}/status`, { status: 'open' })
    await api.patch(`/api/v1/cafe/orders/${orderId}/status`, { status: 'in_kitchen' })
  } catch (e) {
    console.error('Failed to send cafe order to kitchen', e)
    errorMsg.value = 'اتسجّل الطلب لكن حصل خطأ في إرساله للبار — راجعه من قائمة الطلبات'
    setTimeout(() => { errorMsg.value = '' }, 5000)
  }

  try {
    const receiptRes = await api.get(`/api/v1/cafe/orders/${orderId}/receipt`, {
      responseType: 'blob',
    })
    const outcome = printBlob(receiptRes.data, `receipt-${orderId}.pdf`)
    if (outcome.downloadedInstead) {
      toast.error('الإيصال اتحمّل كملف (المتصفح منع نافذة الطباعة) — افتحه واطبعه يدويًا')
    }
  } catch {
    // receipt optional
  }
}

/** #5: تطبيق أفضل قاعدة خصم نشطة على الطلب اللي بيتبنى دلوقتي — نفس منطق
 * RestaurantPOSView.applyDiscountToCart بالظبط (راجعها لتفاصيل أوسع). */
async function applyDiscountToCart() {
  if (!hasItems.value || applyingDiscount.value) return
  errorMsg.value = ''

  if (pendingOrderId.value === null) {
    try {
      const { data } = await api.post('/api/v1/cafe/orders/hold', {
        branch_id:  branchId,
        order_type: 'takeaway',
        items: cart.value.map(i => ({
          item_id:    i.menu_item_id,
          variant_id: i.variant_id ?? undefined,
          quantity:   i.quantity,
          notes:      i.notes || undefined,
        })),
      })
      pendingOrderId.value     = data.id
      pendingOrderNumber.value = data.order_number
    } catch (e: any) {
      errorMsg.value = e?.response?.data?.detail ?? 'تعذّر تسجيل الطلب لتطبيق الخصم'
      setTimeout(() => { errorMsg.value = '' }, 4000)
      return
    }
  }

  try {
    const data = await applyDiscountRule(pendingOrderId.value!)
    pendingOrderSummary.value = { discount_amount: data.discount_amount, total: data.total }
    successMsg.value = Number(data.discount_amount) > 0
      ? `تم تطبيق خصم ${data.discount_amount} ج ✓`
      : 'مفيش قاعدة خصم سارية تنطبق على الطلب ده حاليًا'
    setTimeout(() => { successMsg.value = '' }, 3000)
  } catch {
    // discountError من useOrderDiscount بيتعرض في الـ template تحت
  }
}

async function submitOrder() {
  if (!hasItems.value || submitting.value) return
  submitting.value = true
  try {
    if (pendingOrderId.value !== null) {
      // #5: الطلب اتنشأ بالفعل (held) وقت تطبيق الخصم — منعملش POST تاني.
      await finalizeOrderToKitchen(pendingOrderId.value, true)
    } else {
      const payload = {
        branch_id:      branchId,
        order_type:     'takeaway',
        payment_method: paymentMethod.value,
        items: cart.value.map(i => ({
          item_id:    i.menu_item_id,
          variant_id: i.variant_id ?? undefined,
          quantity:   i.quantity,
          notes:      i.notes || undefined,
        })),
      }

      // #4: submitOrderOnlineOrQueue من useOfflineQueue('cafe') — بيتعامل مع
      // offline تلقائيًا ويحفظ في IndexedDB ويبعت لـ /cafe/orders لما يرجع النت
      const data = await submitOrderOnlineOrQueue(branchId, payload)

      if (data === null) {
        // offline — اتحفظ في queue
        clearOrder()
        successMsg.value = '📥 الطلب محفوظ — هيتبعت للبار أول ما النت يرجع'
        setTimeout(() => { successMsg.value = '' }, 4000)
        return
      }

      const orderId = data.id ?? data.order_id
      if (orderId) await finalizeOrderToKitchen(orderId, false)
    }

    // الطلب اتبعت فعليًا — مفيش داعي نلغي حاجة في clearOrder() بعد كده.
    pendingOrderId.value      = null
    pendingOrderNumber.value  = ''
    pendingOrderSummary.value = null
    clearOrder()
    successMsg.value = 'تم إرسال الطلب للبار ✓ — الدفع يتم بعد التحضير'
    setTimeout(() => { successMsg.value = '' }, 3000)
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail ?? 'فشل في إرسال الطلب'
    setTimeout(() => { errorMsg.value = '' }, 4000)
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  loadData()
  loadActiveOrders()
  window.addEventListener('online', handleOnline)
  window.addEventListener('offline', handleOffline)
  if (navigator.onLine) syncPendingOrders()
  // safety-net poll — covers cases where the 'online' event never fires
  pollTimer = setInterval(() => {
    if (navigator.onLine && pendingCount.value > 0) syncPendingOrders()
  }, 30_000)
})

onUnmounted(() => {
  window.removeEventListener('online', handleOnline)
  window.removeEventListener('offline', handleOffline)
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div class="flex flex-col h-full" dir="rtl">

    <!-- ── Offline banner ── -->
    <div
      v-if="!isOnline"
      class="bg-amber-500 text-white text-xs font-bold px-4 py-1.5 flex items-center justify-center gap-2 flex-shrink-0"
    >
      <span>⚠️ وضع offline — الطلبات بتتحفظ محلياً وهتتبعت أول ما النت يرجع</span>
      <span v-if="pendingCount > 0" class="bg-amber-700 px-2 py-0.5 rounded-full">{{ pendingCount }} في الانتظار</span>
    </div>
    <div
      v-else-if="pendingCount > 0"
      class="bg-blue-500 text-white text-xs font-bold px-4 py-1.5 flex items-center justify-center gap-2 flex-shrink-0"
    >
      <span>⏳ جاري إرسال {{ pendingCount }} طلب محفوظ من فترة الانقطاع...</span>
    </div>
    <!-- #3 fix: banner لـ partial rejection — كان مستورداً بس مش معروضاً -->
    <div
      v-if="lastPartialRejection && lastPartialRejection.length"
      class="bg-red-100 text-red-800 text-xs font-semibold px-4 py-2 flex-shrink-0 border-b border-red-200"
    >
      ⚠️ تم رفض بعض الأصناف من طلب كافيه محفوظ سابقاً (نفاد المخزون):
      {{ lastPartialRejection.map(i => `${i.name} (×${i.requested_qty})`).join('، ') }}
    </div>

    <!-- ── Category tabs ── -->
    <div class="bg-white border-b border-stone-200 px-4 py-3 flex gap-2 flex-wrap items-center shadow-sm flex-shrink-0">
      <span class="text-sm font-bold text-gray-700 ml-2">☕ الكافيه</span>

      <!-- زر الطلبات الجارية — للكاشير لتحصيل الطلبات اللي جهّزها البار -->
      <button
        @click="openActiveOrders"
        class="relative px-3 py-1.5 bg-white border-2 border-amber-400 text-amber-700 rounded-lg font-bold text-sm hover:bg-amber-50 transition-colors flex items-center gap-1.5"
      >
        🧾 الطلبات الجارية
        <AppBadge v-if="activeOrders.length" variant="warning" size="sm">{{ activeOrders.length }}</AppBadge>
      </button>

      <!-- #13: زر الطلبات المعلّقة — استعادة held order وإرسالها للبار -->
      <button
        @click="heldOrdersOpen = true; loadHeldOrders()"
        class="relative px-3 py-1.5 bg-white border-2 border-slate-300 text-slate-600 rounded-lg font-bold text-sm hover:bg-slate-50 transition-colors flex items-center gap-1.5"
      >
        ⏸ الطلبات المعلّقة
        <AppBadge v-if="heldOrders.length" variant="neutral" size="sm">{{ heldOrders.length }}</AppBadge>
      </button>

      <button
        @click="selectedCategoryId = null"
        :class="[
          'px-4 py-1.5 rounded-full text-sm font-medium transition-colors',
          selectedCategoryId === null
            ? 'bg-amber-600 text-white shadow-sm'
            : 'bg-gray-100 text-gray-600 hover:bg-gray-200',
        ]"
      >الكل</button>

      <button
        v-for="cat in categories"
        :key="cat.id"
        @click="selectedCategoryId = cat.id"
        :class="[
          'px-4 py-1.5 rounded-full text-sm font-medium transition-colors',
          selectedCategoryId === cat.id
            ? 'bg-amber-600 text-white shadow-sm'
            : 'bg-gray-100 text-gray-600 hover:bg-gray-200',
        ]"
      >{{ cat.name_ar || cat.name }}</button>
    </div>

    <!-- ── Main split ── -->
    <div class="flex flex-1 overflow-hidden">

      <!-- Menu tiles (larger, café style) -->
      <div class="flex-1 overflow-y-auto p-4 bg-stone-50">
        <div v-if="loading" class="flex items-center justify-center h-40">
          <div class="animate-spin w-8 h-8 border-4 border-amber-600 border-t-transparent rounded-full" />
        </div>

        <!-- No connection -->
        <div v-else-if="loadError" class="flex flex-col items-center justify-center h-64 text-gray-500 gap-3">
          <div class="text-5xl">⚠️</div>
          <p class="font-medium">لا يمكن الاتصال بالسيرفر</p>
          <button @click="loadData" class="px-4 py-2 bg-amber-600 text-white rounded-lg text-sm font-medium hover:bg-amber-700">
            إعادة المحاولة
          </button>
        </div>

        <div v-else class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-3">
          <button
            v-for="item in filteredItems"
            :key="item.id"
            @click="addToCart(item)"
            @contextmenu.prevent="openQtyPad(item)"
            :disabled="cartLocked"
            class="group bg-white rounded-2xl border border-stone-200 p-5 text-right hover:border-amber-400 hover:shadow-lg transition-all active:scale-95 flex flex-col justify-between min-h-[110px] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:border-stone-200 disabled:hover:shadow-none"
          >
            <div class="font-bold text-gray-900 leading-tight text-sm mb-2">
              {{ item.name_ar || item.name }}
            </div>
            <div class="flex items-end justify-between">
              <div v-if="(item.variants ?? []).filter(v => v.is_available).length > 0" class="text-sm font-bold text-amber-700">
                من {{ Math.min(...item.variants!.filter(v => v.is_available).map(v => v.price)) }}<span class="text-xs font-normal text-gray-400 mr-0.5">ج</span>
              </div>
              <div v-else class="text-xl font-black text-amber-700">
                {{ item.price }}<span class="text-xs font-normal text-gray-400 mr-0.5">ج</span>
              </div>
              <!-- Quick add indicator -->
              <div class="w-7 h-7 rounded-full bg-amber-100 group-hover:bg-amber-600 flex items-center justify-center transition-colors">
                <span class="text-amber-700 group-hover:text-white font-bold text-lg leading-none">+</span>
              </div>
            </div>
          </button>
        </div>

        <div v-if="!loading && !loadError && filteredItems.length === 0" class="flex flex-col items-center justify-center py-16 text-gray-400">
          <div class="text-4xl mb-2">☕</div>
          <p class="text-sm">لا توجد أصناف في هذه الفئة</p>
        </div>

        <!-- Hint -->
        <p v-if="!loading && !loadError && filteredItems.length > 0" class="text-center text-xs text-gray-300 mt-4">
          اضغط مرة لإضافة واحدة · كليك يمين لتحديد الكمية
        </p>
      </div>

      <!-- ── Order panel ── -->
      <div class="w-72 bg-white border-r border-stone-200 flex flex-col flex-shrink-0 shadow-lg">

        <!-- Header -->
        <div class="p-4 border-b border-stone-100 bg-amber-50">
          <div class="font-bold text-amber-900 flex items-center gap-2">
            <span>☕</span>
            <span>الطلب الحالي</span>
          </div>
        </div>

        <!-- Cart items -->
        <div class="flex-1 overflow-y-auto p-3 space-y-2">
          <div v-if="cart.length === 0" class="flex flex-col items-center justify-center py-10 text-gray-400">
            <div class="text-4xl mb-2">☕</div>
            <p class="text-sm">اختر أصناف من القائمة</p>
            <p class="text-xs mt-1 text-gray-300">كليك يمين لتحديد الكمية</p>
          </div>

          <!-- #5: بعد تطبيق الخصم، الطلب بيتسجّل سيرفر-سايد (held) — السلة
               بتتقفل من التعديل عشان تفضل مطابقة للطلب المحفوظ بالظبط. -->
          <div v-if="cartLocked" class="bg-green-50 border border-green-200 rounded-lg px-3 py-2 text-xs text-green-700">
            🔒 الطلب #{{ pendingOrderNumber }} اتسجّل وطُبّق عليه خصم — امسح الطلب لو عايز تعدّل الأصناف
          </div>

          <div
            v-for="item in cart"
            :key="cartKey(item.menu_item_id, item.variant_id)"
            class="bg-amber-50 rounded-xl p-3 border border-amber-100"
          >
            <div class="flex items-start justify-between mb-2 gap-1">
              <span class="text-sm font-semibold text-gray-900 leading-tight flex-1">
                {{ item.name_ar || item.name }}
                <span v-if="item.variant_label" class="text-xs font-normal text-amber-700">— {{ item.variant_label }}</span>
              </span>
              <button
                @click="removeFromCart(item.menu_item_id, item.variant_id)"
                :disabled="cartLocked"
                class="text-red-400 hover:text-red-600 text-lg leading-none w-5 h-5 flex items-center justify-center rounded hover:bg-red-50 transition-colors flex-shrink-0 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent"
              >×</button>
            </div>

            <div class="flex items-center justify-between">
              <div class="flex items-center gap-1.5">
                <button
                  @click="adjustQty(item.menu_item_id, item.variant_id, -1)"
                  :disabled="cartLocked"
                  class="w-7 h-7 rounded-lg bg-white border border-amber-200 hover:bg-amber-100 text-sm font-bold transition-colors leading-none disabled:opacity-40 disabled:cursor-not-allowed"
                >−</button>
                <span class="text-sm font-black w-6 text-center text-gray-900">{{ item.quantity }}</span>
                <button
                  @click="adjustQty(item.menu_item_id, item.variant_id, 1)"
                  :disabled="cartLocked"
                  class="w-7 h-7 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-sm font-bold transition-colors leading-none disabled:opacity-40 disabled:cursor-not-allowed"
                >+</button>
              </div>
              <span class="text-sm font-black text-amber-700">{{ item.price * item.quantity }} ج</span>
            </div>

            <button
              @click="openNoteEditor(item.menu_item_id, item.variant_id, item.notes)"
              :disabled="cartLocked"
              class="mt-1.5 text-xs text-gray-400 hover:text-amber-600 transition-colors text-right w-full truncate disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {{ item.notes ? `📝 ${item.notes}` : '+ ملاحظة' }}
            </button>
          </div>
        </div>

        <!-- Footer -->
        <div class="border-t border-stone-200 p-3 space-y-3 bg-white">

          <!-- Total -->
          <div class="flex justify-between items-center">
            <span class="text-base font-bold text-gray-900">المجموع</span>
            <span class="text-xl font-black text-amber-700">{{ displayTotal }} ج</span>
          </div>

          <!-- #5: تطبيق خصم — قبل الإرسال للبار، بنفس محرك الخصم اللي
               OrderDetailModal بيستخدمه لطلب موجود بالفعل (راجع useOrderDiscount) -->
          <div v-if="!cartLocked" class="pt-0.5">
            <button
              @click="applyDiscountToCart"
              :disabled="!hasItems || applyingDiscount"
              class="w-full py-2 rounded-lg border-2 border-dashed border-amber-300 text-amber-700 text-xs font-bold hover:bg-amber-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-1.5"
            >
              <div v-if="applyingDiscount" class="animate-spin w-3 h-3 border-2 border-amber-600 border-t-transparent rounded-full" />
              <span>🏷️ تطبيق خصم</span>
            </button>
            <p v-if="discountError" class="text-xs text-red-600 mt-1 text-center">{{ discountError }}</p>
          </div>
          <div v-else class="rounded-lg border-2 border-green-200 bg-green-50 px-3 py-2 text-xs">
            <div class="flex justify-between text-green-700 font-bold">
              <span>خصم مطبّق ✓</span>
              <span v-if="pendingOrderSummary && Number(pendingOrderSummary.discount_amount) > 0">
                −{{ pendingOrderSummary.discount_amount }} ج
              </span>
            </div>
          </div>

          <!-- Payment method -->
          <div class="grid grid-cols-3 gap-1">
            <button
              v-for="m in [{ val: 'cash', label: 'كاش' }, { val: 'card', label: 'كارت' }, { val: 'wallet', label: 'محفظة' }]"
              :key="m.val"
              @click="paymentMethod = (m.val as 'cash' | 'card' | 'wallet')"
              :class="[
                'py-1.5 rounded-lg text-xs font-semibold border-2 transition-all',
                paymentMethod === m.val
                  ? 'border-amber-600 bg-amber-50 text-amber-700'
                  : 'border-stone-200 text-gray-600 hover:border-amber-200',
              ]"
            >{{ m.label }}</button>
          </div>

          <!-- Messages -->
          <transition name="fade">
            <div v-if="successMsg" class="bg-green-100 text-green-700 text-xs px-2 py-2 rounded-lg text-center font-medium">
              {{ successMsg }}
            </div>
          </transition>
          <transition name="fade">
            <div v-if="errorMsg" class="bg-red-100 text-red-700 text-xs px-2 py-2 rounded-lg text-center font-medium">
              {{ errorMsg }}
            </div>
          </transition>

          <!-- Buttons -->
          <div class="grid grid-cols-2 gap-2">
            <button
              @click="clearOrder"
              :disabled="!hasItems || cancellingPendingOrder"
              class="py-2.5 rounded-xl border-2 border-stone-200 text-sm font-semibold text-gray-600 hover:bg-gray-50 disabled:opacity-40 transition-colors"
            >{{ cancellingPendingOrder ? 'جاري الإلغاء...' : 'مسح' }}</button>
            <button
              @click="submitOrder"
              :disabled="!hasItems || submitting || cancellingPendingOrder"
              class="py-2.5 rounded-xl bg-amber-600 text-white text-sm font-bold hover:bg-amber-700 disabled:opacity-50 transition-colors flex items-center justify-center gap-1.5"
            >
              <div v-if="submitting" class="animate-spin w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full" />
              <span>{{ submitting ? 'جاري...' : 'تأكيد الطلب' }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Quick Qty Pad Modal ── -->
    <Transition name="modal">
      <div
        v-if="qtyPadItem"
        class="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
        @click.self="qtyPadItem = null"
      >
        <div class="bg-white rounded-2xl shadow-2xl w-64 overflow-hidden">
          <!-- Header -->
          <div class="bg-amber-600 text-white px-4 py-3 text-center">
            <div class="font-bold">{{ qtyPadItem.name_ar || qtyPadItem.name }}</div>
            <div class="text-xs text-amber-100 mt-0.5">{{ qtyPadItem.price }} ج × {{ qtyPadValue }} = {{ qtyPadItem.price * (parseInt(qtyPadValue) || 1) }} ج</div>
          </div>

          <!-- Display -->
          <div class="bg-gray-50 px-4 py-3 text-center">
            <div class="text-4xl font-black text-gray-900">{{ qtyPadValue }}</div>
          </div>

          <!-- Number pad -->
          <div class="grid grid-cols-3 gap-px bg-stone-200 border-t border-stone-200">
            <button
              v-for="key in ['7','8','9','4','5','6','1','2','3','C','0','⌫']"
              :key="key"
              @click="qtyPadPress(key)"
              :class="[
                'py-4 text-lg font-bold bg-white hover:bg-amber-50 transition-colors',
                key === 'C' ? 'text-red-500' : key === '⌫' ? 'text-gray-500' : 'text-gray-900',
              ]"
            >{{ key }}</button>
          </div>

          <!-- Confirm -->
          <button
            @click="confirmQtyPad"
            class="w-full py-4 bg-amber-600 text-white font-bold text-lg hover:bg-amber-700 transition-colors"
          >إضافة {{ qtyPadValue }} قطعة</button>
        </div>
      </div>
    </Transition>

    <!-- ── Note Editor Modal ── -->
    <Transition name="modal">
      <div
        v-if="editingNoteId !== null"
        class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
        @click.self="editingNoteId = null"
      >
        <div class="bg-white rounded-2xl p-5 w-full max-w-sm shadow-2xl">
          <h3 class="font-bold text-gray-900 mb-1">ملاحظة على الصنف</h3>
          <p class="text-xs text-gray-400 mb-3">مثال: بدون سكر، ثلج كتير، ساخن جداً</p>
          <textarea
            v-model="tempNote"
            rows="3"
            placeholder="اكتب الملاحظة هنا..."
            class="w-full border border-stone-300 rounded-xl p-3 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500 resize-none"
          />
          <div class="flex gap-2 mt-3">
            <button
              @click="editingNoteId = null"
              class="flex-1 py-2.5 border-2 border-stone-200 rounded-xl text-sm font-semibold text-gray-600 hover:bg-gray-50"
            >إلغاء</button>
            <button
              @click="saveNote"
              class="flex-1 py-2.5 bg-amber-600 text-white rounded-xl text-sm font-bold hover:bg-amber-700"
            >حفظ</button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- ── اختيار الحجم/النوع (Variant) — لصنف عنده متغيّرات متاحة، لازم
         يتحدد واحد قبل الإضافة للسلة (الباك إند بيرفض غير كده). ── -->
    <Transition name="modal">
      <div
        v-if="variantPickerItem"
        class="fixed inset-0 bg-black/60 z-50 flex items-center justify-center p-4"
        @click.self="variantPickerItem = null"
      >
        <div class="bg-white rounded-2xl shadow-2xl w-72 overflow-hidden">
          <div class="bg-amber-600 text-white px-4 py-3 text-center font-bold">
            اختر الحجم/النوع — {{ variantPickerItem.name_ar || variantPickerItem.name }}
          </div>
          <div class="p-3 space-y-2">
            <button
              v-for="variant in variantPickerItem.variants!.filter(v => v.is_available)"
              :key="variant.id"
              @click="addToCartWithVariant(variantPickerItem!, variant)"
              class="w-full flex items-center justify-between gap-2 p-3 rounded-xl border-2 border-stone-200 hover:border-amber-400 hover:bg-amber-50 transition-all text-right"
            >
              <span class="font-semibold text-gray-900 text-sm">{{ variant.name_ar || variant.name }}</span>
              <span class="font-black text-amber-700">{{ variant.price }} ج</span>
            </button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- ── الطلبات الجارية — كاشير يحصّل طلبات البار/الكافيه ── -->
    <Transition name="modal">
      <div
        v-if="activeOrdersOpen"
        class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
        @click.self="activeOrdersOpen = false"
      >
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-lg max-h-[80vh] flex flex-col overflow-hidden">
          <!-- Header -->
          <div class="bg-amber-600 text-white px-5 py-4 flex items-center justify-between flex-shrink-0">
            <div>
              <h2 class="font-black text-lg">🧾 الطلبات الجارية</h2>
              <p class="text-xs text-amber-100 mt-0.5">اختر طلباً لتحصيله أو عرض تفاصيله</p>
            </div>
            <button @click="activeOrdersOpen = false" class="text-amber-200 hover:text-white text-2xl leading-none">×</button>
          </div>

          <!-- Payment method selector -->
          <div class="px-5 py-3 border-b border-stone-100 bg-amber-50 flex items-center gap-3 flex-shrink-0">
            <span class="text-xs font-bold text-gray-600">طريقة الدفع:</span>
            <div class="flex gap-1">
              <button
                v-for="m in [{ val: 'cash', label: 'كاش 💵' }, { val: 'card', label: 'كارت 💳' }, { val: 'wallet', label: 'محفظة 📱' }]"
                :key="m.val"
                @click="cafePayingMethod = (m.val as 'cash' | 'card' | 'wallet')"
                :class="[
                  'px-3 py-1 rounded-lg text-xs font-semibold border-2 transition-all',
                  cafePayingMethod === m.val
                    ? 'border-amber-600 bg-amber-600 text-white'
                    : 'border-stone-200 text-gray-600 hover:border-amber-300',
                ]"
              >{{ m.label }}</button>
            </div>
          </div>

          <!-- Messages -->
          <div v-if="cafePaySuccess" class="bg-green-100 text-green-700 text-sm px-5 py-2 text-center font-medium flex-shrink-0">{{ cafePaySuccess }}</div>
          <div v-if="cafePayError" class="bg-red-100 text-red-700 text-sm px-5 py-2 text-center font-medium flex-shrink-0">{{ cafePayError }}</div>

          <!-- Orders list -->
          <div class="flex-1 overflow-y-auto p-4">
            <div v-if="activeOrdersLoading" class="flex justify-center py-10">
              <div class="animate-spin w-6 h-6 border-2 border-amber-600 border-t-transparent rounded-full" />
            </div>
            <div v-else-if="activeOrders.length === 0" class="flex flex-col items-center justify-center py-12 text-gray-400">
              <div class="text-4xl mb-3">✅</div>
              <p class="font-medium">لا توجد طلبات جارية</p>
            </div>
            <div v-else class="space-y-3">
              <div
                v-for="order in activeOrders"
                :key="order.id"
                class="bg-white rounded-xl border-2 border-stone-200 p-4 flex items-center justify-between gap-3 hover:border-amber-300 transition-colors"
              >
                <div class="flex-1 min-w-0">
                  <div class="flex items-center gap-2 mb-1">
                    <span class="font-black text-gray-900">#{{ order.order_number }}</span>
                    <span :class="['text-xs px-2 py-0.5 rounded-full font-semibold', cafeStatusColor(order.status)]">
                      {{ cafeStatusLabel(order.status) }}
                    </span>
                  </div>
                  <div class="text-xs text-gray-500">{{ cafeTableLabelFor(order) }}</div>
                  <div class="text-base font-black text-amber-700 mt-1">{{ order.total }} ج</div>
                </div>
                <div class="flex flex-col gap-2 flex-shrink-0">
                  <button
                    @click="collectCafeOrder(order)"
                    :disabled="cafePayingId === order.id"
                    class="px-4 py-2 bg-green-600 hover:bg-green-700 text-white text-sm font-bold rounded-lg transition-colors disabled:opacity-50 flex items-center gap-1.5"
                  >
                    <div v-if="cafePayingId === order.id" class="animate-spin w-3 h-3 border-2 border-white border-t-transparent rounded-full" />
                    <span>💰 تحصيل</span>
                  </button>
                  <button
                    @click="openOrderDetail(order.id)"
                    class="px-4 py-2 bg-stone-100 hover:bg-stone-200 text-gray-700 text-xs font-semibold rounded-lg transition-colors"
                  >
                    تفاصيل
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Footer -->
          <div class="px-5 py-3 border-t border-stone-100 flex justify-between items-center flex-shrink-0">
            <button @click="loadActiveOrders" class="text-xs text-amber-600 hover:underline font-medium">🔄 تحديث</button>
            <button @click="activeOrdersOpen = false" class="px-4 py-2 bg-stone-100 hover:bg-stone-200 rounded-lg text-sm font-semibold text-gray-700 transition-colors">إغلاق</button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- ── Order Detail Modal ── -->
    <OrderDetailModal
      v-if="selectedOrderId !== null"
      :order-id="selectedOrderId"
      module="cafe"
      @close="onOrderDetailClosed"
      @changed="loadActiveOrders"
    />

    <!-- ── #13: Held Orders Modal — استعادة طلب معلّق وإرساله للبار ── -->
    <Transition name="modal">
      <div
        v-if="heldOrdersOpen"
        class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
        @click.self="heldOrdersOpen = false"
      >
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-md max-h-[70vh] flex flex-col overflow-hidden">
          <div class="bg-slate-700 text-white px-5 py-4 flex items-center justify-between flex-shrink-0">
            <div>
              <h2 class="font-black text-lg">⏸ الطلبات المعلّقة</h2>
              <p class="text-xs text-slate-300 mt-0.5">اختر طلباً لإرساله للبار مباشرةً</p>
            </div>
            <button @click="heldOrdersOpen = false" class="text-slate-300 hover:text-white text-2xl leading-none">×</button>
          </div>

          <div class="flex-1 overflow-y-auto p-4">
            <div v-if="heldOrdersLoading" class="flex justify-center py-10">
              <div class="animate-spin w-6 h-6 border-2 border-slate-600 border-t-transparent rounded-full" />
            </div>
            <div v-else-if="heldOrders.length === 0" class="flex flex-col items-center justify-center py-12 text-gray-400">
              <div class="text-4xl mb-3">✅</div>
              <p class="font-medium">لا توجد طلبات معلّقة</p>
            </div>
            <div v-else class="space-y-3">
              <div
                v-for="order in heldOrders"
                :key="order.id"
                class="bg-white rounded-xl border-2 border-slate-200 p-4 flex items-center justify-between gap-3"
              >
                <div class="flex-1 min-w-0">
                  <div class="font-black text-gray-900">#{{ order.order_number }}</div>
                  <div class="text-xs text-gray-500 mt-0.5">
                    {{ cafeTableLabelFor(order) }}
                  </div>
                  <div class="text-base font-black text-amber-700 mt-1">{{ order.total }} ج</div>
                </div>
                <button
                  @click="resumeHeldOrder(order)"
                  :disabled="resumingOrderId === order.id"
                  class="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white text-sm font-bold rounded-lg transition-colors disabled:opacity-50 flex items-center gap-1.5"
                >
                  <div v-if="resumingOrderId === order.id" class="animate-spin w-3 h-3 border-2 border-white border-t-transparent rounded-full" />
                  <span>▶ إرسال للبار</span>
                </button>
              </div>
            </div>
          </div>

          <div class="px-5 py-3 border-t border-stone-100 flex justify-between items-center flex-shrink-0">
            <button @click="loadHeldOrders" class="text-xs text-slate-600 hover:underline font-medium">🔄 تحديث</button>
            <button @click="heldOrdersOpen = false" class="px-4 py-2 bg-stone-100 hover:bg-stone-200 rounded-lg text-sm font-semibold text-gray-700 transition-colors">إغلاق</button>
          </div>
        </div>
      </div>
    </Transition>

  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s ease;
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
.modal-enter-active > div,
.modal-leave-active > div {
  transition: transform 0.2s ease;
}
.modal-enter-from > div,
.modal-leave-to > div {
  transform: scale(0.95) translateY(8px);
}
</style>
