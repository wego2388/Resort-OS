<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api } from '@resort-os/core'
import { useOfflineQueue, usePrintDocument, useOrderDiscount } from '@resort-os/core/composables'
import { AppModal, AppBadge, EmptyState, useToast } from '@resort-os/ui'
import OrderDetailModal from '../../components/OrderDetailModal.vue'

const { isOnline, pendingCount, submitOrder: submitOrderOnlineOrQueue, lastPartialRejection } = useOfflineQueue()
const { printBlob } = usePrintDocument()
// #5: زرار "تطبيق خصم" وقت بناء طلب جديد — نفس الـ composable المستخدم في
// OrderDetailModal، عشان محرك الخصم يفضل مكان واحد (راجع applyDiscountToCart تحت)
const { applyingDiscount, discountError, applyDiscount: applyDiscountRule } = useOrderDiscount('restaurant')
const toast = useToast()

const branchId = parseInt(localStorage.getItem('branch_id') ?? '1')

// ── Types ──────────────────────────────────────────────────────────────────────
interface Table    { id: number; table_number: string; status: string; capacity: number }
interface Category { id: number; name: string; name_ar: string }
interface Variant  { id: number; name: string; name_ar: string | null; price: number; is_available: boolean }
interface MenuItem {
  id: number; name: string; name_ar: string; price: number; is_available: boolean
  category_id: number; description_ar?: string; variants?: Variant[]
  available_from_time?: string | null; available_until_time?: string | null
}
interface CartItem {
  menu_item_id: number; variant_id: number | null; variant_label: string | null
  name: string; name_ar: string; price: number; quantity: number; notes: string
}

// ── State ──────────────────────────────────────────────────────────────────────
const tables            = ref<Table[]>([])
const categories        = ref<Category[]>([])
const menuItems         = ref<MenuItem[]>([])
const selectedTable     = ref<Table | null>(null)
const selectedCategoryId = ref<number | null>(null)
const cart              = ref<CartItem[]>([])
const covers            = ref(1)
// UI-only عند وقت الطلب — الدفع الفعلي بيحصل لاحقًا (بعد ما الطلب يتقدّم)
// من "الطلبات الجارية" تحت، فيه الكاشير بيختار طريقة الدفع الحقيقية وقت
// إتمام الدفع (راجع OrderDetailModal + activeOrders تحت). مطعم dine-in
// بيتاخد فيه الأوردر الأول والدفع بعدين، عكس الكافيه (بيع فوري عند الكاونتر).
const paymentMethod     = ref<'cash' | 'card' | 'room'>('cash')
const loading           = ref(false)
const submitting        = ref(false)
const successMsg        = ref('')
const errorMsg          = ref('')

// ── #5: تطبيق خصم قبل الإرسال للمطبخ ──────────────────────────────────
// POST /restaurant/orders/{id}/discount محتاج order_id حقيقي موجود في
// الداتابيز بالفعل (راجع services.apply_order_discount — بيقرا order.items/
// subtotal/branch_id مباشرة)، لكن السلة هنا لسه client-side بحتة قبل
// الإرسال. الحل: أول ما الكاشير يضغط "تطبيق خصم"، نعمل POST .../orders/hold
// (نفس endpoint الطلب المعلّق الموجود أصلاً — بيسجّل الطلب من غير ما
// يوصل للمطبخ) عشان يبقى عندنا order_id حقيقي، وبعدين نطبّق الخصم عليه
// بنفس الـ composable المستخدم في OrderDetailModal. لحد ما الطلب ده يتبعت
// فعليًا (submitOrder) أو يتلغي (clearOrder)، السلة بتتقفل من التعديل —
// عشان مفيش desync ممكن يحصل بين الأصناف المحلية والطلب المحفوظ سيرفر-سايد.
const pendingOrderId      = ref<number | null>(null)
const pendingOrderNumber  = ref('')
const pendingOrderSummary = ref<{ discount_amount: number | string; total: number | string } | null>(null)
const cancellingPendingOrder = ref(false)
const cartLocked = computed(() => pendingOrderId.value !== null)

// Note editor modal — مفتاح مركّب (راجع cartKey) عشان يميّز بين سطرين
// لنفس الصنف بمتغيّرات مختلفة
const editingNoteId  = ref<string | null>(null)
const tempNote       = ref('')

// ── Active orders (الطلبات الجارية) — نقطة الدخول الوحيدة للكاشير عشان
// يلاقي طلب اتبعت للمطبخ ويقفل حسابه (يقدّم/يدفع) من غير ما يحتاج ID
// جاهز. GET /restaurant/orders كاشير+ بس (list_orders)، فده متسق مع إن
// الشاشة دي أصلاً محمية بـ requiredRole: 'cashier' في الراوتر.
interface ActiveOrder { id: number; order_number: string; status: string; table_id: number | null; order_type: string; total: number | string }
const activeOrdersOpen = ref(false)
const activeOrders      = ref<ActiveOrder[]>([])
const activeOrdersLoading = ref(false)
const selectedOrderId   = ref<number | null>(null)

const ACTIVE_STATUSES = new Set(['open', 'in_kitchen', 'served'])

