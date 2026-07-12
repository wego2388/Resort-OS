<script setup lang="ts">
/**
 * UnifiedPOSView — first real screen against the unified `dining` API
 * (app/modules/dining/, additive next to restaurant/cafe — see
 * DINING_CUTOVER_PLAN.md). NOT wired into any nav a waiter/cashier sees by
 * default; reachable today only from the manager-only "Dining موحّد
 * (تجريبي)" section in BackOfficeLayout, for deliberate review before this
 * ever becomes the default POS path (task scope — no cutover here).
 *
 * Design points asked for explicitly:
 *  - order-type as a first-class concept (dine_in/takeaway/delivery/
 *    room_service), each showing only the fields relevant to it — mirrors
 *    the resort's previous "Click" POS's real taxonomy, with real Arabic
 *    labels (not that system's literal typos).
 *  - a visual table/zone map grouped by VenueTable.section for dine-in,
 *    not just a flat <select> (wagdy.md zone/section research).
 *  - extras modal supports the new free-text group_type (DiningExtrasModal).
 *  - void/refund reuse the existing PIN-approval pattern via
 *    DiningOrderDetailModal (no parallel approval flow invented).
 *  - built entirely from @resort-os/ui — no ad-hoc buttons/inputs/badges.
 *  - offline queue parity with restaurant/cafe (DINING_CUTOVER_PLAN.md
 *    Batch 1): useOfflineQueue('dining') — same IndexedDB queue/FIFO/
 *    fulfilled|partial|rejected contract, outlet_id threaded through
 *    (dining's create/sync routes are outlet-scoped, unlike restaurant/
 *    cafe's flat paths — see useOfflineQueue.ts's MODULE_CONFIG).
 *
 * Deliberately deferred for this pass (see CLAUDE.md §18 / PROJECT_STATUS.md):
 * course firing, kitchen timer, customer display.
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { api, useAuthStore, ENDPOINTS } from '@resort-os/core'
import { useOfflineQueue, useOrderDiscount, usePrintDocument } from '@resort-os/core/composables'
import {
  AppButton, AppBadge, AppTabs, AppSelect, SearchInput, AppTextarea,
  EmptyState, LoadingState, IconButton, useToast,
} from '@resort-os/ui'
import type { TabItem } from '@resort-os/ui'
import type { SelectOption } from '@resort-os/ui'
import DiningExtrasModal, { type DiningExtrasItem } from '../../components/DiningExtrasModal.vue'
import DiningOrderDetailModal from '../../components/DiningOrderDetailModal.vue'

const toast = useToast()
const { printBlob } = usePrintDocument()
const auth = useAuthStore()
const branchId = auth.branchId
const { isOnline, pendingCount, submitOrder: submitOrderOnlineOrQueue, lastPartialRejection } = useOfflineQueue('dining')

// ── Types ────────────────────────────────────────────────────────────────
interface Outlet { id: number; name: string; name_ar: string | null; outlet_type: string; is_active: boolean }
interface Category { id: number; name: string; name_ar: string | null; sort_order: number }
interface VenueTable { id: number; table_number: string; status: string; capacity: number; section: string | null }
interface DiningItemRow extends DiningExtrasItem {
  is_available: boolean; category_id: number | null; station: string
}
interface CartLine {
  key: string
  itemId: number; variantId: number | null; variantLabel: string | null
  name: string; nameAr: string | null; unitPrice: number
  quantity: number; notes: string
  extraIds: number[]; extraTexts: Record<number, string>
  extrasLabel: string
}
interface ActiveOrder {
  id: number; order_number: string; status: string; table_id: number | null
  order_type: string; total: number | string
}

// ── Order-type tabs — real 4-way taxonomy, not "table vs. takeaway" ───────
const ORDER_TYPE_TABS: TabItem[] = [
  { value: 'dine_in', label: '🍽️ صالة' },
  { value: 'takeaway', label: '🥡 تيك أواي' },
  { value: 'delivery', label: '🛵 توصيل' },
  { value: 'room_service', label: '🛎️ خدمة الغرف' },
]
const orderType = ref<'dine_in' | 'takeaway' | 'delivery' | 'room_service'>('dine_in')

// ── State ────────────────────────────────────────────────────────────────
const outlets = ref<Outlet[]>([])
const selectedOutletId = ref<number | null>(null)
const categories = ref<Category[]>([])
const items = ref<DiningItemRow[]>([])
const tables = ref<VenueTable[]>([])
const selectedTableId = ref<number | null>(null)
const selectedCategoryId = ref<string>('all')
const searchQuery = ref('')
const loading = ref(false)
const submitting = ref(false)
const covers = ref(1)
const extraNoteLabel = computed(() => orderType.value === 'delivery' ? 'عنوان التوصيل' : orderType.value === 'room_service' ? 'رقم الغرفة' : 'ملاحظة')
const extraNote = ref('')

const cart = ref<CartLine[]>([])
const paymentMethod = ref<'cash' | 'card' | 'room' | 'wallet'>('cash')

// Order-in-progress locked by an applied discount (server-side "held" order) —
// same pattern as RestaurantPOSView.applyDiscountToCart.
const pendingOrderId = ref<number | null>(null)
const pendingOrderNumber = ref('')
const pendingOrderSummary = ref<{ discount_amount: number | string; total: number | string } | null>(null)
const cartLocked = computed(() => pendingOrderId.value !== null)
const { applyingDiscount, discountError, applyDiscount: applyDiscountRule } = useOrderDiscount('dining')

const extrasModalItem = ref<DiningItemRow | null>(null)

const activeOrdersOpen = ref(false)
const activeOrders = ref<ActiveOrder[]>([])
const activeOrdersLoading = ref(false)
const selectedOrderId = ref<number | null>(null)
const searchInputEl = ref<InstanceType<typeof SearchInput> | null>(null)

// ── Computed ─────────────────────────────────────────────────────────────
const outletOptions = computed<SelectOption[]>(() =>
  outlets.value.map(o => ({ value: o.id, label: o.name_ar || o.name })))
// AppSelect's modelValue is `string | number | undefined` (native <select>
// values are always strings) — selectedOutletId stays `number | null`
// everywhere else (API params, comparisons), so this proxy is the only
// place the null<->undefined/string<->number conversion happens.
const selectedOutletIdOption = computed<string | number | undefined>({
  get: () => selectedOutletId.value ?? undefined,
  set: (v) => { selectedOutletId.value = v !== undefined && v !== '' ? Number(v) : null },
})

const categoryTabs = computed<TabItem[]>(() => [
  { value: 'all', label: 'الكل' },
  ...categories.value.map(c => ({ value: String(c.id), label: c.name_ar || c.name })),
])

const filteredItems = computed(() => {
  let list = items.value.filter(i => i.is_available)
  if (selectedCategoryId.value !== 'all') {
    list = list.filter(i => i.category_id === Number(selectedCategoryId.value))
  }
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    list = list.filter(i => i.name.toLowerCase().includes(q) || (i.name_ar ?? '').includes(q))
  }
  return list
})

// Zone/section-grouped table map — old "Click" POS grouped tables into a
// zone tree (Terrace -> Terrace-A); VenueTable.section is a flat string
// here, so this groups by that string as the closest honest equivalent
// without a full hierarchy rebuild (CLAUDE.md scope discipline).
const tablesBySection = computed(() => {
  const groups = new Map<string, VenueTable[]>()
  for (const t of tables.value) {
    const key = t.section || 'بدون قسم'
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(t)
  }
  return [...groups.entries()].map(([section, list]) => ({ section, tables: list }))
})

const hasItems = computed(() => cart.value.length > 0)
const cartTotal = computed(() => cart.value.reduce((s, l) => s + l.unitPrice * l.quantity, 0))
const displayTotal = computed(() => pendingOrderSummary.value?.total ?? cartTotal.value)

function cartKey(itemId: number, variantId: number | null, extraIds: number[]): string {
  return `${itemId}:${variantId ?? ''}:${[...extraIds].sort().join(',')}`
}

// ── Data loading ─────────────────────────────────────────────────────────
async function loadOutlets() {
  const { data } = await api.get(ENDPOINTS.dining.outlets, { params: { branch_id: branchId, active_only: true } })
  outlets.value = data
  if (data.length && selectedOutletId.value === null) selectedOutletId.value = data[0].id
}

async function loadOutletData() {
  if (!selectedOutletId.value) return
  loading.value = true
  try {
    const [catsRes, itemsRes, tablesRes] = await Promise.all([
      api.get(ENDPOINTS.dining.categories(selectedOutletId.value)),
      api.get(ENDPOINTS.dining.items(selectedOutletId.value), { params: { available_only: false } }),
      api.get(ENDPOINTS.dining.tables(selectedOutletId.value)),
    ])
    categories.value = catsRes.data
    items.value = itemsRes.data
    tables.value = tablesRes.data
    selectedCategoryId.value = 'all'
    selectedTableId.value = null
  } catch {
    toast.error('تعذّر تحميل بيانات المنفذ — تأكد من الاتصال وحاول تاني')
  } finally {
    loading.value = false
  }
}

async function loadActiveOrders() {
  if (!selectedOutletId.value) return
  activeOrdersLoading.value = true
  try {
    const fetchAll = async (status: string): Promise<ActiveOrder[]> => {
      const results: ActiveOrder[] = []
      let page = 1
      const PAGE_SIZE = 100
      while (true) {
        const res = await api.get(ENDPOINTS.dining.orders, {
          params: { branch_id: branchId, outlet_id: selectedOutletId.value, status, page, size: PAGE_SIZE },
        })
        const pageItems: ActiveOrder[] = res.data?.items ?? []
        results.push(...pageItems)
        if (pageItems.length < PAGE_SIZE) break
        page++
      }
      return results
    }
    const [open, kitchen, served] = await Promise.all([fetchAll('open'), fetchAll('in_kitchen'), fetchAll('served')])
    activeOrders.value = [...open, ...kitchen, ...served]
  } catch {
    toast.error('تعذّر تحميل الطلبات الجارية')
  } finally {
    activeOrdersLoading.value = false
  }
}

function openActiveOrders() {
  activeOrdersOpen.value = true
  loadActiveOrders()
}
function tableLabelFor(order: ActiveOrder): string {
  if (!order.table_id) return ORDER_TYPE_TABS.find(t => t.value === order.order_type)?.label ?? order.order_type
  const t = tables.value.find(t => t.id === order.table_id)
  return t ? `طاولة ${t.table_number}` : `طاولة #${order.table_id}`
}
function openOrder(orderId: number) {
  activeOrdersOpen.value = false
  selectedOrderId.value = orderId
}
function onOrderDetailClosed() {
  selectedOrderId.value = null
  loadActiveOrders()
}

// ── Cart building ────────────────────────────────────────────────────────
function onItemClick(item: DiningItemRow) {
  if (cartLocked.value) return
  const hasVariants = (item.variants ?? []).some(v => v.is_available)
  const hasExtras = (item.extra_groups ?? []).length > 0
  if (hasVariants || hasExtras) {
    extrasModalItem.value = item
    return
  }
  addLineToCart(item, { variantId: null, extraIds: [], extraTexts: {}, notes: '' })
}

function addLineToCart(item: DiningItemRow, choice: { variantId: number | null; extraIds: number[]; extraTexts: Record<number, string>; notes: string }) {
  const key = cartKey(item.id, choice.variantId, choice.extraIds)
  const existing = cart.value.find(l => l.key === key)
  if (existing && Object.keys(choice.extraTexts).length === 0) {
    existing.quantity++
    return
  }
  const variant = (item.variants ?? []).find(v => v.id === choice.variantId)
  const extrasNames = (item.extra_groups ?? [])
    .flatMap(g => g.options)
    .filter(o => choice.extraIds.includes(o.id))
    .map(o => o.name_ar || o.name)
  const textAnswers = Object.entries(choice.extraTexts).map(([groupId, text]) => {
    const group = (item.extra_groups ?? []).find(g => g.id === Number(groupId))
    return `${group?.name_ar || group?.name || ''}: ${text}`
  })
  const extraPrice = (item.extra_groups ?? [])
    .flatMap(g => g.options)
    .filter(o => choice.extraIds.includes(o.id))
    .reduce((s, o) => s + Number(o.price_addition), 0)

  cart.value.push({
    key: `${key}:${cart.value.length}`,
    itemId: item.id, variantId: choice.variantId,
    variantLabel: variant ? (variant.name_ar || variant.name) : null,
    name: item.name, nameAr: item.name_ar,
    unitPrice: Number(variant ? variant.price : item.price) + extraPrice,
    quantity: 1, notes: choice.notes,
    extraIds: choice.extraIds, extraTexts: choice.extraTexts,
    extrasLabel: [...extrasNames, ...textAnswers].join('، '),
  })
}

function onExtrasConfirm(choice: { variantId: number | null; extraIds: number[]; extraTexts: Record<number, string>; notes: string }) {
  if (!extrasModalItem.value) return
  addLineToCart(extrasModalItem.value, choice)
  extrasModalItem.value = null
}

function removeLine(key: string) {
  if (cartLocked.value) return
  cart.value = cart.value.filter(l => l.key !== key)
}
function adjustQty(key: string, delta: number) {
  if (cartLocked.value) return
  const line = cart.value.find(l => l.key === key)
  if (!line) return
  line.quantity = Math.max(0, line.quantity + delta)
  if (line.quantity === 0) removeLine(key)
}

async function clearOrder() {
  if (pendingOrderId.value !== null) {
    try {
      await api.patch(ENDPOINTS.dining.orderStatus(pendingOrderId.value), { status: 'cancelled' })
    } catch {
      toast.error('تعذّر إلغاء الطلب المحفوظ — راجعه من الطلبات الجارية')
    }
  }
  cart.value = []
  covers.value = 1
  extraNote.value = ''
  selectedTableId.value = null
  pendingOrderId.value = null
  pendingOrderNumber.value = ''
  pendingOrderSummary.value = null
}

function buildOrderPayload() {
  return {
    outlet_id: selectedOutletId.value,
    table_id: orderType.value === 'dine_in' ? selectedTableId.value : null,
    order_type: orderType.value,
    guests_count: covers.value,
    notes: extraNote.value.trim() || undefined,
    items: cart.value.map(l => ({
      item_id: l.itemId,
      variant_id: l.variantId ?? undefined,
      quantity: l.quantity,
      notes: l.notes || undefined,
      extra_ids: l.extraIds,
      extra_texts: l.extraTexts,
    })),
  }
}

async function applyDiscountToCart() {
  if (!hasItems.value || applyingDiscount.value || !selectedOutletId.value) return
  if (pendingOrderId.value === null) {
    try {
      const { data } = await api.post(ENDPOINTS.dining.outletOrdersHold(selectedOutletId.value), buildOrderPayload())
      pendingOrderId.value = data.id
      pendingOrderNumber.value = data.order_number
    } catch (e: any) {
      toast.error(e?.response?.data?.detail ?? 'تعذّر تسجيل الطلب لتطبيق الخصم')
      return
    }
  }
  try {
    const data = await applyDiscountRule(pendingOrderId.value!)
    pendingOrderSummary.value = { discount_amount: data.discount_amount, total: data.total }
    toast.success(Number(data.discount_amount) > 0 ? `تم تطبيق خصم ${data.discount_amount} ج ✓` : 'مفيش قاعدة خصم سارية حاليًا')
  } catch { /* discountError shown inline */ }
}

