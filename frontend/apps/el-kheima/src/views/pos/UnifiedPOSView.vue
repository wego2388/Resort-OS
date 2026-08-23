<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, ENDPOINTS, useAuthStore, useResortWebSocket } from '@resort-os/core'
import { useStaffFormat } from '@resort-os/core/i18n/staff'
import { useOfflineQueue, useOrderDiscount, usePrintDocument } from '@resort-os/core/composables'
import {
  AppBadge,
  AppIcon,
  AppSelect,
  EmptyState,
  LoadingState,
  SearchInput,
  useConfirm,
  useToast,
} from '@resort-os/ui'
import type { SelectOption } from '@resort-os/ui'
import DiningExtrasModal, { type DiningExtrasItem } from '../../components/DiningExtrasModal.vue'
import DiningOrderDetailModal from '../../components/DiningOrderDetailModal.vue'
import PinGuardModal from '../../components/PinGuardModal.vue'
import POSActiveOrdersWorkspace from '../../components/dining-pos/POSActiveOrdersWorkspace.vue'
import POSCartPanel from '../../components/dining-pos/POSCartPanel.vue'
import POSCustomerModal from '../../components/dining-pos/POSCustomerModal.vue'
import POSGuestIdentityModal from '../../components/dining-pos/POSGuestIdentityModal.vue'
import POSPaymentModal from '../../components/dining-pos/POSPaymentModal.vue'
import POSTablesWorkspace from '../../components/dining-pos/POSTablesWorkspace.vue'
import POSBeachMapWorkspace from '../../components/dining-pos/POSBeachMapWorkspace.vue'
import type {
  ActiveOrder,
  B2BContractOption,
  BeachLocation,
  CartLine,
  DiningCategory,
  DiningItemRow,
  DiningOrderDetail,
  DiningOutlet,
  OrderType,
  POSCustomer,
  POSWorkspace,
  VenueTable,
} from '../../components/dining-pos/types'

const { t, locale } = useI18n()
const { formatMoney, name } = useStaffFormat()
const toast = useToast()
const { confirm } = useConfirm()
const { printBlob } = usePrintDocument()
const auth = useAuthStore()
const branchId = computed(() => auth.branchId)
const currency = 'EGP'
const {
  isOnline,
  pendingCount,
  submitOrder: submitOrderOnlineOrQueue,
  lastPartialRejection,
} = useOfflineQueue('dining')
const { applyingDiscount, discountError, applyDiscount: applyDiscountRule } = useOrderDiscount()

const workspace = ref<POSWorkspace>('tables')
const outlets = ref<DiningOutlet[]>([])
const selectedOutletId = ref<number | null>(null)
const categories = ref<DiningCategory[]>([])
const items = ref<DiningItemRow[]>([])
const tables = ref<VenueTable[]>([])
const activeOrders = ref<ActiveOrder[]>([])
const activeOrdersLoading = ref(false)
const menuLoading = ref(false)
const submitting = ref(false)

const orderType = ref<OrderType>('dine_in')
const selectedTableId = ref<number | null>(null)
const selectedCategoryId = ref('all')
const searchQuery = ref('')
const covers = ref(1)
const extraNote = ref('')
const cart = ref<CartLine[]>([])
const selectedCustomer = ref<POSCustomer | null>(null)
const extrasModalItem = ref<DiningItemRow | null>(null)
const customerModalOpen = ref(false)
const mobileCartOpen = ref(false)

// هوية الضيف عند فتح طاولة جديدة يدويًا (2026-08-03، طلب Mohamed) — راجع
// POSGuestIdentityModal.vue وstartTableOrder/confirmGuestIdentity تحت.
const guestIdentityModalOpen = ref(false)
const pendingIdentityTable = ref<VenueTable | null>(null)
const guestName  = ref('')
const guestPhone = ref('')

const pendingOrderId = ref<number | null>(null)
const pendingOrderNumber = ref('')
const pendingOrderStatus = ref<'held' | 'open' | null>(null)
const pendingOrderSummary = ref<{ discount_amount: number | string; total: number | string } | null>(null)
const showDiscountPinGuard = ref(false)

// 2026-08-16: إضافة أصناف لفاتورة مفتوحة بالفعل — فتح طاولة مشغولة كان
// بيوديك لعرض/دفع/إلغاء بس (DiningOrderDetailModal)، مفيش أي طريقة تضيف
// صنف تاني على نفس الفاتورة غير من غير SSH على السيرفر. الباك إند
// (dining.services.add_items_to_order، POST /dining/orders/{id}/items)
// كان جاهز بالكامل من الأول ويدعم held/open/in_kitchen/served — الفجوة
// كانت في الفرونت إند بس. عمدًا مش pendingOrderId (ده بيقفل السلة عبر
// cartLocked لخصم الوردية القديم) — appendToOrderId منفصل تمامًا فالكاشير
// يقدر يبني سلة جديدة عادي زي أي طلب جديد.
const appendToOrderId = ref<number | null>(null)
const appendToOrderNumber = ref('')

function openAddItemsToOrder(order: {
  id: number; order_number: string; outlet_id: number
  order_type: OrderType; table_id?: number | null
}) {
  selectedOrderId.value = null
  cart.value = []
  appendToOrderId.value = order.id
  appendToOrderNumber.value = order.order_number
  selectedOutletId.value = order.outlet_id
  orderType.value = order.order_type
  selectedTableId.value = order.order_type === 'dine_in' ? (order.table_id ?? null) : null
  workspace.value = 'order'
  loadMenu()
}

async function sendAppendedItems() {
  if (appendToOrderId.value === null || !hasItems.value || submitting.value) return
  submitting.value = true
  try {
    await api.post(ENDPOINTS.dining.orderItems(appendToOrderId.value), cart.value.map(line => ({
      item_id: line.itemId,
      variant_id: line.variantId ?? undefined,
      quantity: line.quantity,
      notes: line.notes || undefined,
      extra_ids: line.extraIds,
      extra_texts: line.extraTexts,
    })))
    toast.success(t('backoffice.pos.appendItems.success', { number: appendToOrderNumber.value }))
    resetDraft()
    workspace.value = 'tables'
    await Promise.all([loadTables(), loadActiveOrders()])
  } catch (e: any) {
    const detail = e?.response?.data?.detail
    const message = typeof detail === 'string' ? detail : typeof detail?.message === 'string' ? detail.message : ''
    toast.error(message || t('backoffice.pos.appendItems.error'))
  } finally {
    submitting.value = false
  }
}

function cancelAppendItems() {
  resetDraft()
  workspace.value = 'tables'
}

const selectedOrderId = ref<number | null>(null)
const directPaymentOrder = ref<DiningOrderDetail | null>(null)
const paymentOpen = ref(false)
const searchInputEl = ref<InstanceType<typeof SearchInput> | null>(null)
// ref للـ outlet select — للـ shortcut Ctrl+O
const outletSelectEl = ref<HTMLElement | null>(null)
// 2026-08-11: منطقة سكرول شبكة الأصناف — بترجع لفوق تلقائيًا كل ما الفئة أو
// البحث يتغيّر (راجع الـwatch تحت)، عشان الكاشير ميلاقيش نفسه لسه نازل في
// نص الفئة القديمة بعد ما يبدّل لفئة جديدة.
const menuScrollEl = ref<HTMLElement | null>(null)

// ── فيتشر الفنادق (2026-08-07) ─────────────────────────────────────
const selectedContractId = ref<number | null>(null)

// ── فيتشر خريطة الشمسيات (2026-08-07) ──────────────────────────────
// beach_location_id المختارة لما الكاشير يفتح طلب من الخريطة
const selectedBeachLocationId = ref<number | null>(null)