async function loadActiveOrders() {
  activeOrdersLoading.value = true
  try {
    // #17: نجيب *كل* الطلبات الجارية بغض النظر عن العدد — بنستخدم helper
    // بيعمل pagination تلقائي (page 1, 2, ...) حتى ما يبقاش فيه صفحات تانية.
    // كل status في request منفصل لأن الـ backend بيدعم فلتر status واحد بس.
    const fetchAll = async (status: string): Promise<ActiveOrder[]> => {
      const PAGE_SIZE = 100
      const results: ActiveOrder[] = []
      let page = 1
      while (true) {
        const res = await api.get('/api/v1/restaurant/orders', {
          params: { branch_id: branchId, status, page, size: PAGE_SIZE },
        })
        const items: ActiveOrder[] = res.data?.items ?? res.data ?? []
        results.push(...items)
        // لو الصفحة مش ممتلئة يعني وصلنا لآخر البيانات
        if (items.length < PAGE_SIZE) break
        page++
      }
      return results
    }
    const [openOrders, kitchenOrders, servedOrders] = await Promise.all([
      fetchAll('open'),
      fetchAll('in_kitchen'),
      fetchAll('served'),
    ])
    activeOrders.value = [...openOrders, ...kitchenOrders, ...servedOrders]
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

function tableLabelFor(order: ActiveOrder): string {
  if (!order.table_id) return 'Takeaway'
  const t = tables.value.find(t => t.id === order.table_id)
  return t ? `طاولة ${t.table_number}` : `طاولة #${order.table_id}`
}

function openOrder(orderId: number) {
  activeOrdersOpen.value = false
  selectedOrderId.value = orderId
}

// ── #3: إضافة أصناف لطلب مفتوح ───────────────────────────────────────────────
// الـ backend endpoint: POST /restaurant/orders/{id}/items
// يقبل: { items: [{ menu_item_id, variant_id?, quantity, notes? }] }
const addItemsOrderId   = ref<number | null>(null)
const addItemsOrderNum  = ref<string>('')
const addItemsCart      = ref<CartItem[]>([])
const addItemsSubmitting = ref(false)
const addItemsOpen      = computed(() => addItemsOrderId.value !== null)

function openAddItems(o: ActiveOrder) {
  activeOrdersOpen.value = false
  addItemsOrderId.value  = o.id
  addItemsOrderNum.value = o.order_number
  addItemsCart.value     = []
}

function addItemsAddToCart(item: MenuItem) {
  const availableVariants = (item.variants ?? []).filter(v => v.is_available)
  if (availableVariants.length > 0) {
    // نفس منطق الـ variantPicker الأصلي — لكن للـ add-items cart
    variantPickerItem.value = item
    variantPickerForAddItems.value = true
    return
  }
  const key = cartKey(item.id, null)
  const existing = addItemsCart.value.find(c => cartKey(c.menu_item_id, c.variant_id) === key)
  if (existing) { existing.quantity++; return }
  addItemsCart.value.push({
    menu_item_id: item.id, variant_id: null, variant_label: null,
    name: item.name, name_ar: item.name_ar, price: item.price, quantity: 1, notes: '',
  })
}

function addItemsAddToCartWithVariant(item: MenuItem, variant: Variant) {
  variantPickerItem.value = null
  variantPickerForAddItems.value = false
  const key = cartKey(item.id, variant.id)
  const existing = addItemsCart.value.find(c => cartKey(c.menu_item_id, c.variant_id) === key)
  if (existing) { existing.quantity++; return }
  addItemsCart.value.push({
    menu_item_id: item.id, variant_id: variant.id,
    variant_label: variant.name_ar || variant.name,
    name: item.name, name_ar: item.name_ar, price: variant.price, quantity: 1, notes: '',
  })
}

// علامة لتمييز variant picker بين new order و add-items
const variantPickerForAddItems = ref(false)

function onVariantPick(item: MenuItem, variant: Variant) {
  if (variantPickerForAddItems.value) {
    addItemsAddToCartWithVariant(item, variant)
  } else {
    addToCartWithVariant(item, variant)
  }
}

function onVariantPickerClose() {
  variantPickerItem.value = null
  variantPickerForAddItems.value = false
}

async function submitAddItems() {
  if (!addItemsCart.value.length || addItemsSubmitting.value) return
  addItemsSubmitting.value = true
  try {
    const res = await api.post(`/api/v1/restaurant/orders/${addItemsOrderId.value}/items`, {
      items: addItemsCart.value.map(i => ({
        menu_item_id: i.menu_item_id,
        variant_id:   i.variant_id ?? undefined,
        quantity:     i.quantity,
        notes:        i.notes || undefined,
      })),
    })
    // #4 fix: لو الطلب كان open (مش in_kitchen بعد)، الـ backend مش بيعمل
    // broadcast للـ KDS — لازم نبعت PATCH لـ in_kitchen عشان المطبخ يشوف الأصناف
    const updatedOrder = res.data
    if (updatedOrder?.status === 'open') {
      try {
        await api.patch(`/api/v1/restaurant/orders/${addItemsOrderId.value}/status`, { status: 'in_kitchen' })
      } catch {
        toast.warning('أُضيفت الأصناف لكن تعذّر إرسالها للمطبخ — غيّر حالة الطلب يدوياً')
      }
    }
    toast.success(`✓ أُضيفت ${addItemsCart.value.length} أصناف للطلب ${addItemsOrderNum.value}`)
    addItemsOrderId.value = null
    addItemsCart.value    = []
    loadActiveOrders()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'فشل إضافة الأصناف — حاول تاني')
  } finally {
    addItemsSubmitting.value = false
  }
}

function onOrderDetailClosed() {
  selectedOrderId.value = null
  loadActiveOrders()
}

// ── Computed ───────────────────────────────────────────────────────────────────
const searchQuery = ref('')
const searchInputEl = ref<HTMLInputElement | null>(null)

const filteredItems = computed(() => {
  let items = selectedCategoryId.value !== null
    ? menuItems.value.filter(i => i.category_id === selectedCategoryId.value && i.is_available)
    : menuItems.value.filter(i => i.is_available)
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    items = items.filter(i =>
      i.name.toLowerCase().includes(q) ||
      (i.name_ar ?? '').includes(q) ||
      (i.description_ar ?? '').includes(q)
    )
  }
  return items
})

const total    = computed(() => cart.value.reduce((s, i) => s + i.price * i.quantity, 0))
const hasItems = computed(() => cart.value.length > 0)
// #5: بعد تطبيق الخصم، الإجمالي الحقيقي (بعد VAT/خدمة/خصم) بييجي من السيرفر
// (pendingOrderSummary) مش من مجموع السلة الخام المحلي.
const displayTotal = computed(() => pendingOrderSummary.value?.total ?? total.value)