async function finalizeOrderToKitchen(orderId: number, wasHeld: boolean) {
  try {
    if (wasHeld) await api.patch(ENDPOINTS.dining.orderStatus(orderId), { status: 'open' })
    await api.patch(ENDPOINTS.dining.orderStatus(orderId), { status: 'in_kitchen' })
  } catch {
    toast.error('اتسجّل الطلب لكن حصل خطأ في إرساله للمطبخ — راجعه من الطلبات الجارية')
  }
  try {
    const receiptRes = await api.get(ENDPOINTS.dining.receipt(orderId), { responseType: 'blob' })
    const outcome = printBlob(receiptRes.data, `dining-receipt-${orderId}.pdf`)
    if (outcome.downloadedInstead) toast.warning('الإيصال اتحمّل كملف (المتصفح منع نافذة الطباعة)')
  } catch { /* receipt optional */ }
}

async function submitOrder() {
  if (!hasItems.value || submitting.value || !selectedOutletId.value) return
  if (orderType.value === 'dine_in' && !selectedTableId.value) {
    toast.error('اختر طاولة للطلب الداخلي')
    return
  }
  submitting.value = true
  try {
    if (pendingOrderId.value !== null) {
      // #5: الطلب اتنشأ بالفعل (held) وقت تطبيق الخصم — منعملش POST تاني،
      // ومحتاج نت أصلاً عشان applyDiscountToCart بيبعت مباشرة (مش عبر
      // الطابور)، فمفيش داعي لمسار offline هنا. راجع RestaurantPOSView.
      await finalizeOrderToKitchen(pendingOrderId.value, true)
    } else {
      const data = await submitOrderOnlineOrQueue(branchId, buildOrderPayload(), selectedOutletId.value)
      if (data === null) {
        // مفيش نت — اتحفظ محليًا (IndexedDB)، هيتزامن أوتوماتيك لما الاتصال يرجع
        await clearOrder()
        toast.success('📥 الطلب محفوظ — هيتبعت للمطبخ أول ما النت يرجع')
        return
      }
      await finalizeOrderToKitchen(data.id, false)
    }
    await clearOrder()
    toast.success('تم إرسال الطلب للمطبخ ✓')
    loadActiveOrders()
  } catch (e: any) {
    toast.error(e?.response?.data?.detail ?? 'فشل في إرسال الطلب')
  } finally {
    submitting.value = false
  }
}