const { status: wsStatus, onMessage: onWsMessage } = useResortWebSocket(
  computed(() => branchId.value != null ? ENDPOINTS.dining.tablesWs(branchId.value) : null),
)
onWsMessage((message: any) => {
  if (message?.type === 'table_updated' || message?.type === 'tables_updated') {
    loadTables()
    loadActiveOrders()
  }
})

const listSeparator = computed(() => locale.value === 'ar' ? '، ' : ', ')
const cartLocked = computed(() => pendingOrderId.value !== null)
const hasItems = computed(() => cart.value.length > 0)
const cartSubtotal = computed(() => cart.value.reduce((sum, line) => sum + line.unitPrice * line.quantity, 0))

const outletOptions = computed<SelectOption[]>(() => outlets.value.map(outlet => ({
  value: outlet.id,
  label: localizedName(outlet),
})))

const orderTypeOptions = computed<Array<{ value: OrderType; label: string; icon: string }>>(() => [
  { value: 'dine_in', label: t('backoffice.pos.orderTypes.dineIn'), icon: '🍽️' },
  { value: 'takeaway', label: t('backoffice.pos.orderTypes.takeaway'), icon: '🥡' },
  { value: 'delivery', label: t('backoffice.pos.orderTypes.delivery'), icon: '🛵' },
  { value: 'room_service', label: t('backoffice.pos.orderTypes.roomService'), icon: '🛎️' },
])

// 2026-08-11: تحسين ذكي — الصنف الخلصان من المخزون (is_available=false) كان
// بيختفي من الشبكة تمامًا بدل ما يظهر معطّل. ده كان بيربك الكاشير (يفتكر
// الصنف مش موجود في المنيو أصلاً فيدوّر تاني أو يسأل المدير غلط) — دلوقتي
// بيفضل ظاهر مكانه، رمادي مع badge "غير متاح"، وغير قابل للضغط، ومرتّب في
// آخر القائمة عشان الأصناف المتاحة تفضل هي اللي قدام العين أول حاجة.
// 2026-08-11: "الأكثر طلبًا" — تحسين ذكي للمنيو، طلب Mohamed صراحةً. تتبّع
// محلي بالكامل (localStorage لكل outlet، بدون أي نداء Backend جديد ولا
// أثر على بيانات المنتجع) لعدد مرات إضافة كل صنف للسلة على الجهاز ده —
// نفس فكرة "Favorites" في أنظمة POS الاحترافية (Foodics/Toast)، بيسرّع
// اختيار الأصناف المتكررة للكاشير اللي بيشتغل على نفس المحطة يوميًا.
// 2026-08-23، طلب Mohamed صراحةً — لما النت يقطع، المنيو والطاولات كانت
// بتفضى تمامًا (الشاشة بتترسم أول مرة أو تتحدّث من غير أي بيانات مخزّنة —
// loadOutlets/loadMenu/loadTables ما كانوش بيحفظوا آخر رد ناجح خالص)، يعني
// أي إعادة تحميل للصفحة أو mount جديد وقت انقطاع النت كان يسيب الكاشير من
// غير منيو ولا طاولات لحد ما النت يرجع. نفس فكرة `useOfflineQueue('dining')`
// الموجودة بالفعل (بتحفظ الطلبات المُنشأة أوفلاين وتزامنها تلقائيًا عند
// الاتصال)، بس هنا للقراءة: آخر رد ناجح من السيرفر بيتخزّن في localStorage
// (نفس نمط FREQ_STORAGE_PREFIX تحت بالظبط)، ولو أي فشل شبكة حصل، الشاشة
// بترجع لآخر نسخة معروفة بدل ما تفضى — والمزامنة الفعلية بترجع أوتوماتيك
// أول ما isOnline يرجع true (راجع الـ watch تحت).
const CACHE_STORAGE_PREFIX = 'pos:dining:cache:'

function loadCached<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(`${CACHE_STORAGE_PREFIX}${key}`)
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

function saveCached<T>(key: string, value: T) {
  try {
    localStorage.setItem(`${CACHE_STORAGE_PREFIX}${key}`, JSON.stringify(value))
  } catch {
    // localStorage ممكن يبقى غير متاح (وضع خاص/سعة ممتلئة) — الكاش تحسين
    // إضافي بس، مفيش داعي يوقف تدفق الطلب لأجله.
  }
}

const FREQ_STORAGE_PREFIX = 'pos:itemFreq:'
const FREQ_MIN_TAPS = 3     // متطلب حد أدنى قبل ما الصف يظهر — يمنع صف فاضي/عشوائي أول استخدام
const FREQ_TOP_N = 8

function loadItemFrequency(outletId: number): Record<number, number> {
  try {
    const raw = localStorage.getItem(`${FREQ_STORAGE_PREFIX}${outletId}`)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

function bumpItemFrequency(outletId: number, itemId: number) {
  try {
    const freq = loadItemFrequency(outletId)
    freq[itemId] = (freq[itemId] ?? 0) + 1
    localStorage.setItem(`${FREQ_STORAGE_PREFIX}${outletId}`, JSON.stringify(freq))
  } catch {
    // localStorage ممكن يبقى غير متاح (وضع خاص/سعة ممتلئة) — تحسين تجميلي
    // بس، مفيش داعي يوقف تدفق الطلب لأجله.
  }
}

const itemFrequencyVersion = ref(0)   // بيتغيّر بعد كل إضافة عشان يجبر إعادة حساب frequentItems تحت
const frequentItems = computed(() => {
  void itemFrequencyVersion.value
  if (!selectedOutletId.value || selectedCategoryId.value !== 'all' || searchQuery.value.trim()) return []
  const freq = loadItemFrequency(selectedOutletId.value)
  return items.value
    .filter(item => item.is_available && (freq[item.id] ?? 0) >= FREQ_MIN_TAPS)
    .sort((a, b) => (freq[b.id] ?? 0) - (freq[a.id] ?? 0))
    .slice(0, FREQ_TOP_N)
})

const filteredItems = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  return items.value
    .filter(item => {
      if (selectedCategoryId.value !== 'all' && item.category_id !== Number(selectedCategoryId.value)) return false
      if (!query) return true
      return item.name.toLowerCase().includes(query) || (item.name_ar ?? '').toLowerCase().includes(query)
    })
    .sort((a, b) => Number(b.is_available) - Number(a.is_available))
})

const cartContextLabel = computed(() => {
  // شمسية/برجولة — يتحقق الأول قبل الطاولة
  if (selectedBeachLocationId.value) {
    // نرجع label محفوظ من وقت الاختيار
    return beachLocationLabel.value
  }
  if (orderType.value === 'dine_in' && selectedTableId.value) {
    const table = tables.value.find(item => item.id === selectedTableId.value)
    return table
      ? t('backoffice.pos.tableLabel', { number: table.table_number })
      : t('backoffice.pos.orderTypes.dineIn')
  }
  const option = orderTypeOptions.value.find(item => item.value === orderType.value)
  return option ? `${option.icon} ${option.label}` : ''
})

const noteLabel = computed(() => {
  if (orderType.value === 'delivery') return t('backoffice.pos.deliveryAddress')
  if (orderType.value === 'room_service') return t('backoffice.pos.roomNumber')
  return t('backoffice.pos.note')
})

// label محفوظ للشمسية/البرجولة المختارة — مثلاً "⛱️ شمسية 5"
const beachLocationLabel = ref('')

function localizedName(value: { name: string; name_ar: string | null }): string {
  return name(value)
}

function categoryName(category: DiningCategory): string {
  return localizedName(category)
}

function itemName(item: DiningItemRow): string {
  return localizedName(item)
}

function itemPrice(item: DiningItemRow): number {
  const variants = (item.variants ?? []).filter(variant => variant.is_available)
  if (variants.length) return Math.min(...variants.map(variant => Number(variant.price)))
  return Number(item.price)
}