// ── متغيّرات (حجم/نوع) — لو الصنف عنده متغيّرات متاحة، لازم يتحدد واحد
// منهم إجباريًا وقت الطلب (الباك إند بيرفض غير كده)، فبدل الإضافة المباشرة
// للسلة بنفتح مودال اختيار صغير. صنف بدون متغيّرات سلوكه زي ما كان بالظبط. ──
const variantPickerItem = ref<MenuItem | null>(null)

// مفتاح تعريف سطر السلة — menu_item_id لوحده مش كافي لما يبقى فيه أكتر من
// سطر لنفس الصنف بمتغيّرات مختلفة (كابتشينو صغير + كابتشينو كبير في نفس
// الأوردر)، فكل عمليات المطابقة (إضافة/حذف/تعديل كمية/ملاحظة) لازم تستخدم
// الـ key المركّب ده بدل menu_item_id بمفرده.
function cartKey(menuItemId: number, variantId: number | null): string {
  return variantId != null ? `${menuItemId}:${variantId}` : `${menuItemId}`
}

// ── نافذة تقديم الصنف (wagdy.md P-03) — مثال: إفطار 07:00-11:00. عرض بصري
// بس (تحسين UX، يقلل محاولات طلب مرفوضة) — التحقق الحقيقي دايمًا سيرفر-سايد
// (services._check_item_available_now)، هنا نفس منطق النافذة العابرة لمنتصف
// الليل بالظبط، بس على وقت الجهاز المحلي (مفروض يبقى نفس توقيت المنتجع). ──
function isItemOutOfWindow(item: MenuItem): boolean {
  if (!item.available_from_time && !item.available_until_time) return false
  const toMinutes = (t: string) => {
    const [h, m] = t.split(':').map(Number)
    return h * 60 + m
  }
  const now = new Date()
  const nowMinutes = now.getHours() * 60 + now.getMinutes()
  const start = item.available_from_time ? toMinutes(item.available_from_time) : 0
  const end = item.available_until_time ? toMinutes(item.available_until_time) : 24 * 60 - 1
  if (start <= end) return !(nowMinutes >= start && nowMinutes <= end)
  return !(nowMinutes >= start || nowMinutes <= end)
}
function itemWindowLabel(item: MenuItem): string {
  const from = item.available_from_time?.slice(0, 5) ?? '00:00'
  const until = item.available_until_time?.slice(0, 5) ?? '23:59'
  return `متاح ${from}-${until}`
}

// ── Cart actions ───────────────────────────────────────────────────────────────
function addToCart(item: MenuItem) {
  if (cartLocked.value) return
  const availableVariants = (item.variants ?? []).filter(v => v.is_available)
  if (availableVariants.length > 0) {
    variantPickerItem.value = item
    return
  }
  const existing = cart.value.find(c => cartKey(c.menu_item_id, c.variant_id) === cartKey(item.id, null))
  if (existing) { existing.quantity++; return }
  cart.value.push({
    menu_item_id: item.id,
    variant_id:   null,
    variant_label: null,
    name:         item.name,
    name_ar:      item.name_ar,
    price:        item.price,
    quantity:     1,
    notes:        '',
  })
}