// ── Keyboard hotkeys (POS usability, matches RestaurantPOSView) ──────────
function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el) return false
  return ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) || el.isContentEditable
}
function handleKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    if (extrasModalItem.value !== null) { extrasModalItem.value = null; return }
    if (activeOrdersOpen.value) { activeOrdersOpen.value = false; return }
    if (selectedOrderId.value !== null) { onOrderDetailClosed(); return }
    if (isTypingTarget(e.target)) return
    if (hasItems.value) clearOrder()
    return
  }
  if (isTypingTarget(e.target)) return
  if (e.key === '/') { e.preventDefault(); (searchInputEl.value as any)?.$el?.querySelector('input')?.focus(); return }
  if (e.key === 'Enter' && hasItems.value && !submitting.value) { e.preventDefault(); submitOrder() }
}

onMounted(async () => {
  await loadOutlets()
  await loadOutletData()
  loadActiveOrders()
  window.addEventListener('keydown', handleKeydown)
})
onUnmounted(() => window.removeEventListener('keydown', handleKeydown))
</script>

<template>
  <div class="flex flex-col h-full" dir="rtl">

    <!-- ── Offline banner — visible الطول، مش toast بيختفي (راجع RestaurantPOSView) ── -->
    <div
      v-if="!isOnline"
      class="bg-amber-500 text-white text-xs font-bold px-4 py-1.5 flex items-center justify-center gap-2 flex-shrink-0"
    >
      <span>⚠️ وضع offline — الطلبات بتتحفظ محلياً وهتتبعت أول ما النت يرجع</span>
      <span v-if="pendingCount > 0" class="bg-amber-700 px-2 py-0.5 rounded-full">{{ pendingCount }} في الانتظار</span>
    </div>
    <div
      v-else-if="pendingCount > 0"
      class="bg-primary-500 text-white text-xs font-bold px-4 py-1.5 flex items-center justify-center gap-2 flex-shrink-0"
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

    <!-- ── Top bar ── -->
    <div class="bg-white border-b border-stone-200 px-4 py-3 flex flex-wrap gap-3 items-center shadow-sm flex-shrink-0">
      <div class="w-48">
        <AppSelect v-model="selectedOutletIdOption" :options="outletOptions" placeholder="اختر المنفذ" @update:model-value="loadOutletData(); loadActiveOrders()" />
      </div>

      <AppTabs v-model="orderType" :tabs="ORDER_TYPE_TABS" />

      <button
        type="button"
        @click="openActiveOrders"
        class="relative px-3 py-2 bg-white border-2 border-primary-400 text-primary-700 rounded-lg font-bold text-sm hover:bg-primary-50 transition-colors min-h-[48px]"
      >
        🧾 الطلبات الجارية
        <AppBadge v-if="activeOrders.length" variant="info" size="sm" class="ms-1.5">{{ activeOrders.length }}</AppBadge>
      </button>

      <div class="w-56">
        <SearchInput ref="searchInputEl" v-model="searchQuery" placeholder="🔍 بحث في الأصناف... (/)" />
      </div>

      <span
        class="text-gray-300 hover:text-gray-500 cursor-help text-sm select-none transition-colors"
        title="⌨️ /  — تركيز على البحث · Enter — إرسال الطلب · Esc — إغلاق/مسح"
      >⌨️</span>
    </div>

    <!-- ── Order-type-specific fields ── -->
    <div class="bg-stone-50 border-b border-stone-200 px-4 py-3 flex-shrink-0">
      <template v-if="orderType === 'dine_in'">
        <div class="text-xs font-bold text-gray-500 uppercase tracking-wide mb-2">اختر الطاولة</div>
        <div v-if="tables.length === 0" class="text-sm text-gray-400">لا توجد طاولات لهذا المنفذ</div>
        <div v-for="group in tablesBySection" :key="group.section" class="mb-2 last:mb-0">
          <div class="text-xs font-semibold text-gray-400 mb-1">{{ group.section }}</div>
          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="t in group.tables"
              :key="t.id"
              type="button"
              :disabled="cartLocked || t.status === 'out_of_service'"
              @click="selectedTableId = t.id"
              :class="[
                'min-w-[64px] min-h-[48px] px-3 py-2 rounded-xl border-2 text-sm font-bold transition-all flex flex-col items-center justify-center gap-0.5',
                selectedTableId === t.id ? 'border-primary-600 bg-primary-50 text-primary-800' : 'border-stone-200 bg-white hover:border-primary-300',
                t.status === 'occupied' ? 'ring-2 ring-danger/40' : '',
                t.status === 'out_of_service' ? 'opacity-40 cursor-not-allowed' : '',
              ]"
            >
              <span>{{ t.table_number }}</span>
              <span class="text-[10px] font-normal text-gray-400">{{
                t.status === 'available' ? 'فارغة' : t.status === 'occupied' ? 'مشغولة' : t.status === 'reserved' ? 'محجوزة' : 'خارج الخدمة'
              }}</span>
            </button>
          </div>
        </div>
        <div class="flex items-center gap-2 mt-2">
          <label class="text-xs font-semibold text-gray-600">الغطاءات:</label>
          <IconButton icon="remove" label="تقليل الغطاءات" size="sm" :disabled="cartLocked" @click="covers = Math.max(1, covers - 1)" />
          <span class="w-6 text-center font-bold text-sm">{{ covers }}</span>
          <IconButton icon="add" label="زيادة الغطاءات" size="sm" :disabled="cartLocked" @click="covers++" />
        </div>
      </template>

      <template v-else-if="orderType === 'delivery' || orderType === 'room_service'">
        <AppTextarea v-model="extraNote" :label="extraNoteLabel" :rows="2" :disabled="cartLocked" />
      </template>

      <template v-else>
        <div class="text-sm text-gray-500">🥡 تيك أواي — أسرع مسار، بدون طاولة</div>
      </template>
    </div>

    <!-- ── Main split: menu + cart ── -->
    <div class="flex flex-1 overflow-hidden">
      <div class="flex-1 overflow-y-auto p-4 bg-stone-50">
        <div class="mb-3">
          <AppTabs v-model="selectedCategoryId" :tabs="categoryTabs" />
        </div>

        <LoadingState v-if="loading" />
        <EmptyState v-else-if="filteredItems.length === 0" icon="🍽️" title="لا توجد أصناف" :subtitle="searchQuery ? `لا نتائج لـ «${searchQuery}»` : undefined" />
        <div v-else class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 xl:grid-cols-5 gap-3">
          <button
            v-for="item in filteredItems"
            :key="item.id"
            type="button"
            :disabled="cartLocked"
            @click="onItemClick(item)"
            class="relative bg-white rounded-xl border border-stone-200 p-4 text-start hover:border-primary-400 hover:shadow-elevation-2 transition-all active:scale-95 flex flex-col justify-between min-h-[90px] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <div class="font-semibold text-gray-900 text-sm leading-tight mb-2">{{ item.name_ar || item.name }}</div>
            <div v-if="(item.variants ?? []).some(v => v.is_available)" class="text-sm font-bold text-primary-700">
              من {{ Math.min(...item.variants!.filter(v => v.is_available).map(v => Number(v.price))) }}
              <span class="text-xs font-normal text-gray-400 ms-0.5">ج · اختر الحجم</span>
            </div>
            <div v-else class="text-lg font-black text-primary-700">{{ item.price }}<span class="text-xs font-normal text-gray-400 ms-0.5">ج</span></div>
            <AppBadge v-if="(item.extra_groups ?? []).length > 0" variant="info" size="sm" class="absolute top-1.5 start-1.5">إضافات</AppBadge>
          </button>
        </div>
      </div>

      <!-- ── Cart sidebar ── -->
      <div class="w-80 bg-white border-s border-stone-200 flex flex-col flex-shrink-0 shadow-elevation-3">
        <div class="p-4 border-b border-stone-100 bg-stone-50">
          <div class="font-bold text-gray-900">
            {{ orderType === 'dine_in' && selectedTableId ? `طاولة ${tables.find(t => t.id === selectedTableId)?.table_number}` : ORDER_TYPE_TABS.find(t => t.value === orderType)?.label }}
          </div>
        </div>

        <div class="flex-1 overflow-y-auto p-3 space-y-2">
          <EmptyState v-if="cart.length === 0" icon="🛒" title="اختر أصناف من القائمة" />

          <div v-if="cartLocked" class="bg-success/10 border border-success/30 rounded-lg px-3 py-2 text-xs text-success">
            🔒 الطلب #{{ pendingOrderNumber }} اتسجّل وطُبّق عليه خصم — امسح الطلب لو عايز تعدّل
          </div>

          <div v-for="line in cart" :key="line.key" class="bg-stone-50 rounded-lg p-3 border border-stone-200">
            <div class="flex items-start justify-between mb-2 gap-1">
              <span class="text-sm font-semibold text-gray-900 leading-tight flex-1">
                {{ line.nameAr || line.name }}
                <span v-if="line.variantLabel" class="text-xs font-normal text-primary-600">— {{ line.variantLabel }}</span>
              </span>
              <IconButton icon="close" label="حذف الصنف" size="sm" variant="danger" :disabled="cartLocked" @click="removeLine(line.key)" />
            </div>
            <div v-if="line.extrasLabel" class="text-xs text-gray-500 mb-1.5">{{ line.extrasLabel }}</div>
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-1.5">
                <IconButton icon="remove" label="تقليل الكمية" size="sm" :disabled="cartLocked" @click="adjustQty(line.key, -1)" />
                <span class="text-sm font-bold w-5 text-center">{{ line.quantity }}</span>
                <IconButton icon="add" label="زيادة الكمية" size="sm" :disabled="cartLocked" @click="adjustQty(line.key, 1)" />
              </div>
              <span class="text-sm font-bold text-primary-700">{{ (line.unitPrice * line.quantity).toFixed(2) }} ج</span>
            </div>
          </div>
        </div>

        <div class="border-t border-stone-200 p-3 space-y-3 bg-white">
          <div class="flex justify-between items-center">
            <span class="text-base font-bold text-gray-900">المجموع</span>
            <span class="text-xl font-black text-primary-700">{{ displayTotal }} ج</span>
          </div>

          <div v-if="!cartLocked">
            <AppButton variant="outline" size="sm" block :disabled="!hasItems" :loading="applyingDiscount" @click="applyDiscountToCart">🏷️ تطبيق خصم</AppButton>
            <p v-if="discountError" class="text-xs text-danger mt-1 text-center">{{ discountError }}</p>
          </div>
          <div v-else class="rounded-lg border-2 border-success/30 bg-success/10 px-3 py-2 text-xs">
            <div class="flex justify-between text-success font-bold">
              <span>خصم مطبّق ✓</span>
              <span v-if="pendingOrderSummary && Number(pendingOrderSummary.discount_amount) > 0">−{{ pendingOrderSummary.discount_amount }} ج</span>
            </div>
          </div>

          <div class="grid grid-cols-2 gap-2">
            <AppButton variant="ghost" :disabled="!hasItems" @click="clearOrder">مسح</AppButton>
            <AppButton variant="primary" :disabled="!hasItems" :loading="submitting" @click="submitOrder">إرسال للمطبخ</AppButton>
          </div>
        </div>
      </div>
    </div>

    <!-- ── Extras/variant picker ── -->
    <DiningExtrasModal :item="extrasModalItem" @confirm="onExtrasConfirm" @close="extrasModalItem = null" />

    <!-- ── Active orders drawer ── -->
    <DiningOrderDetailModal :order-id="selectedOrderId" :tables="tables" @close="onOrderDetailClosed" @changed="loadActiveOrders" />

    <Teleport to="body">
      <Transition name="fade">
        <div v-if="activeOrdersOpen" class="fixed inset-0 z-40 flex items-center justify-center p-4">
          <div class="absolute inset-0 bg-black/50" @click="activeOrdersOpen = false" />
          <div class="relative bg-white rounded-2xl shadow-2xl w-full max-w-sm max-h-[80vh] flex flex-col">
            <div class="flex items-center justify-between px-5 py-4 border-b border-stone-100">
              <h2 class="text-lg font-bold text-gray-900">الطلبات الجارية</h2>
              <IconButton icon="close" label="إغلاق" size="sm" @click="activeOrdersOpen = false" />
            </div>
            <div class="overflow-y-auto p-4 space-y-2">
              <LoadingState v-if="activeOrdersLoading" />
              <EmptyState v-else-if="activeOrders.length === 0" icon="🧾" title="مفيش طلبات جارية دلوقتي" />
              <button
                v-for="o in activeOrders"
                :key="o.id"
                type="button"
                @click="openOrder(o.id)"
                class="w-full flex items-center gap-2 p-3 rounded-xl border-2 border-primary-100 bg-primary-50/50 hover:border-primary-300 transition-all text-start min-h-[48px]"
              >
                <div class="flex-1">
                  <div class="font-bold text-gray-900 text-sm">{{ o.order_number }}</div>
                  <div class="text-xs text-gray-500">{{ tableLabelFor(o) }} · {{ o.status }}</div>
                </div>
                <div class="font-bold text-primary-700 text-sm">{{ o.total }} ج</div>
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.fade-enter-active, .fade-leave-active { transition: opacity 0.2s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }
</style>