async function loadOutlets() {
  const cacheKey = `outlets:${branchId.value}`
  try {
    const { data } = await api.get(ENDPOINTS.dining.outlets, {
      params: { branch_id: branchId.value, active_only: true },
    })
    outlets.value = data
    if (data.length && selectedOutletId.value === null) selectedOutletId.value = data[0].id
    saveCached(cacheKey, data)
  } catch {
    const cached = loadCached<DiningOutlet[]>(cacheKey)
    if (cached?.length) {
      outlets.value = cached
      if (selectedOutletId.value === null) selectedOutletId.value = cached[0].id
      if (!isOnline.value) return  // آخر نسخة معروفة كافية أثناء الانقطاع — بلاغ الخطأ زيادة مربكة
    }
    toast.error(t('backoffice.pos.errors.loadOutlets'))
  }
}

async function loadMenu() {
  if (!selectedOutletId.value) return
  const cacheKey = `menu:${selectedOutletId.value}`
  menuLoading.value = true
  try {
    const [categoryResponse, itemResponse] = await Promise.all([
      api.get(ENDPOINTS.dining.categories(selectedOutletId.value)),
      api.get(ENDPOINTS.dining.items(selectedOutletId.value), { params: { available_only: false } }),
    ])
    categories.value = categoryResponse.data
    items.value = itemResponse.data
    selectedCategoryId.value = 'all'
    saveCached(cacheKey, { categories: categoryResponse.data, items: itemResponse.data })
  } catch {
    const cached = loadCached<{ categories: DiningCategory[]; items: DiningItemRow[] }>(cacheKey)
    if (cached) {
      categories.value = cached.categories
      items.value = cached.items
      selectedCategoryId.value = 'all'
      if (!isOnline.value) { menuLoading.value = false; return }
    }
    toast.error(t('backoffice.pos.errors.loadOutletData'))
  } finally {
    menuLoading.value = false
  }
}

async function loadTables() {
  const cacheKey = `tables:${branchId.value}`
  try {
    const { data } = await api.get(ENDPOINTS.dining.tables(branchId.value ?? 0))
    tables.value = data
    saveCached(cacheKey, data)
  } catch {
    const cached = loadCached<VenueTable[]>(cacheKey)
    if (cached) {
      tables.value = cached
      if (!isOnline.value) return
    }
    toast.error(t('backoffice.pos.errors.loadTables'))
  }
}

async function loadActiveOrders() {
  activeOrdersLoading.value = true
  try {
    const fetchStatus = async (status: string): Promise<ActiveOrder[]> => {
      const result: ActiveOrder[] = []
      let page = 1
      const pageSize = 100
      while (true) {
        const { data } = await api.get(ENDPOINTS.dining.orders, {
          params: { branch_id: branchId.value, status, page, size: pageSize },
        })
        const pageItems: ActiveOrder[] = data?.items ?? []
        result.push(...pageItems)
        if (pageItems.length < pageSize) break
        page += 1
      }
      return result
    }
    const [open, kitchen, served] = await Promise.all([
      fetchStatus('open'),
      fetchStatus('in_kitchen'),
      fetchStatus('served'),
    ])
    activeOrders.value = [...open, ...kitchen, ...served]
  } catch {
    toast.error(t('backoffice.pos.errors.loadActiveOrders'))
  } finally {
    activeOrdersLoading.value = false
  }
}

function cartKey(itemId: number, variantId: number | null, extraIds: number[]): string {
  return `${itemId}:${variantId ?? ''}:${[...extraIds].sort().join(',')}`
}


/** إجمالي الكمية من نفس الصنف في السلة (كل المتغيّرات معاً) */
function itemQtyInCart(itemId: number): number {
  return cart.value.filter(l => l.itemId === itemId).reduce((s, l) => s + l.quantity, 0)
}
function onItemClick(item: DiningItemRow) {
  if (cartLocked.value || !item.is_available) return
  const hasVariants = (item.variants ?? []).some(variant => variant.is_available)
  const hasExtras = (item.extra_groups ?? []).length > 0
  if (hasVariants || hasExtras) {
    extrasModalItem.value = item
    return
  }
  addLineToCart(item, { variantId: null, extraIds: [], extraTexts: {}, notes: '' })
}

function addLineToCart(
  item: DiningItemRow,
  choice: { variantId: number | null; extraIds: number[]; extraTexts: Record<number, string>; notes: string },
) {
  const baseKey = cartKey(item.id, choice.variantId, choice.extraIds)
  const normalizedExtraIds = [...choice.extraIds].sort((a, b) => a - b).join(',')
  if (selectedOutletId.value) {
    bumpItemFrequency(selectedOutletId.value, item.id)
    itemFrequencyVersion.value += 1
  }
  const existing = cart.value.find(line => (
    line.itemId === item.id &&
    line.variantId === choice.variantId &&
    [...line.extraIds].sort((a, b) => a - b).join(',') === normalizedExtraIds &&
    Object.keys(line.extraTexts).length === 0 &&
    Object.keys(choice.extraTexts).length === 0 &&
    !line.notes &&
    !choice.notes
  ))
  if (existing) {
    existing.quantity += 1
    return
  }
  const variant = (item.variants ?? []).find(value => value.id === choice.variantId)
  const extras = (item.extra_groups ?? [])
    .flatMap(group => group.options)
    .filter(option => choice.extraIds.includes(option.id))
  const textAnswers = Object.entries(choice.extraTexts).map(([groupId, answer]) => {
    const group = (item.extra_groups ?? []).find(value => value.id === Number(groupId))
    return `${group ? localizedName(group) : ''}: ${answer}`
  })
  const extraPrice = extras.reduce((sum, option) => sum + Number(option.price_addition), 0)
  const currentOutlet = outlets.value.find(o => o.id === selectedOutletId.value)
  cart.value.push({
    key: `${baseKey}:${Date.now()}:${cart.value.length}`,
    itemId: item.id,
    outletId: selectedOutletId.value ?? 0,
    outletName: currentOutlet ? localizedName(currentOutlet) : '',
    variantId: choice.variantId,
    variantLabel: variant ? localizedName(variant) : null,
    name: item.name,
    nameAr: item.name_ar,
    unitPrice: Number(variant ? variant.price : item.price) + extraPrice,
    quantity: 1,
    notes: choice.notes,
    extraIds: choice.extraIds,
    extraTexts: choice.extraTexts,
    // منفصلين عمدًا (2026-08-23) — إضافات مُختارة مقابل إجابات نصية حرة،
    // عشان يتعرضوا مميزين في السلة بدل نص واحد مخلوط (راجع types.ts).
    extrasLabel: extras.map(option => localizedName(option)).join(listSeparator.value),
    textAnswersLabel: textAnswers.join(listSeparator.value),
  })
}

function onExtrasConfirm(choice: {
  variantId: number | null
  extraIds: number[]
  extraTexts: Record<number, string>
  notes: string
}) {
  if (!extrasModalItem.value) return
  addLineToCart(extrasModalItem.value, choice)
  extrasModalItem.value = null
}

// 2026-08-23، طلب Mohamed صراحةً — كان إنقاص الكمية لصفر بيمسح الصنف بالكامل
// بصمت (نفس فعل الحذف الصريح تمامًا)، ومسح صنف واحد (باقي إضافاته/ملاحظاته)
// كان بدون أي تأكيد خالص — عكس مسح السلة كلها (requestClearDraft) اللي عنده
// تأكيد فعلي. الحذف (سواء بالزرار أو بالإنقاص لصفر) بقى يمر بنفس useConfirm()
// الموجود بالفعل في هذا الملف، بدل مكوّن جديد.
async function adjustQuantity(key: string, delta: number) {
  if (cartLocked.value) return
  const line = cart.value.find(item => item.key === key)
  if (!line) return
  if (line.quantity + delta <= 0) {
    await removeLine(key)
    return
  }
  line.quantity += delta
}