function addToCartWithVariant(item: MenuItem, variant: Variant) {
  if (cartLocked.value) return
  variantPickerItem.value = null
  variantPickerForAddItems.value = false
  const key = cartKey(item.id, variant.id)
  const existing = cart.value.find(c => cartKey(c.menu_item_id, c.variant_id) === key)
  if (existing) { existing.quantity++; return }
  cart.value.push({
    menu_item_id: item.id,
    variant_id:   variant.id,
    variant_label: variant.name_ar || variant.name,
    name:         item.name,
    name_ar:      item.name_ar,
    price:        variant.price,
    quantity:     1,
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
 * قبل كده عشان الطاولة ترجع تتاح والطلب ميفضلش معلّق للأبد بلا داعي. */
async function clearOrder() {
  if (pendingOrderId.value !== null) {
    cancellingPendingOrder.value = true
    try {
      await api.patch(`/api/v1/restaurant/orders/${pendingOrderId.value}/status`, { status: 'cancelled' })
    } catch {
      toast.error('تعذّر إلغاء الطلب المحفوظ من السيرفر — راجعه من الطلبات الجارية وألغِه يدويًا')
    } finally {
      cancellingPendingOrder.value = false
    }
  }
  cart.value = []
  covers.value = 1
  pendingOrderId.value = null
  pendingOrderNumber.value = ''
  pendingOrderSummary.value = null
}

/** #5: تطبيق أفضل قاعدة خصم نشطة على الطلب اللي بيتبنى دلوقتي. أول ضغطة
 * بتنشئ الطلب كـ "held" سيرفر-سايد (لسه ملوش وجود قبل كده)، وأي ضغطة بعد
 * كده بترجع تحسب الخصم تاني على نفس الطلب (مفيد لو قواعد الخصم اتغيّرت). */
async function applyDiscountToCart() {
  if (!hasItems.value || applyingDiscount.value) return
  errorMsg.value = ''

  if (pendingOrderId.value === null) {
    try {
      const { data } = await api.post(`/api/v1/restaurant/orders/hold?branch_id=${branchId}`, {
        table_id:     selectedTable.value?.id ?? null,
        order_type:   selectedTable.value ? 'dine_in' : 'takeaway',
        guests_count: covers.value,
        items: cart.value.map(i => ({
          menu_item_id: i.menu_item_id,
          variant_id:   i.variant_id ?? undefined,
          quantity:     i.quantity,
          notes:        i.notes || undefined,
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

// ── Helpers ────────────────────────────────────────────────────────────────────
function tableStatusLabel(status: string): string {
  if (status === 'available') return 'فارغة'
  if (status === 'occupied')  return 'مشغولة'
  return 'محجوزة'
}

function tableStatusDot(status: string): string {
  if (status === 'available') return 'bg-green-500'
  if (status === 'occupied')  return 'bg-red-500'
  return 'bg-amber-500'
}

// ── API calls ──────────────────────────────────────────────────────────────────
async function loadData() {
  loading.value = true
  try {
    const [tablesRes, catsRes, itemsRes] = await Promise.all([
      api.get('/api/v1/restaurant/tables', {
        params: { branch_id: branchId },
      }),
      api.get('/api/v1/restaurant/menu/categories', {
        params: { branch_id: branchId },
      }),
      api.get('/api/v1/restaurant/menu/items', {
        params: { branch_id: branchId, limit: 200 },
      }),
    ])

    tables.value     = tablesRes.data.tables    ?? tablesRes.data.items    ?? tablesRes.data
    categories.value = catsRes.data.categories  ?? catsRes.data.items      ?? catsRes.data
    menuItems.value  = itemsRes.data.items       ?? itemsRes.data

    if (categories.value.length) {
      selectedCategoryId.value = categories.value[0].id
    }
  } catch {
    // من غير إشعار كان الكاشير بيشوف قائمة أصناف فاضية من غير أي تفسير
    toast.error('تعذّر تحميل بيانات المطعم — تأكد من الاتصال وحاول تاني')
  } finally {
    loading.value = false
  }
}

/** تحديث خفيف لقائمة الطاولات بس — بعد نقل طلب لطاولة تانية (OrderDetailModal
 * "نقل لطاولة") حالة الطاولتين (القديمة/الجديدة) بتتغيّر سيرفر-سايد، فقائمة
 * الطاولات المستخدمة في تحديد طلب جديد لازم تتحدّث فورًا، مش تنتظر تحديث كامل. */
async function refreshTables() {
  try {
    const { data } = await api.get('/api/v1/restaurant/tables', { params: { branch_id: branchId } })
    tables.value = data.tables ?? data.items ?? data
  } catch {
    // فشل صامت — الطاولات هتتحدّث في المرة الجاية اللي loadData بيتنادى فيها
  }
}

/** ⚠️ باج حقيقي كان هنا (نفس اللي اتصلح في waiter/OrderView.vue.sendToKitchen):
 * إنشاء الطلب لوحده بيسيبه في status "open"/"held" — تذكرة الـ KDS بترتبط بس
 * بانتقالة →in_kitchen (services.update_order_status). من غير الـ PATCH ده،
 * أي طلب يتعمل من شاشة الكاشير هنا كان يوصل للسيرفر ويتسجّل، لكن المطبخ
 * ماكانش يشوفه خالص. لو الطلب كان "held" (اتنشأ وقت تطبيق خصم — راجع
 * applyDiscountToCart)، لازم يعدّي held→open الأول (نفس منطق
 * OrderDetailModal.resumeAndSend) قبل ما يتحول لـ in_kitchen. */
async function finalizeOrderToKitchen(orderId: number, wasHeld: boolean) {
  try {
    if (wasHeld) await api.patch(`/api/v1/restaurant/orders/${orderId}/status`, { status: 'open' })
    await api.patch(`/api/v1/restaurant/orders/${orderId}/status`, { status: 'in_kitchen' })
  } catch (e) {
    console.error('Failed to send order to kitchen', e)
    errorMsg.value = 'اتسجّل الطلب لكن حصل خطأ في إرساله للمطبخ — راجعه من الطلبات الجارية'
    setTimeout(() => { errorMsg.value = '' }, 5000)
  }

  try {
    const receiptRes = await api.get(`/api/v1/restaurant/orders/${orderId}/receipt`, {
      responseType: 'blob',
    })
    const outcome = printBlob(receiptRes.data, `receipt-${orderId}.pdf`)
    if (outcome.downloadedInstead) {
      errorMsg.value = 'الإيصال اتحمّل كملف (المتصفح منع نافذة الطباعة) — افتحه واطبعه يدويًا'
      setTimeout(() => { errorMsg.value = '' }, 5000)
    }
  } catch {
    // receipt optional — never block the order itself
  }
}

async function submitOrder() {
  if (!hasItems.value || submitting.value) return
  submitting.value = true
  try {
    if (pendingOrderId.value !== null) {
      // #5: الطلب اتنشأ بالفعل (held) وقت تطبيق الخصم — منعملش POST تاني،
      // بس نكمّل نفس الطلب للمطبخ.
      await finalizeOrderToKitchen(pendingOrderId.value, true)
    } else {
      const payload = {
        table_id:     selectedTable.value?.id ?? null,
        order_type:   selectedTable.value ? 'dine_in' : 'takeaway',
        guests_count: covers.value,
        items: cart.value.map(i => ({
          menu_item_id: i.menu_item_id,
          variant_id:   i.variant_id ?? undefined,
          quantity:     i.quantity,
          notes:        i.notes || undefined,
        })),
      }

      const data = await submitOrderOnlineOrQueue(branchId, payload)

      if (data === null) {
        // مفيش نت — اتحفظ في IndexedDB، هيتزامن أوتوماتيك لما الاتصال يرجع
        clearOrder()
        successMsg.value = '📥 الطلب محفوظ — هيتبعت للمطبخ أول ما النت يرجع'
        setTimeout(() => { successMsg.value = '' }, 4000)
        return
      }

      const orderId = data.id ?? data.order_id
      if (orderId) await finalizeOrderToKitchen(orderId, false)
    }

    // الطلب اتبعت فعليًا (أو فشل الإرسال بس اتسجّل — راجع الرسالة فوق) —
    // مفيش داعي نلغي حاجة في clearOrder() بعد كده، فنصفّر pendingOrderId الأول.
    pendingOrderId.value      = null
    pendingOrderNumber.value  = ''
    pendingOrderSummary.value = null
    clearOrder()
    successMsg.value = 'تم إرسال الطلب للمطبخ ✓'
    setTimeout(() => { successMsg.value = '' }, 3000)
  } catch (e: any) {
    errorMsg.value = e?.response?.data?.detail ?? 'فشل في إرسال الطلب'
    setTimeout(() => { errorMsg.value = '' }, 4000)
  } finally {
    submitting.value = false
  }
}

// ── اختصارات لوحة المفاتيح (wagdy.md #26) ──────────────────────────────────
// هدفها تسريع أكتر الحركات تكرارًا للكاشير من غير ما يحتاج يلمس الشاشة كل
// مرة: بحث سريع، إرسال الطلب، إغلاق مودال/مسح السلة. مش بديل لأزرار
// الماوس/اللمس — إضافة اختيارية بس فوقها.
function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el) return false
  const tag = el.tagName
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el.isContentEditable
}

function handleKeydown(e: KeyboardEvent) {
  // Esc بتقفل أقرب مودال مفتوح لو فيه واحد — وده لازم يشتغل حتى لو الفوكس
  // جوه حقل نص داخل المودال نفسه (زي textarea الملاحظة)، عشان ده السلوك
  // المتوقع من أي مستخدم. لو مفيش مودال مفتوح، بتمسح السلة (لو مسموح).
  if (e.key === 'Escape') {
    if (editingNoteId.value !== null) { editingNoteId.value = null; return }
    if (variantPickerItem.value !== null) { onVariantPickerClose(); return }
    if (addItemsOpen.value) { addItemsOrderId.value = null; addItemsCart.value = []; return }
    if (activeOrdersOpen.value) { activeOrdersOpen.value = false; return }
    if (selectedOrderId.value !== null) { onOrderDetailClosed(); return }
    if (isTypingTarget(e.target)) return
    // نفس شرط تعطيل زرار "مسح" بالظبط — cartLocked مش بيمنع المسح لأن
    // clearOrder() هي اللي بتلغي الطلب المعلّق سيرفر-سايد أصلاً.
    if (hasItems.value && !cancellingPendingOrder.value) clearOrder()
    return
  }

  // باقي الاختصارات ميشتغلوش وقت الكتابة في أي حقل نص — أشهر باج في أي
  // تطبيق اختصارات لوحة مفاتيح.
  if (isTypingTarget(e.target)) return

  if (e.key === '/') {
    e.preventDefault()
    searchInputEl.value?.focus()
    return
  }

  if (e.key === 'Enter') {
    // نفس شرط تعطيل زرار "إرسال للمطبخ" بالظبط. preventDefault هنا كمان
    // بيمنع تفعيل الزرار اللي ممكن يكون فوكس عليه (زي صنف من المنيو) من
    // إضافة نفس الصنف مرة تانية في نفس الضغطة.
    if (hasItems.value && !submitting.value && !cancellingPendingOrder.value) {
      e.preventDefault()
      submitOrder()
    }
  }
}

onMounted(() => {
  loadData()
  loadActiveOrders()
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<template>
  <div class="flex flex-col h-full" dir="rtl">

    <!-- ── Offline banner — visible الطول، مش toast بيختفي ── -->
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
    <div
      v-if="lastPartialRejection && lastPartialRejection.length"
      class="bg-red-100 text-red-800 text-xs font-semibold px-4 py-2 flex-shrink-0 border-b border-red-200"
    >
      ⚠️ تم رفض بعض الأصناف من طلب محفوظ سابقاً (نفاد المخزون):
      {{ lastPartialRejection.map(i => `${i.name} (×${i.requested_qty})`).join('، ') }}
    </div>

    <!-- ── Top bar: table + covers + categories ── -->
    <div class="bg-white border-b border-stone-200 px-4 py-3 flex flex-wrap gap-3 items-center shadow-sm flex-shrink-0">

      <!-- Table selector -->
      <div class="flex items-center gap-2">
        <label class="text-sm font-semibold text-gray-700">الطاولة:</label>
        <div class="relative">
          <select
            v-model="selectedTable"
            :disabled="cartLocked"
            class="border border-stone-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 appearance-none pr-7 bg-white cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <option :value="null">Takeaway (بدون طاولة)</option>
            <option v-for="t in tables" :key="t.id" :value="t">
              طاولة {{ t.table_number }} — {{ tableStatusLabel(t.status) }}
            </option>
          </select>
          <!-- Status dot for selected table -->
          <span
            v-if="selectedTable"
            class="absolute left-2 top-1/2 -translate-y-1/2 w-2 h-2 rounded-full"
            :class="tableStatusDot(selectedTable.status)"
          />
        </div>
      </div>

      <!-- Covers counter -->
      <div class="flex items-center gap-2">
        <label class="text-sm font-semibold text-gray-700">الغطاءات:</label>
        <div class="flex items-center gap-1 bg-gray-100 rounded-lg p-0.5">
          <button
            @click="covers = Math.max(1, covers - 1)"
            :disabled="cartLocked"
            class="w-7 h-7 rounded-md bg-white hover:bg-gray-50 text-sm font-bold shadow-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >−</button>
          <span class="w-8 text-center font-bold text-sm">{{ covers }}</span>
          <button
            @click="covers++"
            :disabled="cartLocked"
            class="w-7 h-7 rounded-md bg-white hover:bg-gray-50 text-sm font-bold shadow-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >+</button>
        </div>
      </div>

      <!-- Active orders (send served/complete payment) -->
      <button
        @click="openActiveOrders"
        class="relative px-3 py-1.5 bg-white border-2 border-blue-400 text-blue-700 rounded-lg font-bold text-sm hover:bg-blue-50 transition-colors"
      >
        🧾 الطلبات الجارية
        <AppBadge v-if="activeOrders.length" variant="info" size="sm" class="mr-1.5">{{ activeOrders.length }}</AppBadge>
      </button>

      <!-- Category tabs -->
      <div class="flex gap-1 flex-wrap">
        <button
          @click="selectedCategoryId = null"
          :class="[
            'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
            selectedCategoryId === null
              ? 'bg-blue-600 text-white shadow-sm'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200',
          ]"
        >الكل</button>
        <button
          v-for="cat in categories"
          :key="cat.id"
          @click="selectedCategoryId = cat.id"
          :class="[
            'px-3 py-1.5 rounded-lg text-sm font-medium transition-colors',
            selectedCategoryId === cat.id
              ? 'bg-blue-600 text-white shadow-sm'
              : 'bg-gray-100 text-gray-600 hover:bg-gray-200',
          ]"
        >{{ cat.name_ar || cat.name }}</button>
      </div>

      <!-- #12: حقل بحث سريع — لمطاعم عندها 50+ صنف -->
      <div class="relative">
        <input
          ref="searchInputEl"
          v-model="searchQuery"
          type="text"
          placeholder="🔍 بحث في الأصناف... (/)"
          class="border border-stone-200 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400 bg-white w-48"
        />
        <button
          v-if="searchQuery"
          @click="searchQuery = ''"
          class="absolute left-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 text-lg leading-none"
        >×</button>
      </div>

      <!-- #26: تلميح اختصارات لوحة المفاتيح -->
      <span
        class="text-gray-300 hover:text-gray-500 cursor-help text-sm select-none transition-colors"
        title="⌨️ اختصارات لوحة المفاتيح:&#10;/  — تركيز على حقل البحث&#10;Enter — إرسال الطلب للمطبخ&#10;Esc — إغلاق نافذة مفتوحة، أو مسح الطلب"
      >⌨️</span>

    </div>

    <!-- ── Main split: menu + order ── -->
    <div class="flex flex-1 overflow-hidden">

      <!-- Menu grid (left/main area) -->
      <div class="flex-1 overflow-y-auto p-4 bg-stone-50">
        <div v-if="loading" class="flex items-center justify-center h-40">
          <div class="animate-spin w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full" />
        </div>

        <div v-else class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-3">
          <button
            v-for="item in filteredItems"
            :key="item.id"
            @click="addToCart(item)"
            :disabled="cartLocked || isItemOutOfWindow(item)"
            :title="isItemOutOfWindow(item) ? itemWindowLabel(item) : undefined"
            class="relative bg-white rounded-xl border border-stone-200 p-4 text-right hover:border-blue-400 hover:shadow-md transition-all active:scale-95 active:shadow-sm flex flex-col justify-between min-h-[90px] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:border-stone-200 disabled:hover:shadow-none"
          >
            <div class="font-semibold text-gray-900 text-sm leading-tight mb-2">
              {{ item.name_ar || item.name }}
            </div>
            <div v-if="(item.variants ?? []).filter(v => v.is_available).length > 0" class="text-sm font-bold text-blue-700">
              من {{ Math.min(...item.variants!.filter(v => v.is_available).map(v => v.price)) }}<span class="text-xs font-normal text-gray-400 mr-0.5">ج · اختر الحجم</span>
            </div>
            <div v-else class="text-lg font-black text-blue-700">
              {{ item.price }}<span class="text-xs font-normal text-gray-400 mr-0.5">ج</span>
            </div>
            <span
              v-if="isItemOutOfWindow(item)"
              class="absolute top-1.5 left-1.5 bg-stone-700/90 text-white text-[10px] font-semibold px-1.5 py-0.5 rounded"
            >⏰ {{ itemWindowLabel(item) }}</span>
          </button>
        </div>

        <div v-if="!loading && filteredItems.length === 0" class="flex flex-col items-center justify-center py-16 text-gray-400">
          <div class="text-4xl mb-2">🍽️</div>
          <p class="text-sm">{{ searchQuery ? `لا نتائج لـ "${searchQuery}"` : 'لا توجد أصناف في هذه الفئة' }}</p>
        </div>
      </div>

      <!-- ── Order panel (right sidebar) ── -->
      <div class="w-72 bg-white border-r border-stone-200 flex flex-col flex-shrink-0 shadow-lg">

        <!-- Order header -->
        <div class="p-4 border-b border-stone-100 bg-gray-50">
          <div class="font-bold text-gray-900">
            {{ selectedTable ? `طاولة ${selectedTable.table_number}` : 'Takeaway' }}
          </div>
          <div class="text-xs text-gray-500 mt-0.5">
            {{ covers }} {{ covers === 1 ? 'غطاء' : 'غطاءات' }}
            <span v-if="selectedTable" :class="['inline-block w-2 h-2 rounded-full mr-1.5 mb-0.5', tableStatusDot(selectedTable.status)]" />
          </div>
        </div>

        <!-- Cart items -->
        <div class="flex-1 overflow-y-auto p-3 space-y-2">
          <div v-if="cart.length === 0" class="flex flex-col items-center justify-center py-10 text-gray-400">
            <div class="text-3xl mb-2">🛒</div>
            <p class="text-sm">اختر أصناف من القائمة</p>
          </div>

          <!-- #5: بعد تطبيق الخصم، الطلب بيتسجّل سيرفر-سايد (held) — السلة
               بتتقفل من التعديل عشان تفضل مطابقة للطلب المحفوظ بالظبط. -->
          <div v-if="cartLocked" class="bg-green-50 border border-green-200 rounded-lg px-3 py-2 text-xs text-green-700">
            🔒 الطلب #{{ pendingOrderNumber }} اتسجّل وطُبّق عليه خصم — امسح الطلب لو عايز تعدّل الأصناف
          </div>

          <div
            v-for="item in cart"
            :key="cartKey(item.menu_item_id, item.variant_id)"
            class="bg-stone-50 rounded-lg p-3 border border-stone-200"
          >
            <!-- Item name + remove -->
            <div class="flex items-start justify-between mb-2 gap-1">
              <span class="text-sm font-semibold text-gray-900 leading-tight flex-1">
                {{ item.name_ar || item.name }}
                <span v-if="item.variant_label" class="text-xs font-normal text-blue-600">— {{ item.variant_label }}</span>
              </span>
              <button
                @click="removeFromCart(item.menu_item_id, item.variant_id)"
                :disabled="cartLocked"
                class="text-red-400 hover:text-red-600 text-lg leading-none flex-shrink-0 w-5 h-5 flex items-center justify-center rounded hover:bg-red-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:bg-transparent"
              >×</button>
            </div>

            <!-- Qty controls + subtotal -->
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-1.5">
                <button
                  @click="adjustQty(item.menu_item_id, item.variant_id, -1)"
                  :disabled="cartLocked"
                  class="w-6 h-6 rounded bg-gray-200 hover:bg-gray-300 text-sm font-bold transition-colors leading-none disabled:opacity-40 disabled:cursor-not-allowed"
                >−</button>
                <span class="text-sm font-bold w-5 text-center">{{ item.quantity }}</span>
                <button
                  @click="adjustQty(item.menu_item_id, item.variant_id, 1)"
                  :disabled="cartLocked"
                  class="w-6 h-6 rounded bg-blue-100 hover:bg-blue-200 text-blue-700 text-sm font-bold transition-colors leading-none disabled:opacity-40 disabled:cursor-not-allowed"
                >+</button>
              </div>
              <span class="text-sm font-bold text-blue-700">{{ item.price * item.quantity }} ج</span>
            </div>

            <!-- Notes -->
            <button
              @click="openNoteEditor(item.menu_item_id, item.variant_id, item.notes)"
              :disabled="cartLocked"
              class="mt-2 text-xs text-gray-400 hover:text-blue-600 transition-colors text-right w-full truncate disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {{ item.notes ? `📝 ${item.notes}` : '+ إضافة ملاحظة' }}
            </button>
          </div>
        </div>

        <!-- Footer: total + payment + submit -->
        <div class="border-t border-stone-200 p-3 space-y-3 bg-white">

          <!-- Total -->
          <div class="flex justify-between items-center">
            <span class="text-base font-bold text-gray-900">المجموع</span>
            <span class="text-xl font-black text-blue-700">{{ displayTotal }} ج</span>
          </div>

          <!-- #5: تطبيق خصم — قبل الإرسال للمطبخ، بنفس محرك الخصم اللي
               OrderDetailModal بيستخدمه لطلب موجود بالفعل (راجع useOrderDiscount) -->
          <div v-if="!cartLocked" class="pt-0.5">
            <button
              @click="applyDiscountToCart"
              :disabled="!hasItems || applyingDiscount"
              class="w-full py-2 rounded-lg border-2 border-dashed border-blue-300 text-blue-700 text-xs font-bold hover:bg-blue-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-1.5"
            >
              <div v-if="applyingDiscount" class="animate-spin w-3 h-3 border-2 border-blue-600 border-t-transparent rounded-full" />
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
              v-for="m in [{ val: 'cash', label: 'كاش' }, { val: 'card', label: 'كارت' }, { val: 'room', label: 'أوضة' }]"
              :key="m.val"
              @click="paymentMethod = (m.val as 'cash' | 'card' | 'room')"
              :class="[
                'py-1.5 rounded-lg text-xs font-semibold border-2 transition-all',
                paymentMethod === m.val
                  ? 'border-blue-600 bg-blue-50 text-blue-700'
                  : 'border-stone-200 text-gray-600 hover:border-blue-200',
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

          <!-- Action buttons -->
          <div class="grid grid-cols-2 gap-2">
            <button
              @click="clearOrder"
              :disabled="!hasItems || cancellingPendingOrder"
              class="py-2.5 rounded-xl border-2 border-stone-200 text-sm font-semibold text-gray-600 hover:bg-gray-50 disabled:opacity-40 transition-colors"
            >{{ cancellingPendingOrder ? 'جاري الإلغاء...' : 'مسح' }}</button>
            <button
              @click="submitOrder"
              :disabled="!hasItems || submitting || cancellingPendingOrder"
              class="py-2.5 rounded-xl bg-blue-700 text-white text-sm font-bold hover:bg-blue-800 disabled:opacity-50 transition-colors flex items-center justify-center gap-1.5"
            >
              <div v-if="submitting" class="animate-spin w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full" />
              <span>{{ submitting ? 'جاري...' : 'إرسال للمطبخ' }}</span>
            </button>
          </div>

        </div>
      </div>
    </div>

    <!-- ── Note editor modal ── -->
    <Transition name="modal">
      <div
        v-if="editingNoteId !== null"
        class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
        @click.self="editingNoteId = null"
      >
        <div class="bg-white rounded-2xl p-5 w-full max-w-sm shadow-2xl">
          <h3 class="font-bold text-gray-900 mb-1 text-base">ملاحظة على الصنف</h3>
          <p class="text-xs text-gray-400 mb-3">مثال: بدون ثوم، حار جداً، بدون خل</p>
          <textarea
            v-model="tempNote"
            rows="3"
            placeholder="اكتب الملاحظة هنا..."
            class="w-full border border-stone-300 rounded-xl p-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
            autofocus
          />
          <div class="flex gap-2 mt-3">
            <button
              @click="editingNoteId = null"
              class="flex-1 py-2.5 border-2 border-stone-200 rounded-xl text-sm font-semibold text-gray-600 hover:bg-gray-50 transition-colors"
            >إلغاء</button>
            <button
              @click="saveNote"
              class="flex-1 py-2.5 bg-blue-700 text-white rounded-xl text-sm font-bold hover:bg-blue-800 transition-colors"
            >حفظ الملاحظة</button>
          </div>
        </div>
      </div>
    </Transition>

    <!-- ── اختيار الحجم/النوع (Variant) ── -->
    <AppModal
      :open="variantPickerItem !== null"
      :title="`اختر الحجم/النوع — ${variantPickerItem?.name_ar || variantPickerItem?.name || ''}`"
      size="sm"
      @close="onVariantPickerClose"
    >
      <div v-if="variantPickerItem" class="space-y-2">
        <button
          v-for="variant in variantPickerItem.variants!.filter(v => v.is_available)"
          :key="variant.id"
          @click="onVariantPick(variantPickerItem!, variant)"
          class="w-full flex items-center justify-between gap-2 p-3 rounded-xl border-2 border-stone-200 hover:border-blue-400 hover:bg-blue-50/50 transition-all text-right"
        >
          <span class="font-semibold text-gray-900 text-sm">{{ variant.name_ar || variant.name }}</span>
          <span class="font-black text-blue-700">{{ variant.price }} ج</span>
        </button>
      </div>
    </AppModal>

    <!-- ── Active orders list ── -->
    <AppModal :open="activeOrdersOpen" title="الطلبات الجارية" size="sm" @close="activeOrdersOpen = false">
      <div v-if="activeOrdersLoading" class="flex items-center justify-center py-8">
        <div class="animate-spin w-7 h-7 border-4 border-blue-600 border-t-transparent rounded-full" />
      </div>
      <EmptyState v-else-if="activeOrders.length === 0" icon="🧾" title="مفيش طلبات جارية دلوقتي" />
      <div v-else class="space-y-2">
        <div
          v-for="o in activeOrders"
          :key="o.id"
          class="flex items-center gap-2 p-3 rounded-xl border-2 border-blue-100 bg-blue-50/50 hover:border-blue-300 transition-all"
        >
          <!-- معلومات الطلب -->
          <button @click="openOrder(o.id)" class="flex-1 text-right">
            <div class="font-bold text-gray-900 text-sm">{{ o.order_number }}</div>
            <div class="text-xs text-gray-500">{{ tableLabelFor(o) }} · {{ o.status }}</div>
          </button>
          <div class="text-left flex-shrink-0">
            <div class="font-bold text-blue-700 text-sm">{{ o.total }} ج</div>
          </div>
          <!-- #3: زر إضافة أصناف — متاح فقط للطلبات open أو in_kitchen -->
          <button
            v-if="o.status === 'open' || o.status === 'in_kitchen'"
            @click="openAddItems(o)"
            class="flex-shrink-0 bg-green-100 hover:bg-green-200 text-green-800 text-xs font-bold px-2 py-1.5 rounded-lg transition-colors"
            title="إضافة أصناف لهذا الطلب"
          >➕ أصناف</button>
        </div>
      </div>
    </AppModal>

    <OrderDetailModal
      :order-id="selectedOrderId"
      :tables="tables"
      @close="onOrderDetailClosed"
      @changed="loadActiveOrders(); refreshTables()"
    />

    <!-- ── #3: Modal إضافة أصناف لطلب مفتوح ── -->
    <AppModal
      :open="addItemsOpen"
      :title="`➕ إضافة أصناف — ${addItemsOrderNum}`"
      size="lg"
      @close="addItemsOrderId = null; addItemsCart = []"
    >
      <div class="flex flex-col gap-4">
        <!-- Category tabs مصغّرة -->
        <div class="flex gap-1 flex-wrap">
          <button
            @click="selectedCategoryId = null"
            :class="['px-2 py-1 rounded-lg text-xs font-medium transition-colors',
              selectedCategoryId === null ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200']"
          >الكل</button>
          <button
            v-for="cat in categories" :key="cat.id"
            @click="selectedCategoryId = cat.id"
            :class="['px-2 py-1 rounded-lg text-xs font-medium transition-colors',
              selectedCategoryId === cat.id ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-600 hover:bg-gray-200']"
          >{{ cat.name_ar || cat.name }}</button>
        </div>

        <!-- قائمة الأصناف -->
        <div class="grid grid-cols-3 sm:grid-cols-4 gap-2 max-h-48 overflow-y-auto">
          <button
            v-for="item in filteredItems" :key="item.id"
            @click="addItemsAddToCart(item)"
            :disabled="isItemOutOfWindow(item)"
            :title="isItemOutOfWindow(item) ? itemWindowLabel(item) : undefined"
            class="bg-stone-50 border border-stone-200 rounded-lg p-2 text-right text-xs hover:border-blue-400 hover:bg-blue-50 transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:border-stone-200 disabled:hover:bg-stone-50"
          >
            <div class="font-semibold text-gray-900 leading-tight truncate">{{ item.name_ar || item.name }}</div>
            <div class="text-blue-700 font-bold mt-1">{{ item.price }} ج</div>
            <div v-if="isItemOutOfWindow(item)" class="text-[10px] text-stone-500 mt-0.5">⏰ {{ itemWindowLabel(item) }}</div>
          </button>
        </div>

        <!-- السلة المؤقتة -->
        <div v-if="addItemsCart.length" class="border-t pt-3">
          <div class="text-xs font-bold text-gray-600 mb-2">الأصناف المضافة:</div>
          <div class="space-y-1.5">
            <div v-for="(ci, idx) in addItemsCart" :key="idx"
              class="flex items-center justify-between gap-2 text-sm bg-green-50 border border-green-200 rounded-lg px-3 py-1.5"
            >
              <span class="font-medium text-gray-800 flex-1 truncate">
                {{ ci.name_ar || ci.name }}
                <span v-if="ci.variant_label" class="text-gray-400 text-xs"> — {{ ci.variant_label }}</span>
              </span>
              <div class="flex items-center gap-1 flex-shrink-0">
                <button @click="ci.quantity > 1 ? ci.quantity-- : addItemsCart.splice(idx,1)"
                  class="w-6 h-6 rounded-full bg-red-100 text-red-700 font-bold text-sm hover:bg-red-200">−</button>
                <span class="w-5 text-center font-bold text-sm">{{ ci.quantity }}</span>
                <button @click="ci.quantity++"
                  class="w-6 h-6 rounded-full bg-green-100 text-green-700 font-bold text-sm hover:bg-green-200">+</button>
              </div>
              <span class="text-blue-700 font-bold text-xs flex-shrink-0">{{ (ci.price * ci.quantity).toFixed(0) }} ج</span>
            </div>
          </div>
        </div>

        <!-- زر الإرسال -->
        <div class="flex justify-end gap-2 pt-2 border-t">
          <button @click="addItemsOrderId = null; addItemsCart = []"
            class="px-4 py-2 rounded-lg text-sm text-gray-600 bg-gray-100 hover:bg-gray-200">إلغاء</button>
          <button
            @click="submitAddItems"
            :disabled="!addItemsCart.length || addItemsSubmitting"
            class="px-5 py-2 rounded-lg text-sm font-bold text-white bg-green-600 hover:bg-green-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <span v-if="addItemsSubmitting" class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
            إرسال الأصناف للمطبخ
          </button>
        </div>
      </div>
    </AppModal>

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