async function removeLine(key: string) {
  if (cartLocked.value) return
  const line = cart.value.find(item => item.key === key)
  if (!line) return
  const accepted = await confirm({
    title: t('backoffice.pos.cart.removeItemTitle'),
    message: t('backoffice.pos.cart.removeItemMessage', { name: name({ name: line.name, name_ar: line.nameAr }) }),
    confirmText: t('backoffice.pos.cart.removeItemConfirm'),
    cancelText: t('backoffice.pos.cart.keepOrder'),
    danger: true,
  })
  if (!accepted) return
  cart.value = cart.value.filter(item => item.key !== key)
}

function buildOrderPayload() {
  return {
    outlet_id: selectedOutletId.value,
    table_id: orderType.value === 'dine_in' ? selectedTableId.value : null,
    order_type: orderType.value,
    guests_count: covers.value,
    notes: extraNote.value.trim() || undefined,
    customer_id: selectedCustomer.value?.id,
    // اتلقطت من POSGuestIdentityModal وقت فتح الطاولة (راجع
    // confirmGuestIdentity) — مفيش قيمة لطلبات takeaway/delivery/
    // room_service (المودال ده بس لـdine_in).
    guest_name: guestName.value.trim() || undefined,
    guest_phone: guestPhone.value.trim() || undefined,
    // ── فيتشر الفنادق (2026-08-07) ──────────────────────────────────
    b2b_contract_id: selectedContractId.value || undefined,
    // ── فيتشر خريطة الشمسيات (2026-08-07) ──────────────────────────
    beach_location_id: selectedBeachLocationId.value || undefined,
    items: cart.value.map(line => ({
      item_id: line.itemId,
      variant_id: line.variantId ?? undefined,
      quantity: line.quantity,
      notes: line.notes || undefined,
      extra_ids: line.extraIds,
      extra_texts: line.extraTexts,
    })),
  }
}

function resetDraft() {
  cart.value = []
  covers.value = 1
  extraNote.value = ''
  selectedTableId.value = null
  selectedCustomer.value = null
  pendingOrderId.value = null
  pendingOrderNumber.value = ''
  pendingOrderStatus.value = null
  pendingOrderSummary.value = null
  appendToOrderId.value = null
  appendToOrderNumber.value = ''
  mobileCartOpen.value = false
  guestName.value = ''
  guestPhone.value = ''
  // ── فيتشر الفنادق + الشمسيات (2026-08-07) ──
  selectedContractId.value = null
  selectedBeachLocationId.value = null
}

async function cancelAndResetDraft(): Promise<boolean> {
  if (pendingOrderId.value !== null) {
    try {
      await api.patch(ENDPOINTS.dining.orderStatus(pendingOrderId.value), { status: 'cancelled' })
    } catch {
      toast.error(t('backoffice.pos.errors.cancelHeldOrder'))
      return false
    }
  }
  resetDraft()
  await Promise.all([loadTables(), loadActiveOrders()])
  return true
}

async function requestClearDraft() {
  if (!hasItems.value && pendingOrderId.value === null) return
  const accepted = await confirm({
    title: t('backoffice.pos.cart.clearTitle'),
    message: t('backoffice.pos.cart.clearMessage'),
    confirmText: t('backoffice.pos.cart.clearConfirm'),
    cancelText: t('backoffice.pos.cart.keepOrder'),
    danger: true,
  })
  if (accepted) await cancelAndResetDraft()
}

function validateDraft(): boolean {
  if (!hasItems.value || !selectedOutletId.value) return false
  if (orderType.value === 'dine_in' && !selectedTableId.value && !selectedBeachLocationId.value) {
    toast.error(t('backoffice.pos.errors.selectTableRequired'))
    workspace.value = 'tables'
    return false
  }
  return true
}

function stageServerOrder(order: DiningOrderDetail, status: 'held' | 'open') {
  pendingOrderId.value = order.id
  pendingOrderNumber.value = order.order_number
  pendingOrderStatus.value = status
  pendingOrderSummary.value = {
    discount_amount: order.discount_amount,
    total: order.total,
  }
}

async function applyDiscountToCart() {
  if (!validateDraft() || applyingDiscount.value || !selectedOutletId.value) return
  if (pendingOrderId.value === null) {
    try {
      const { data } = await api.post(
        ENDPOINTS.dining.outletOrdersHold(selectedOutletId.value),
        buildOrderPayload(),
      )
      stageServerOrder(data, 'held')
    } catch {
      toast.error(t('backoffice.pos.errors.holdOrderForDiscount'))
      return
    }
  }
  showDiscountPinGuard.value = true
}

function onDiscountPinApproved(approval: { approverUserId: number | null; approverPin: string | null }) {
  showDiscountPinGuard.value = false
  performDiscount(approval)
}

async function performDiscount(approval: { approverUserId: number | null; approverPin: string | null }) {
  if (pendingOrderId.value === null) return
  try {
    const data = await applyDiscountRule(pendingOrderId.value, approval)
    pendingOrderSummary.value = { discount_amount: data.discount_amount, total: data.total }
    toast.success(Number(data.discount_amount) > 0
      ? t('backoffice.pos.discountApplied', { amount: formatMoney(data.discount_amount, currency) })
      : t('backoffice.pos.noActiveDiscountRule'))
  } catch {
    // useOrderDiscount exposes the localized/renderable message inline.
  }
}

async function printReceipt(orderId: number) {
  try {
    const response = await api.get(ENDPOINTS.dining.receipt(orderId), { responseType: 'blob' })
    const outcome = printBlob(response.data, `dining-receipt-${orderId}.pdf`)
    if (outcome.downloadedInstead) toast.warning(t('backoffice.pos.receiptDownloadedInstead'))
  } catch {
    // Printing is a convenience after a confirmed server transition; failure
    // must never roll back or misreport the order itself.
  }
}

async function sendOrderToKitchen() {
  if (!validateDraft() || submitting.value || !selectedOutletId.value) return
  submitting.value = true
  let orderId: number | null = pendingOrderId.value
  try {
    if (pendingOrderId.value !== null) {
      if (pendingOrderStatus.value === 'held') {
        const { data } = await api.patch(ENDPOINTS.dining.orderStatus(pendingOrderId.value), { status: 'open' })
        stageServerOrder(data, 'open')
      }
    } else {
      const data = await submitOrderOnlineOrQueue(branchId.value ?? 0, buildOrderPayload(), selectedOutletId.value)
      if (data === null) {
        resetDraft()
        workspace.value = orderType.value === 'dine_in' ? 'tables' : 'order'
        toast.success(t('backoffice.pos.offlineSaved'))
        return
      }
      orderId = data.id
      stageServerOrder(data, 'open')
    }

    orderId = pendingOrderId.value
    if (!orderId) return
    await api.patch(ENDPOINTS.dining.orderStatus(orderId), { status: 'in_kitchen' })
    await printReceipt(orderId)
    resetDraft()
    toast.success(t('backoffice.pos.kitchenSentSuccess'))
    selectedOrderId.value = orderId
    await Promise.all([loadTables(), loadActiveOrders()])
  } catch {
    toast.error(t('backoffice.pos.errors.sendToKitchen'))
    if (orderId) selectedOrderId.value = orderId
  } finally {
    submitting.value = false
  }
}

async function openDirectPayment() {
  if (!validateDraft() || submitting.value || !selectedOutletId.value) return
  if (!isOnline.value) {
    toast.error(t('backoffice.pos.cart.paymentOffline'))
    return
  }
  submitting.value = true
  try {
    let order: DiningOrderDetail
    if (pendingOrderId.value !== null) {
      if (pendingOrderStatus.value === 'held') {
        const { data } = await api.patch(ENDPOINTS.dining.orderStatus(pendingOrderId.value), { status: 'open' })
        order = data
        stageServerOrder(order, 'open')
      } else {
        const { data } = await api.get(ENDPOINTS.dining.order(pendingOrderId.value))
        order = data
      }
    } else {
      const { data } = await api.post(ENDPOINTS.dining.outletOrders(selectedOutletId.value), buildOrderPayload())
      order = data
      stageServerOrder(order, 'open')
    }
    directPaymentOrder.value = order
    pendingOrderSummary.value = { discount_amount: order.discount_amount, total: order.total }
    paymentOpen.value = true
    mobileCartOpen.value = false
  } catch {
    toast.error(t('backoffice.pos.errors.createForPayment'))
  } finally {
    submitting.value = false
  }
}

async function onDirectPaymentCompleted(order: DiningOrderDetail) {
  paymentOpen.value = false
  directPaymentOrder.value = null
  resetDraft()
  toast.success(t('backoffice.pos.payment.success', { number: order.order_number }))
  workspace.value = order.order_type === 'dine_in' ? 'tables' : 'order'
  await Promise.all([loadTables(), loadActiveOrders()])
}

async function selectOutlet(value: string | number) {
  // cross-outlet (2026-08-02): تبديل المنفذ بيغيّر المنيو المعروضة بس —
  // الطلب/السلة الحاليين يفضلوا زي ما هم دايمًا. الكاشير يقدر يضيف صنف
  // مطعم وصنف كافيه على نفس الفاتورة من غير إلغاء أو تحذير (الـBackend
  // بيسجّل outlet كل صنف بنفسه، راجع dining/services.py add_items_to_order).
  const nextId = Number(value)
  if (nextId === selectedOutletId.value) return
  selectedOutletId.value = nextId
  await loadMenu()
}

async function changeOrderType(nextType: OrderType) {
  if (nextType === orderType.value) return
  if (hasItems.value || pendingOrderId.value !== null) {
    const accepted = await confirm({
      title: t('backoffice.pos.switchOrderType.title'),
      message: t('backoffice.pos.switchOrderType.message'),
      confirmText: t('backoffice.pos.switchOrderType.confirm'),
      cancelText: t('backoffice.pos.cart.keepOrder'),
      danger: true,
    })
    if (!accepted || !(await cancelAndResetDraft())) return
  }
  orderType.value = nextType
  selectedTableId.value = null
  workspace.value = nextType === 'dine_in' ? 'tables' : 'order'
}

async function startTableOrder(table: VenueTable) {
  if ((hasItems.value || pendingOrderId.value !== null) && selectedTableId.value !== table.id) {
    const accepted = await confirm({
      title: t('backoffice.pos.tablesWorkspace.changeTableTitle'),
      message: t('backoffice.pos.tablesWorkspace.changeTableMessage'),
      confirmText: t('backoffice.pos.tablesWorkspace.changeTableConfirm'),
      cancelText: t('backoffice.pos.cart.keepOrder'),
      danger: true,
    })
    if (!accepted || !(await cancelAndResetDraft())) return
  }
  // طاولة فاضية دايمًا (POSTablesWorkspace.activate بيوجّه طاولة فيها
  // active_order_id لـ emit('open', ...) بدل 'start') — يعني هنا فعليًا
  // "فتح طاولة جديدة"، فاسم الضيف إجباري قبل ما نكمل (راجع
  // confirmGuestIdentity تحت لباقي المنطق الأصلي).
  pendingIdentityTable.value = table
  guestIdentityModalOpen.value = true
}

function confirmGuestIdentity({ name, phone }: { name: string; phone: string | undefined }) {
  const table = pendingIdentityTable.value
  guestIdentityModalOpen.value = false
  pendingIdentityTable.value = null
  if (!table) return
  guestName.value = name
  guestPhone.value = phone ?? ''
  orderType.value = 'dine_in'
  selectedTableId.value = table.id
  covers.value = Math.max(1, table.capacity > 0 ? Math.min(2, table.capacity) : 1)
  workspace.value = 'order'
}

function openOrder(orderId: number) {
  selectedOrderId.value = orderId
}

async function onOrderDetailClosed() {
  selectedOrderId.value = null
  await Promise.all([loadTables(), loadActiveOrders()])
}

function openWorkspace(next: POSWorkspace) {
  workspace.value = next
  // كلا الـ workspace 'active' و 'beach_map' يحتاجوا الطلبات النشطة محدّثة:
  // 'active' → يعرضها مباشرة، 'beach_map' → يلوّن الشمسيات المشغولة بطلب دايننج.
  if (next === 'active' || next === 'beach_map') loadActiveOrders()
}

// 2026-08-23، طلب Mohamed صراحةً — كان الكاشير مجبر يمر بشاشة الطاولات (ويكتب
// اسم ضيف إجباري) قبل ما يشوف المنيو خالص، حتى لو الطلب تيك أواي/توصيل/خدمة
// غرف مش صالة، لأن orderType الافتراضي 'dine_in' دايمًا. صف اختيار نوع الطلب
// موجود بالفعل جوه شاشة 'order' — المشكلة كانت في التنقّل بس، مش في التصميم.
// دلوقتي بيوديك لشاشة الطلب مباشرة أيًا كان النوع الحالي؛ لو الكاشير اختار
// "صالة" فعلاً، changeOrderType() الموجودة أصلاً بتوديه لشاشة الطاولات —
// سلوك الصالة نفسه متغيّرش، اتشالت بس البوابة الإجبارية قبل اختيار النوع.
function beginNewOrder() {
  workspace.value = 'order'
}

function selectCustomer(customer: POSCustomer) {
  selectedCustomer.value = customer
  customerModalOpen.value = false
}

function clearCustomer() {
  selectedCustomer.value = null
  customerModalOpen.value = false
}

// ── فيتشر الفنادق (2026-08-07) ──────────────────────────────────────
function onSelectHotel(contract: B2BContractOption | null) {
  selectedContractId.value = contract?.id ?? null
}

// ── فيتشر خريطة الشمسيات (2026-08-07) ──────────────────────────────
/**
 * كاشير الدايننج ضغط على شمسية/برجولة من الخريطة —
 * بيفتح منطقة الطلب ويضبط beach_location_id كبديل للطاولة.
 *
 * الشمسية مش محتاجة اسم ضيف — الـ label هو رقم الشمسية نفسه
 * ("⛱️ شمسية 5") وده كافي كـ context للكاشير والمطبخ.
 * لو الشمسية مشغولة بضيف شاطئ (has guest_name)، نستخدم اسمه تلقائياً.
 */
async function startBeachLocationOrder(location: BeachLocation) {
  if ((hasItems.value || pendingOrderId.value !== null) && selectedBeachLocationId.value !== location.id) {
    const accepted = await confirm({
      title: t('backoffice.pos.tablesWorkspace.changeTableTitle'),
      message: t('backoffice.pos.tablesWorkspace.changeTableMessage'),
      confirmText: t('backoffice.pos.tablesWorkspace.changeTableConfirm'),
      cancelText: t('backoffice.pos.cart.keepOrder'),
      danger: true,
    })
    if (!accepted || !(await cancelAndResetDraft())) return
  }

  const ICONS: Record<string, string> = {
    umbrella: '⛱️',
    pergola: '🏕️',
    sunbed: '🛋️',
    cabana: '🏖️',
  }
  const icon = ICONS[location.location_type] ?? '📍'

  // label واضح: "⛱️ Umbrella 5" — يظهر في الكارت بدل "طاولة"
  beachLocationLabel.value = `${icon} ${location.location_type} ${location.number}`

  selectedBeachLocationId.value = location.id
  orderType.value = 'dine_in'
  selectedTableId.value = null   // الشمسية بديل الطاولة
  covers.value = Math.max(1, location.guests_count || 1)

  // لو الضيف عنده اسم من تشيك-إن الشاطئ، استخدمه — وإلا اتركه فاضي
  // (الكاشير مش مطلوب منه يدخل اسم للشمسيات، الرقم كافي)
  guestName.value = location.guest_name ?? ''
  guestPhone.value = location.guest_phone ?? ''

  workspace.value = 'order'
}

function isTypingTarget(target: EventTarget | null): boolean {
  const element = target as HTMLElement | null
  return !!element && (
    ['INPUT', 'TEXTAREA', 'SELECT'].includes(element.tagName) || element.isContentEditable
  )
}

function focusSearch() {
  const root = (searchInputEl.value as any)?.$el as HTMLElement | undefined
  root?.querySelector<HTMLInputElement>('input')?.focus()
}

function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') {
    if (mobileCartOpen.value) { mobileCartOpen.value = false; return }
    if (extrasModalItem.value) { extrasModalItem.value = null; return }
    if (customerModalOpen.value) { customerModalOpen.value = false; return }
    // Escape من أي workspace غير tables → ارجع للطاولات
    if (workspace.value !== 'tables') { workspace.value = 'tables'; return }
    return
  }
  if (isTypingTarget(event.target)) return
  if (event.key === '/') {
    event.preventDefault()
    workspace.value = 'order'
    focusSearch()
    return
  }
  if (event.key === 'F4' && hasItems.value) {
    event.preventDefault()
    openDirectPayment()
    return
  }
  if (event.key === 'Enter' && event.ctrlKey && hasItems.value) {
    event.preventDefault()
    sendOrderToKitchen()
    return
  }
  // ── Shortcuts جديدة (2026-08-07) ────────────────────────────────
  // Alt+1..4 = تبديل الـ workspace
  if (event.altKey && !event.ctrlKey && !event.shiftKey) {
    if (event.key === '1') { event.preventDefault(); openWorkspace('tables'); return }
    if (event.key === '2') { event.preventDefault(); beginNewOrder(); return }
    if (event.key === '3') { event.preventDefault(); openWorkspace('active'); return }
    if (event.key === '4') { event.preventDefault(); openWorkspace('beach_map'); return }
    // Alt+O = focus على الـ outlet select
    if (event.key === 'o' || event.key === 'O') {
      event.preventDefault()
      outletSelectEl.value?.querySelector<HTMLElement>('button, select, [role="combobox"]')?.focus()
      return
    }
  }
}

watch([selectedCategoryId, searchQuery], () => {
  if (menuScrollEl.value) menuScrollEl.value.scrollTop = 0
})

// 2026-08-23 — لما الاتصال يرجع بعد انقطاع، حدّث المنيو/الطاولات/الطلبات
// النشطة فورًا من السيرفر بدل ما تستنى تفاعل الكاشير — نفس لحظة المزامنة
// اللي useOfflineQueue('dining') بيستخدمها بالفعل لتفريغ الطلبات المحفوظة
// أوفلاين (راجع تعليق CACHE_STORAGE_PREFIX فوق لمنطق القراءة أثناء الانقطاع).
watch(isOnline, (online, wasOnline) => {
  if (online && wasOnline === false) {
    loadOutlets()
    loadMenu()
    loadTables()
    loadActiveOrders()
  }
})

onMounted(async () => {
  await loadOutlets()
  await Promise.all([loadMenu(), loadTables(), loadActiveOrders()])
  window.addEventListener('keydown', handleKeydown)
})
onUnmounted(() => window.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <div class="h-full min-h-0 flex flex-col bg-stone-50 dark:bg-background">
    <div
      v-if="!isOnline"
      class="bg-amber-500 text-white text-sm font-bold px-4 py-2 flex items-center justify-center gap-2 flex-shrink-0"
    >
      <AppIcon name="offline" class="w-5 h-5" />
      <span>{{ t('backoffice.pos.offlineBanner') }}</span>
      <AppBadge v-if="pendingCount > 0" variant="warning">{{ t('backoffice.pos.pendingCount', { count: pendingCount }) }}</AppBadge>
    </div>
    <div
      v-else-if="pendingCount > 0"
      class="bg-primary-700 text-white text-sm font-bold px-4 py-2 text-center flex-shrink-0"
    >
      {{ t('backoffice.pos.syncingBanner', { count: pendingCount }) }}
    </div>
    <div
      v-if="lastPartialRejection?.length"
      class="bg-red-100 text-red-900 dark:bg-red-950/40 dark:text-red-200 text-sm font-semibold px-4 py-2 flex-shrink-0 border-b border-red-200"
    >
      {{ t('backoffice.pos.partialRejectionBanner') }}
      {{ lastPartialRejection.map(item => `${item.name} (×${item.requested_qty})`).join(listSeparator) }}
    </div>

    <header class="bg-white dark:bg-surface border-b border-stone-200 dark:border-border px-3 lg:px-4 py-2.5 flex items-center gap-3 flex-shrink-0 shadow-sm">
      <div class="w-44 lg:w-56 flex-shrink-0" ref="outletSelectEl">
        <AppSelect
          :model-value="selectedOutletId ?? ''"
          :options="outletOptions"
          :placeholder="t('backoffice.pos.selectOutlet')"
          @update:model-value="selectOutlet"
        />
      </div>

      <nav class="flex items-center gap-1.5 min-w-0 overflow-x-auto" :aria-label="t('backoffice.pos.workspaceNav.label')">
        <button
          type="button"
          :aria-current="workspace === 'tables' ? 'page' : undefined"
          :class="[
            'min-h-[46px] px-3 rounded-xl font-bold text-sm whitespace-nowrap flex items-center gap-2 transition-colors',
            workspace === 'tables' ? 'bg-primary-700 text-white' : 'text-gray-700 dark:text-gray-300 hover:bg-stone-100 dark:hover:bg-gray-800',
          ]"
          @click="openWorkspace('tables')"
        >
          <AppIcon name="table" size="sm" />
          <span>{{ t('backoffice.pos.workspaceNav.tables') }}</span>
        </button>
        <button
          type="button"
          :aria-current="workspace === 'order' ? 'page' : undefined"
          :class="[
            'min-h-[46px] px-3 rounded-xl font-bold text-sm whitespace-nowrap flex items-center gap-2 transition-colors',
            workspace === 'order' ? 'bg-primary-700 text-white' : 'text-gray-700 dark:text-gray-300 hover:bg-stone-100 dark:hover:bg-gray-800',
          ]"
          @click="beginNewOrder"
        >
          <AppIcon name="cart" size="sm" />
          <span>{{ t('backoffice.pos.workspaceNav.order') }}</span>
          <AppBadge v-if="cart.length" variant="warning" size="sm">{{ cart.length }}</AppBadge>
        </button>
        <button
          type="button"
          :aria-current="workspace === 'active' ? 'page' : undefined"
          :class="[
            'min-h-[46px] px-3 rounded-xl font-bold text-sm whitespace-nowrap flex items-center gap-2 transition-colors',
            workspace === 'active' ? 'bg-primary-700 text-white' : 'text-gray-700 dark:text-gray-300 hover:bg-stone-100 dark:hover:bg-gray-800',
          ]"
          @click="openWorkspace('active')"
        >
          <AppIcon name="clipboard" size="sm" />
          <span>{{ t('backoffice.pos.workspaceNav.active') }}</span>
          <AppBadge v-if="activeOrders.length" variant="info" size="sm">{{ activeOrders.length }}</AppBadge>
        </button>
        <button
          type="button"
          :aria-current="workspace === 'beach_map' ? 'page' : undefined"
          :class="[
            'min-h-[46px] px-3 rounded-xl font-bold text-sm whitespace-nowrap flex items-center gap-2 transition-colors',
            workspace === 'beach_map' ? 'bg-primary-700 text-white' : 'text-gray-700 dark:text-gray-300 hover:bg-stone-100 dark:hover:bg-gray-800',
          ]"
          @click="openWorkspace('beach_map')"
        >
          <span aria-hidden="true">⛱️</span>
          <span>{{ t('backoffice.pos.workspaceNav.beachMap') }}</span>
        </button>
      </nav>

      <div class="ms-auto flex items-center gap-2 flex-shrink-0">
        <span
          :class="[
            'hidden sm:inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-bold',
            wsStatus === 'connected' ? 'bg-success/10 text-success' : wsStatus === 'connecting' ? 'bg-warning/10 text-warning' : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
          ]"
          :title="wsStatus === 'connected' ? t('backoffice.pos.wsStatus.connected') : wsStatus === 'connecting' ? t('backoffice.pos.wsStatus.connecting') : t('backoffice.pos.wsStatus.disconnected')"
        >
          <span :class="['w-2 h-2 rounded-full', wsStatus === 'connected' ? 'bg-success' : wsStatus === 'connecting' ? 'bg-warning animate-pulse' : 'bg-gray-400']" />
          {{ t('backoffice.pos.workspaceNav.live') }}
        </span>
      </div>
    </header>

    <main class="flex-1 min-h-0">
      <POSTablesWorkspace
        v-if="workspace === 'tables'"
        :tables="tables"
        :outlets="outlets"
        :selected-outlet-id="selectedOutletId"
        @start="startTableOrder"
        @open="openOrder"
      />

      <POSActiveOrdersWorkspace
        v-else-if="workspace === 'active'"
        :orders="activeOrders"
        :outlets="outlets"
        :tables="tables"
        :loading="activeOrdersLoading"
        :initial-outlet-id="selectedOutletId"
        @open="openOrder"
        @refresh="loadActiveOrders"
      />

      <!-- ── فيتشر خريطة الشمسيات (2026-08-07) ─────────────────────── -->
      <POSBeachMapWorkspace
        v-else-if="workspace === 'beach_map'"
        :branch-id="branchId"
        :active-orders="activeOrders"
        @start-order="startBeachLocationOrder"
        @open-order="openOrder"
      />

      <div v-else class="pos-order-grid h-full min-h-0">
        <nav class="pos-category-rail bg-white dark:bg-surface border-e border-stone-200 dark:border-border p-2 overflow-y-auto" :aria-label="t('backoffice.pos.categoriesLabel')">
          <button
            type="button"
            :aria-pressed="selectedCategoryId === 'all'"
            :class="[
              'pos-category-button w-full min-h-[52px] rounded-xl px-3 py-2 text-sm font-bold transition-colors text-start',
              selectedCategoryId === 'all' ? 'bg-primary-700 text-white' : 'text-gray-700 dark:text-gray-300 hover:bg-stone-100 dark:hover:bg-gray-800',
            ]"
            @click="selectedCategoryId = 'all'"
          >
            {{ t('backoffice.pos.categoryAll') }}
          </button>
          <button
            v-for="category in categories"
            :key="category.id"
            type="button"
            :aria-pressed="selectedCategoryId === String(category.id)"
            :class="[
              'pos-category-button w-full min-h-[52px] rounded-xl px-3 py-2 text-sm font-bold transition-colors text-start mt-1',
              selectedCategoryId === String(category.id) ? 'bg-primary-700 text-white' : 'text-gray-700 dark:text-gray-300 hover:bg-stone-100 dark:hover:bg-gray-800',
            ]"
            @click="selectedCategoryId = String(category.id)"
          >
            {{ categoryName(category) }}
          </button>
        </nav>

        <section class="pos-menu min-h-0 flex flex-col bg-stone-50/80 dark:bg-background">
          <div class="bg-white dark:bg-surface border-b border-stone-200 dark:border-border p-3 flex flex-col xl:flex-row xl:items-center gap-3 flex-shrink-0">
            <div class="flex gap-1.5 overflow-x-auto pb-0.5" :aria-label="t('backoffice.pos.orderTypeLabel')">
              <button
                v-for="type in orderTypeOptions"
                :key="type.value"
                type="button"
                :aria-pressed="orderType === type.value"
                :class="[
                  'min-h-[44px] whitespace-nowrap rounded-xl px-3 font-bold text-sm border-2 transition-colors',
                  orderType === type.value
                    ? 'border-primary-700 bg-primary-50 text-primary-800'
                    : 'border-stone-200 dark:border-border text-gray-600 dark:text-gray-300',
                ]"
                @click="changeOrderType(type.value)"
              >
                {{ type.icon }} {{ type.label }}
              </button>
            </div>
            <div class="xl:ms-auto xl:w-72">
              <SearchInput
                ref="searchInputEl"
                v-model="searchQuery"
                :placeholder="t('backoffice.pos.searchPlaceholder')"
                :clear-label="t('backoffice.pos.clearSearch')"
                :debounce-ms="0"
              />
            </div>
          </div>

          <div ref="menuScrollEl" class="flex-1 min-h-0 overflow-y-auto p-3 lg:p-4">
            <!-- "الأكثر طلبًا" — تتبّع محلي بالجهاز، راجع frequentItems -->
            <div v-if="frequentItems.length" class="mb-4">
              <h3 class="text-xs font-black text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-2 flex items-center gap-1.5">
                <span aria-hidden="true">⭐</span> {{ t('backoffice.pos.frequentItems') }}
              </h3>
              <div class="flex gap-2 overflow-x-auto pb-1">
                <button
                  v-for="item in frequentItems"
                  :key="`freq-${item.id}`"
                  type="button"
                  :disabled="cartLocked"
                  class="flex-shrink-0 min-h-[64px] min-w-[140px] rounded-xl border-2 border-primary-200 dark:border-primary-800 bg-primary-50/60 dark:bg-primary-950/20 px-3 py-2 text-start hover:border-primary-400 active:scale-[0.98] transition-all disabled:opacity-60 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2"
                  @click="onItemClick(item)"
                >
                  <div class="font-bold text-gray-900 dark:text-gray-100 text-sm leading-snug line-clamp-2">{{ itemName(item) }}</div>
                  <div class="text-xs font-black text-primary-800 dark:text-primary-300 tabular-nums mt-1">{{ formatMoney(itemPrice(item), currency) }}</div>
                </button>
              </div>
            </div>
            <LoadingState v-if="menuLoading" :label="t('backoffice.pos.loadingMenu')" />
            <EmptyState
              v-else-if="filteredItems.length === 0"
              icon="🍽️"
              :title="t('backoffice.pos.noItems')"
              :subtitle="searchQuery ? t('backoffice.pos.noResultsFor', { query: searchQuery }) : undefined"
            />
            <div v-else class="pos-products-grid">
              <button
                v-for="item in filteredItems"
                :key="item.id"
                type="button"
                :disabled="cartLocked || !item.is_available"
                :class="[
                  'relative min-h-[138px] rounded-xl border p-3 text-start shadow-sm active:scale-[0.99] transition-all flex flex-col justify-between gap-3 disabled:cursor-not-allowed focus:outline-none focus:ring-2 focus:ring-primary-500 focus:ring-offset-2',
                  item.is_available
                    ? 'border-stone-200 dark:border-border bg-white dark:bg-surface hover:border-primary-400 hover:shadow-md disabled:opacity-60'
                    : 'border-stone-200 dark:border-border bg-stone-100 dark:bg-gray-900/40 opacity-60 grayscale-[35%]',
                ]"
                @click="onItemClick(item)"
              >
                <!-- badge كمية: يظهر لو الصنف موجود في السلة -->
                <span
                  v-if="itemQtyInCart(item.id) > 0"
                  class="absolute -top-2 -right-2 z-10 min-w-[22px] h-[22px] bg-primary-700 text-white text-[11px] font-black rounded-full flex items-center justify-center px-1 shadow"
                  :aria-label="t('backoffice.pos.itemInCartQty', { qty: itemQtyInCart(item.id) })"
                >{{ itemQtyInCart(item.id) }}</span>
                <div class="w-full">
                  <div class="flex items-start justify-between gap-2">
                    <span class="text-xs font-semibold text-gray-400 uppercase">{{ item.station }}</span>
                    <AppBadge v-if="!item.is_available" variant="danger" size="sm">{{ t('backoffice.pos.itemUnavailable') }}</AppBadge>
                    <AppBadge v-else-if="(item.extra_groups ?? []).length" variant="info" size="sm">{{ t('backoffice.pos.extrasBadge') }}</AppBadge>
                  </div>
                  <h3 class="font-black text-gray-950 dark:text-gray-100 leading-snug mt-3 line-clamp-2">{{ itemName(item) }}</h3>
                </div>
                <div class="flex items-end justify-between gap-2 w-full">
                  <span v-if="(item.variants ?? []).some(variant => variant.is_available)" class="text-xs text-gray-500 dark:text-gray-400">{{ t('backoffice.pos.fromPrice') }}</span>
                  <span class="text-lg font-black text-primary-800 dark:text-primary-300 tabular-nums">{{ formatMoney(itemPrice(item), currency) }}</span>
                </div>
              </button>
            </div>
          </div>
        </section>

        <POSCartPanel
          class="pos-cart"
          :cart="cart"
          :order-type="orderType"
          :context-label="cartContextLabel"
          :covers="covers"
          :note="extraNote"
          :note-label="noteLabel"
          :cart-locked="cartLocked"
          :pending-order-number="pendingOrderNumber"
          :item-subtotal="cartSubtotal"
          :server-summary="pendingOrderSummary"
          :customer="selectedCustomer"
          :submitting="submitting"
          :applying-discount="applyingDiscount"
          :discount-error="discountError"
          :online="isOnline"
          :branch-id="branchId"
          :selected-contract-id="selectedContractId"
          :append-order-number="appendToOrderNumber"
          @update:covers="covers = $event"
          @update:note="extraNote = $event"
          @quantity="adjustQuantity"
          @remove="removeLine"
          @clear="requestClearDraft"
          @discount="applyDiscountToCart"
          @customer="customerModalOpen = true"
          @select-hotel="onSelectHotel"
          @send="sendOrderToKitchen"
          @pay="openDirectPayment"
          @append="sendAppendedItems"
          @cancel-append="cancelAppendItems"
        />

        <button
          v-if="!mobileCartOpen"
          type="button"
          class="pos-mobile-cart md:hidden fixed z-30 bottom-4 inset-x-4 min-h-[56px] rounded-2xl bg-primary-800 text-white px-4 shadow-xl flex items-center justify-between gap-3 font-black"
          @click="mobileCartOpen = true"
        >
          <span>🛒 {{ t('backoffice.pos.cart.mobileCart', { count: cart.length }) }}</span>
          <span class="tabular-nums">{{ formatMoney(pendingOrderSummary?.total ?? cartSubtotal, currency) }}</span>
        </button>

        <Teleport to="body">
          <div v-if="mobileCartOpen" class="md:hidden fixed inset-0 z-40">
            <div class="absolute inset-0 bg-black/50" @click="mobileCartOpen = false" />
            <div class="absolute inset-x-0 bottom-0 h-[88vh] rounded-t-3xl overflow-hidden bg-white dark:bg-surface shadow-2xl">
              <button
                type="button"
                class="absolute top-2 end-2 z-10 w-11 h-11 rounded-full bg-stone-100 dark:bg-gray-800 flex items-center justify-center"
                :aria-label="t('backoffice.pos.close')"
                @click="mobileCartOpen = false"
              >
                <AppIcon name="close" />
              </button>
              <POSCartPanel
                :cart="cart"
                :order-type="orderType"
                :context-label="cartContextLabel"
                :covers="covers"
                :note="extraNote"
                :note-label="noteLabel"
                :cart-locked="cartLocked"
                :pending-order-number="pendingOrderNumber"
                :item-subtotal="cartSubtotal"
                :server-summary="pendingOrderSummary"
                :customer="selectedCustomer"
                :submitting="submitting"
                :applying-discount="applyingDiscount"
                :discount-error="discountError"
                :online="isOnline"
                :branch-id="branchId"
                :selected-contract-id="selectedContractId"
                :append-order-number="appendToOrderNumber"
                @update:covers="covers = $event"
                @update:note="extraNote = $event"
                @quantity="adjustQuantity"
                @remove="removeLine"
                @clear="requestClearDraft"
                @discount="applyDiscountToCart"
                @customer="customerModalOpen = true"
                @select-hotel="onSelectHotel"
                @send="sendOrderToKitchen"
                @pay="openDirectPayment"
                @append="sendAppendedItems"
                @cancel-append="cancelAppendItems"
              />
            </div>
          </div>
        </Teleport>
      </div>
    </main>

    <DiningExtrasModal
      :item="(extrasModalItem as DiningExtrasItem | null)"
      @confirm="onExtrasConfirm"
      @close="extrasModalItem = null"
    />
    <DiningOrderDetailModal
      :order-id="selectedOrderId"
      :tables="tables"
      :branch-id="branchId"
      @close="onOrderDetailClosed"
      @changed="loadActiveOrders(); loadTables()"
      @add-items="openAddItemsToOrder"
    />
    <POSCustomerModal
      :open="customerModalOpen"
      :branch-id="branchId"
      :selected-customer-id="selectedCustomer?.id ?? null"
      @close="customerModalOpen = false"
      @select="selectCustomer"
      @clear="clearCustomer"
    />
    <POSGuestIdentityModal
      :open="guestIdentityModalOpen"
      :table-number="pendingIdentityTable?.table_number ?? ''"
      @close="guestIdentityModalOpen = false; pendingIdentityTable = null"
      @confirm="confirmGuestIdentity"
    />
    <POSPaymentModal
      :open="paymentOpen"
      :order="directPaymentOrder"
      :branch-id="branchId"
      @close="paymentOpen = false"
      @paid="onDirectPaymentCompleted"
    />
    <PinGuardModal
      v-if="showDiscountPinGuard"
      :min-level="60"
      :title="t('backoffice.pos.discountPinGuard.title')"
      :message="t('backoffice.pos.discountPinGuard.message')"
      :loading="applyingDiscount"
      :error-message="discountError"
      @approved="onDiscountPinApproved"
      @cancel="showDiscountPinGuard = false"
    />
  </div>
</template>

<style scoped>
.pos-order-grid {
  display: grid;
  grid-template-columns: 8.75rem minmax(0, 1fr) 24rem;
  grid-template-areas: "categories menu cart";
}
.pos-category-rail { grid-area: categories; }
.pos-menu { grid-area: menu; }
.pos-cart { grid-area: cart; }
.pos-products-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(155px, 1fr));
  gap: 0.75rem;
}

@media (max-width: 1279px) {
  .pos-order-grid {
    grid-template-columns: minmax(0, 1fr) 22rem;
    grid-template-rows: auto minmax(0, 1fr);
    grid-template-areas:
      "categories cart"
      "menu cart";
  }
  .pos-category-rail {
    display: flex;
    gap: 0.375rem;
    overflow-x: auto;
    overflow-y: hidden;
    border-inline-end: 0;
    border-bottom: 1px solid rgb(231 229 228);
  }
  .pos-category-button {
    width: auto;
    min-width: max-content;
    margin-top: 0;
  }
}

@media (max-width: 767px) {
  .pos-order-grid {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto minmax(0, 1fr);
    grid-template-areas:
      "categories"
      "menu";
  }
  .pos-cart { display: none; }
  .pos-products-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
</style>
